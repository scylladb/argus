package cmd

import (
	"archive/tar"
	"bufio"
	"bytes"
	"compress/gzip"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"mime"
	"net/http"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"github.com/klauspost/compress/zstd"
	"github.com/scylladb/argus/cli/internal/api"
	"github.com/scylladb/argus/cli/internal/logging"
	"github.com/scylladb/argus/cli/internal/models"
	"github.com/spf13/cobra"
)

// The format of a log body comes from its content. The magic bytes give the
// compression, and a tar header in the decompressed stream marks a tar
// archive. The log name gives the output file name of a single log file.
var (
	gzipMagic = []byte{0x1f, 0x8b}
	zstdMagic = []byte{0x28, 0xb5, 0x2f, 0xfd}
	tarMagic  = []byte("ustar")

	compressionSuffixes = [...]string{".gz", ".zst", ".zstd"}
)

// tarMagicOffset is the offset of the "ustar" magic in a POSIX or GNU tar
// header.
const tarMagicOffset = 257

// maxErrorEnvelopeSize is the largest JSON body that is checked for an Argus
// error envelope. An error envelope is much smaller.
const maxErrorEnvelopeSize = 64 << 10

// isZstdStart reports whether head starts a zstd stream: a zstd frame or a
// skippable frame (magic 0x184D2A50 to 0x184D2A5F, little-endian).
func isZstdStart(head []byte) bool {
	if bytes.HasPrefix(head, zstdMagic) {
		return true
	}
	return len(head) >= 4 && head[0]&0xf0 == 0x50 && head[1] == 0x2a && head[2] == 0x4d && head[3] == 0x18
}

// trimCompressionSuffix removes a trailing ".gz", ".zst" or ".zstd" from name,
// ignoring case. A name without such a suffix is returned unchanged.
func trimCompressionSuffix(name string) string {
	lower := strings.ToLower(name)
	for _, suffix := range compressionSuffixes {
		if strings.HasSuffix(lower, suffix) {
			return name[:len(name)-len(suffix)]
		}
	}
	return name
}

// logBody is the decompressed body of a downloaded log.
type logBody struct {
	r          *bufio.Reader
	compressed bool
	tar        bool
	close      func()
}

// openLogBody gets the compression of br from its magic bytes and peeks at
// the decompressed stream for a tar header. A body without gzip or zstd magic
// is an error when logName has a compression suffix. The caller must call
// close on the result.
func openLogBody(logName string, br *bufio.Reader) (*logBody, error) {
	head, err := br.Peek(len(zstdMagic))
	if err != nil && !errors.Is(err, io.EOF) {
		return nil, fmt.Errorf("reading log body: %w", err)
	}

	body := &logBody{close: func() {}}
	var stream io.Reader = br
	switch {
	case bytes.HasPrefix(head, gzipMagic):
		gr, err := gzip.NewReader(br)
		if err != nil {
			return nil, fmt.Errorf("creating gzip reader: %w", err)
		}
		stream, body.compressed, body.close = gr, true, func() { _ = gr.Close() }
	case isZstdStart(head):
		zr, err := zstd.NewReader(br)
		if err != nil {
			return nil, fmt.Errorf("creating zstd reader: %w", err)
		}
		stream, body.compressed, body.close = zr, true, zr.Close
	case trimCompressionSuffix(logName) != logName:
		return nil, fmt.Errorf("log %q has a compressed file name, but the server response is not gzip or zstd data", logName)
	}

	body.r = bufio.NewReader(stream)
	header, err := body.r.Peek(tarMagicOffset + len(tarMagic))
	if err != nil && !errors.Is(err, io.EOF) {
		body.close()
		return nil, fmt.Errorf("reading log body: %w", err)
	}
	body.tar = len(header) > tarMagicOffset && bytes.HasPrefix(header[tarMagicOffset:], tarMagic)
	return body, nil
}

func (b *logBody) action() string {
	switch {
	case b.tar:
		return "Extracting"
	case b.compressed:
		return "Decompressing"
	default:
		return "Writing"
	}
}

// extract writes the log under dest. A tar archive is extracted. Any other
// log is written as a single file named logName without its compression
// suffix.
func (b *logBody) extract(logName, dest string) error {
	if b.tar {
		return extractTar(b.r, dest)
	}
	return writeSingleFile(logName, trimCompressionSuffix(logName), b.r, dest)
}

// rejectHTMLResponse fails when the server sent an HTML page, for example the
// login page of an expired auth proxy, instead of a log file.
func rejectHTMLResponse(contentType string) error {
	mediaType, _, err := mime.ParseMediaType(contentType)
	if err == nil && mediaType == "text/html" {
		return fmt.Errorf("server returned an HTML page (Content-Type %q) instead of a log file, check your authentication", contentType)
	}
	return nil
}

// rejectErrorEnvelope fails when br holds an Argus error envelope. Argus sends
// API errors, for example an unknown log name, as HTTP 200 JSON. br is not
// consumed.
func rejectErrorEnvelope(contentType string, br *bufio.Reader) error {
	mediaType, _, err := mime.ParseMediaType(contentType)
	if err != nil || mediaType != "application/json" {
		return nil
	}
	head, err := br.Peek(maxErrorEnvelopeSize)
	if err != nil && !errors.Is(err, io.EOF) && !errors.Is(err, bufio.ErrBufferFull) {
		return fmt.Errorf("reading log body: %w", err)
	}
	var envelope models.APIResponse[json.RawMessage]
	if json.Unmarshal(head, &envelope) != nil || envelope.Status != "error" {
		return nil
	}
	body, err := envelope.DecodeError()
	if err != nil {
		return fmt.Errorf("server returned an error envelope that cannot be decoded: %w", err)
	}
	return &api.APIError{Body: body}
}

// ---------------------------------------------------------------------------
// Parent command: run logs
// ---------------------------------------------------------------------------

var logsCmd = &cobra.Command{
	Use:   "logs",
	Short: "Commands for log file operations",
	Long:  `List and download log files attached to a test run.`,
}

// ---------------------------------------------------------------------------
// Subcommand: run logs list
// ---------------------------------------------------------------------------

var logsListCmd = &cobra.Command{
	Use:   "list",
	Short: "List log files for a test run",
	Long:  `Fetch the names of all log files attached to a test run.`,
	RunE: func(cmd *cobra.Command, _ []string) error {
		cmd.SilenceUsage = true
		ctx := cmd.Context()
		client := APIClientFrom(ctx)
		out := OutputterFrom(ctx)
		log := logging.For(LoggerFrom(ctx), "run-logs-list")

		runID, _ := cmd.Flags().GetString("run-id")

		log.Debug().Str("run_id", runID).Msg("listing log files for run")

		runType, err := ResolveRunType(ctx, client, runID)
		if err != nil {
			log.Error().Err(err).Str("run_id", runID).Msg("failed to resolve run type")
			return err
		}

		log.Debug().Str("run_id", runID).Str("run_type", runType).Msg("run type resolved")

		handler, ok := RunTypeHandlers[runType]
		if !ok {
			err := fmt.Errorf("unknown run type %q, valid types: %s", runType, ValidRunTypes())
			log.Error().Err(err).Str("run_type", runType).Msg("unsupported run type")
			return err
		}

		route := fmt.Sprintf(api.TestRunGet, runType, runID)
		log.Debug().Str("run_id", runID).Str("route", route).Msg("fetching run to list logs")
		req, err := client.NewRequest(ctx, "GET", route, nil)
		if err != nil {
			log.Error().Err(err).Str("run_id", runID).Str("route", route).Msg("failed to build request")
			return err
		}

		run, err := handler(client, req)
		if err != nil {
			log.Error().Err(err).Str("run_id", runID).Str("run_type", runType).Msg("failed to fetch run")
			return err
		}

		entries, err := runLogEntries(run)
		if err != nil {
			log.Error().Err(err).Str("run_id", runID).Msg("failed to extract log entries from run")
			return err
		}

		log.Info().Str("run_id", runID).Int("log_count", len(entries)).Msg("log files listed successfully")
		return out.Write(models.NewTabularSlice(entries))
	},
}

// ---------------------------------------------------------------------------
// Subcommand: run logs download
// ---------------------------------------------------------------------------

var logsDownloadCmd = &cobra.Command{
	Use:   "download <log-name>",
	Short: "Download and extract a log file for a test run",
	Long: `Fetch a log file for a test run from Argus and write its contents to
the destination directory. The format comes from the file content, not the
name. A gzip or zstd body is decompressed. A tar archive is extracted. Any
other log (e.g. a ".log.zst" chunk) is written out as a single file, with the
".gz", ".zst" or ".zstd" suffix removed from its name. A body with such a
suffix that is not gzip or zstd data is an error.

The log-name argument must match a name shown by "argus run logs list".
If --dest is omitted the files are extracted into the current working directory.`,
	Args: cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		cmd.SilenceUsage = true
		ctx := cmd.Context()
		client := APIClientFrom(ctx)
		log := logging.For(LoggerFrom(ctx), "run-logs-download")

		logName := args[0]
		runID, _ := cmd.Flags().GetString("run-id")
		dest, _ := cmd.Flags().GetString("dest")

		if dest == "" {
			var err error
			dest, err = os.Getwd()
			if err != nil {
				log.Error().Err(err).Msg("failed to get current working directory")
				return fmt.Errorf("getting current directory: %w", err)
			}
		}

		log.Debug().Str("run_id", runID).Str("log_name", logName).Str("dest", dest).Msg("downloading log file")

		pluginName, err := ResolveRunType(ctx, client, runID)
		if err != nil {
			log.Error().Err(err).Str("run_id", runID).Msg("failed to resolve run type")
			return err
		}

		log.Debug().Str("run_id", runID).Str("plugin", pluginName).Msg("run type resolved for download")

		route := fmt.Sprintf(api.TestRunLogDownload, pluginName, runID, logName)
		log.Debug().Str("run_id", runID).Str("log_name", logName).Str("route", route).Msg("requesting log download")
		req, err := client.NewRequest(ctx, "GET", route, nil)
		if err != nil {
			log.Error().Err(err).Str("run_id", runID).Str("route", route).Msg("failed to build download request")
			return err
		}

		resp, err := client.DoStream(req)
		if err != nil {
			log.Error().Err(err).Str("run_id", runID).Str("log_name", logName).Msg("log download request failed")
			return err
		}
		defer func() { _ = resp.Body.Close() }()

		if resp.StatusCode < 200 || resp.StatusCode >= 300 {
			err := fmt.Errorf("server returned %d: %s", resp.StatusCode, http.StatusText(resp.StatusCode))
			log.Error().Err(err).
				Str("run_id", runID).Str("log_name", logName).
				Int("status_code", resp.StatusCode).
				Msg("unexpected HTTP status from log download")
			return err
		}

		if err := rejectHTMLResponse(resp.Header.Get("Content-Type")); err != nil {
			log.Error().Err(err).Str("run_id", runID).Str("log_name", logName).Msg("unexpected content type from log download")
			return err
		}

		body := bufio.NewReaderSize(resp.Body, maxErrorEnvelopeSize)
		if err := rejectErrorEnvelope(resp.Header.Get("Content-Type"), body); err != nil {
			log.Error().Err(err).Str("run_id", runID).Str("log_name", logName).Msg("server returned an error instead of the log")
			return err
		}

		logBody, err := openLogBody(logName, body)
		if err != nil {
			log.Error().Err(err).Str("run_id", runID).Str("log_name", logName).Msg("failed to read log body")
			return err
		}
		defer logBody.close()

		log.Debug().Str("run_id", runID).Str("log_name", logName).Str("dest", dest).Msg("extracting log archive")

		_, _ = fmt.Fprintf(cmd.OutOrStdout(), "%s %s to %s\n", logBody.action(), logName, dest)
		if extractErr := logBody.extract(logName, dest); extractErr != nil {
			log.Error().Err(extractErr).Str("run_id", runID).Str("log_name", logName).Str("dest", dest).Msg("failed to extract log archive")
			return extractErr
		}

		log.Info().Str("run_id", runID).Str("log_name", logName).Str("dest", dest).Msg("log downloaded and extracted successfully")
		_, _ = fmt.Fprintln(cmd.OutOrStdout(), "Done.")
		return nil
	},
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

// runLogEntries extracts log entries from a typed run object.
// SCT and DriverMatrix store logs as [][]string ([name, url] pairs);
// Generic and Sirenada store them as map[string]string (name → url).
func runLogEntries(run any) ([]models.LogEntry, error) {
	switch r := run.(type) {
	case models.SCTTestRun:
		return logEntriesFromPairs(r.Logs), nil
	case models.DriverTestRun:
		return logEntriesFromPairs(r.Logs), nil
	case models.GenericRun:
		return logEntriesFromMap(r.Logs), nil
	case models.SirenadaRun:
		return logEntriesFromMap(r.Logs), nil
	default:
		return nil, fmt.Errorf("unsupported run type %T for log listing", run)
	}
}

func logEntriesFromPairs(pairs [][]string) []models.LogEntry {
	entries := make([]models.LogEntry, 0, len(pairs))
	for _, p := range pairs {
		if len(p) < 2 {
			continue
		}
		entries = append(entries, models.LogEntry{Name: p[0], URL: p[1]})
	}
	return entries
}

func logEntriesFromMap(m map[string]string) []models.LogEntry {
	names := make([]string, 0, len(m))
	for name := range m {
		names = append(names, name)
	}
	sort.Strings(names)

	entries := make([]models.LogEntry, 0, len(m))
	for _, name := range names {
		entries = append(entries, models.LogEntry{Name: name, URL: m[name]})
	}
	return entries
}

// writeExtractedFile opens target for writing, copies src into it, and closes
// the file — propagating both copy and close errors.
func writeExtractedFile(target string, mode int64, src io.Reader) error {
	f, err := os.OpenFile(target, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, os.FileMode(mode)&0777)
	if err != nil {
		return fmt.Errorf("creating file %q: %w", target, err)
	}
	if _, err := io.Copy(f, src); err != nil {
		_ = f.Close()
		return fmt.Errorf("writing file %q: %w", target, err)
	}
	if err := f.Close(); err != nil {
		return fmt.Errorf("closing file %q: %w", target, err)
	}
	return nil
}

// extractTarZst decompresses a zstandard-compressed tar archive from r and
// writes its contents under dest. Path traversal entries are rejected.
func extractTarZst(r io.Reader, dest string) error {
	zr, err := zstd.NewReader(r)
	if err != nil {
		return fmt.Errorf("creating zstd reader: %w", err)
	}
	defer zr.Close()

	return extractTar(zr, dest)
}

// extractTar writes the entries of the decompressed tar stream r under dest.
// The tar reader stops at the end-of-archive marker, so extractTar then reads
// r to the end to make the decompressor verify its checksum. On error, it
// removes the files that it wrote. Path traversal entries are rejected.
func extractTar(r io.Reader, dest string) (err error) {
	var written []string
	defer func() {
		if err != nil {
			for _, path := range written {
				_ = os.Remove(path)
			}
		}
	}()

	tr := tar.NewReader(r)
	for {
		hdr, err := tr.Next()
		if err == io.EOF {
			break
		}
		if err != nil {
			return fmt.Errorf("reading tar entry: %w", err)
		}

		// Reject absolute paths and any entry that would escape dest.
		cleanName := filepath.Clean(hdr.Name)
		if !filepath.IsLocal(cleanName) {
			return fmt.Errorf("tar entry %q has an unsafe path", hdr.Name)
		}
		target := filepath.Join(dest, cleanName)

		switch hdr.Typeflag {
		case tar.TypeDir:
			if err := os.MkdirAll(target, 0755); err != nil {
				return fmt.Errorf("creating directory %q: %w", target, err)
			}
		case tar.TypeReg:
			if err := os.MkdirAll(filepath.Dir(target), 0755); err != nil {
				return fmt.Errorf("creating parent directory for %q: %w", target, err)
			}
			written = append(written, target)
			if err := writeExtractedFile(target, hdr.Mode, tr); err != nil {
				return err
			}
		}
	}
	if _, err := io.Copy(io.Discard, r); err != nil {
		return fmt.Errorf("verifying compressed stream: %w", err)
	}
	return nil
}

// writeSingleFile writes src to outName under dest. logName is the name the
// user asked for and is used in error messages.
func writeSingleFile(logName, outName string, src io.Reader, dest string) error {
	cleanName := filepath.Clean(outName)
	if cleanName == "." {
		return fmt.Errorf("log name %q is invalid", logName)
	}
	if !filepath.IsLocal(cleanName) {
		return fmt.Errorf("log name %q has an unsafe path", logName)
	}
	target := filepath.Join(dest, cleanName)

	if err := os.MkdirAll(filepath.Dir(target), 0755); err != nil {
		return fmt.Errorf("creating parent directory for %q: %w", target, err)
	}
	return writeExtractedFile(target, 0644, src)
}

// ---------------------------------------------------------------------------
// Registration
// ---------------------------------------------------------------------------

func init() {
	// logs list
	logsListCmd.Flags().String("run-id", "", "Run UUID (required)")
	_ = logsListCmd.MarkFlagRequired("run-id")

	// logs download
	logsDownloadCmd.Flags().String("run-id", "", "Run UUID (required)")
	logsDownloadCmd.Flags().String("dest", "", "Destination directory (default: current working directory)")
	_ = logsDownloadCmd.MarkFlagRequired("run-id")

	logsCmd.AddCommand(logsListCmd, logsDownloadCmd)
	runCmd.AddCommand(logsCmd)
}
