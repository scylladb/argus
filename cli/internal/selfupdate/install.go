package selfupdate

import (
	"archive/tar"
	"bufio"
	"compress/gzip"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
)

const binaryName = "argus"

// maxArchiveBytes bounds the download of one release archive and the binary in it.
var maxArchiveBytes int64 = 256 << 20

var (
	// ErrChecksum is returned when the checksum file has no line for the archive, or the
	// SHA-256 sum of the archive does not match it.
	ErrChecksum = errors.New("selfupdate: checksum")
	// ErrBinaryNotInArchive is returned when the archive holds no argus binary.
	ErrBinaryNotInArchive = errors.New("selfupdate: argus binary not found in the archive")
	// ErrDownload is returned when an asset cannot be downloaded.
	ErrDownload = errors.New("selfupdate: download")
	// ErrInstall is returned when the new binary cannot be written next to the old one.
	ErrInstall = errors.New("selfupdate: install")
	// ErrArchiveTooLarge is returned when the archive or its binary is larger than maxArchiveBytes.
	ErrArchiveTooLarge = errors.New("selfupdate: archive too large")
)

// ExecutablePath returns the path of the running binary, with its symlinks resolved.
func ExecutablePath() (string, error) {
	path, err := os.Executable()
	if err != nil {
		return "", fmt.Errorf("%w: %w", ErrInstall, err)
	}
	resolved, err := filepath.EvalSymlinks(path)
	if err != nil {
		return "", fmt.Errorf("%w: %w", ErrInstall, err)
	}
	return resolved, nil
}

func get(ctx context.Context, client *http.Client, url string) (io.ReadCloser, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, fmt.Errorf("%w: %w", ErrDownload, err)
	}
	resp, err := client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("%w: %w", ErrDownload, err)
	}
	if resp.StatusCode != http.StatusOK {
		_ = resp.Body.Close()
		return nil, fmt.Errorf("%w: status %d from %s", ErrDownload, resp.StatusCode, url)
	}
	return resp.Body, nil
}

// expectedSum reads the checksum file and returns the sum on the line of archiveName.
func expectedSum(ctx context.Context, client *http.Client, url, archiveName string) (string, error) {
	body, err := get(ctx, client, url)
	if err != nil {
		return "", err
	}
	defer func() { _ = body.Close() }()

	scanner := bufio.NewScanner(body)
	for scanner.Scan() {
		fields := strings.Fields(scanner.Text())
		// A leading "*" marks binary mode in the sha256sum format.
		if len(fields) == 2 && strings.TrimPrefix(fields[1], "*") == archiveName {
			return strings.ToLower(fields[0]), nil
		}
	}
	if err = scanner.Err(); err != nil {
		return "", fmt.Errorf("%w: %w", ErrDownload, err)
	}
	return "", fmt.Errorf("%w: no line for %s", ErrChecksum, archiveName)
}

// extractBinary writes the argus entry of the tar.gz stream to w.
func extractBinary(r io.Reader, w io.Writer) error {
	gz, err := gzip.NewReader(r)
	if err != nil {
		return fmt.Errorf("%w: %w", ErrDownload, err)
	}
	tr := tar.NewReader(gz)
	for {
		hdr, err := tr.Next()
		if errors.Is(err, io.EOF) {
			return ErrBinaryNotInArchive
		}
		if err != nil {
			return fmt.Errorf("%w: %w", ErrDownload, err)
		}
		if hdr.Typeflag == tar.TypeReg && filepath.Base(hdr.Name) == binaryName {
			if hdr.Size > maxArchiveBytes {
				return fmt.Errorf("%w: %s is %d bytes", ErrArchiveTooLarge, hdr.Name, hdr.Size)
			}
			if _, err = io.Copy(w, tr); err != nil {
				return fmt.Errorf("%w: %w", ErrInstall, err)
			}
			return nil
		}
	}
}

// Install downloads the archive of the release, checks its SHA-256 sum against the checksum
// file, and renames the argus binary from the archive over target. target keeps its file
// mode. On any error, target does not change and no temporary file stays behind.
func Install(ctx context.Context, client *http.Client, r Release, archiveName, target string) error {
	want, err := expectedSum(ctx, client, r.ChecksumURL, archiveName)
	if err != nil {
		return err
	}

	info, err := os.Stat(target)
	if err != nil {
		return fmt.Errorf("%w: %w", ErrInstall, err)
	}

	tmp, err := os.CreateTemp(filepath.Dir(target), ".argus-upgrade-*")
	if err != nil {
		return fmt.Errorf("%w: %w", ErrInstall, err)
	}
	tmpName := tmp.Name()
	installed := false
	defer func() {
		_ = tmp.Close()
		if !installed {
			_ = os.Remove(tmpName)
		}
	}()

	body, err := get(ctx, client, r.ArchiveURL)
	if err != nil {
		return err
	}
	defer func() { _ = body.Close() }()

	hash := sha256.New()
	limited := &io.LimitedReader{R: body, N: maxArchiveBytes + 1}
	stream := io.TeeReader(limited, hash)
	if err = extractBinary(stream, tmp); err != nil {
		if limited.N == 0 {
			return fmt.Errorf("%w: %s is larger than %d bytes", ErrArchiveTooLarge, archiveName, maxArchiveBytes)
		}
		return err
	}
	// Read the rest of the archive so the hash covers every byte.
	if _, err = io.Copy(io.Discard, stream); err != nil {
		return fmt.Errorf("%w: %w", ErrDownload, err)
	}
	if limited.N == 0 {
		return fmt.Errorf("%w: %s is larger than %d bytes", ErrArchiveTooLarge, archiveName, maxArchiveBytes)
	}
	if got := hex.EncodeToString(hash.Sum(nil)); got != want {
		return fmt.Errorf("%w: %s has sum %s, want %s", ErrChecksum, archiveName, got, want)
	}

	if err = tmp.Sync(); err != nil {
		return fmt.Errorf("%w: %w", ErrInstall, err)
	}
	if err = tmp.Close(); err != nil {
		return fmt.Errorf("%w: %w", ErrInstall, err)
	}
	if err = os.Chmod(tmpName, info.Mode().Perm()); err != nil {
		return fmt.Errorf("%w: %w", ErrInstall, err)
	}
	if err = os.Rename(tmpName, target); err != nil {
		return fmt.Errorf("%w: %w", ErrInstall, err)
	}
	installed = true
	return nil
}
