package cmd

import (
	"archive/tar"
	"fmt"
	"io"
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

// tarZstSuffixes are the known suffixes of zstd-compressed tar archives that
// extractTarZst can actually decode; any other log file (e.g. the bare
// zstd-compressed ".log.zst" SCT runner log chunks) is a single file that
// only needs decompressing. This is an exact-suffix match, not a substring
// match: extractTarZst hardcodes zstd decompression, so a name that merely
// contains ".tar." (e.g. a plain log named "foo.tar.old.log.zst") must not
// be routed here, and a genuinely different tar compression (".tar.gz")
// would need its own decoder in extractTarZst before it could be added below.
var tarZstSuffixes = [...]string{".tar.zst", ".tar.zstd"}

func isTarZstName(logName string) bool {
	for _, suffix := range tarZstSuffixes {
		if strings.HasSuffix(logName, suffix) {
			return true
		}
	}
	return false
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
the destination directory. ".tar.zst" archives are extracted; any other
log file (e.g. a bare ".log.zst" chunk) is decompressed and written out
as a single file.

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

		isTarArchive := isTarZstName(logName)

		log.Debug().Str("run_id", runID).Str("log_name", logName).Str("dest", dest).Bool("is_tar_archive", isTarArchive).Msg("extracting log archive")

		var extractErr error
		if isTarArchive {
			_, _ = fmt.Fprintf(cmd.OutOrStdout(), "Extracting %s to %s\n", logName, dest)
			extractErr = extractTarZst(resp.Body, dest)
		} else {
			_, _ = fmt.Fprintf(cmd.OutOrStdout(), "Decompressing %s to %s\n", logName, dest)
			extractErr = extractPlainZst(logName, resp.Body, dest)
		}
		if extractErr != nil {
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

	tr := tar.NewReader(zr)
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
			if err := writeExtractedFile(target, hdr.Mode, tr); err != nil {
				return err
			}
		}
	}
	return nil
}

// extractPlainZst decompresses a zstandard-compressed single log file from r
// and writes it under dest, using logName with its ".zst" suffix stripped as
// the output file name. Unsafe (non-local) names are rejected.
func extractPlainZst(logName string, r io.Reader, dest string) error {
	zr, err := zstd.NewReader(r)
	if err != nil {
		return fmt.Errorf("creating zstd reader: %w", err)
	}
	defer zr.Close()

	outName := strings.TrimSuffix(logName, ".zst")
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
	return writeExtractedFile(target, 0644, zr)
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
