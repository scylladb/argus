package cmd

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"slices"
	"strings"
	"time"

	"github.com/scylladb/argus/cli/internal/api"
	"github.com/scylladb/argus/cli/internal/cache"
	"github.com/scylladb/argus/cli/internal/config"
	"github.com/scylladb/argus/cli/internal/logging"
	"github.com/scylladb/argus/cli/internal/models"
	"github.com/spf13/cobra"
)

const (
	promContainerPrefix = "argus-prom-"
	promMaxTTL          = 1 * time.Hour
	promImage           = "prom/prometheus:latest"
)

const promConfig = `global:
  scrape_interval: 15s
  evaluation_interval: 15s
`

// ---------------------------------------------------------------------------
// Parent command: run prometheus
// ---------------------------------------------------------------------------

var prometheusCmd = &cobra.Command{
	Use:   "prometheus",
	Short: "Manage ephemeral Prometheus containers for test run metrics",
	Long: `Download monitoring data from a test run and launch a local Prometheus
instance to explore metrics. Containers are automatically pruned after 1 hour.`,
}

// ---------------------------------------------------------------------------
// Subcommand: run prometheus list
// ---------------------------------------------------------------------------

var promListCmd = &cobra.Command{
	Use:   "list",
	Short: "List running Prometheus containers",
	RunE: func(cmd *cobra.Command, _ []string) error {
		cmd.SilenceUsage = true
		if err := checkDocker(); err != nil {
			return err
		}

		out := OutputterFrom(cmd.Context())

		names, err := promContainerNames(cmd.Context())
		if err != nil {
			return err
		}
		if len(names) == 0 {
			_, _ = fmt.Fprintln(cmd.OutOrStdout(), "No argus prometheus containers found.")
			return nil
		}

		entries := make([]PromContainerEntry, 0, len(names))
		for _, name := range names {
			port, _ := getContainerPort(cmd.Context(), name)
			runID := readRunIDFromDataDir(name)
			entries = append(entries, PromContainerEntry{
				Container: name,
				RunID:     runID,
				Port:      port,
			})
		}

		return out.Write(models.NewTabularSlice(entries))
	},
}

// ---------------------------------------------------------------------------
// Subcommand: run prometheus start
// ---------------------------------------------------------------------------

var promStartCmd = &cobra.Command{
	Use:   "start",
	Short: "Download metrics and start a Prometheus container for a test run",
	RunE: func(cmd *cobra.Command, _ []string) error {
		cmd.SilenceUsage = true
		ctx := cmd.Context()
		client := APIClientFrom(ctx)
		log := logging.For(LoggerFrom(ctx), "prometheus-start")

		runID, _ := cmd.Flags().GetString("run-id")
		root := promDataRoot()
		dataDir, err := promRunDir(root, runID)
		if err != nil {
			return err
		}

		if err := checkDocker(); err != nil {
			return err
		}

		// Prune stale containers and the data they leave behind
		pruneOldContainers(ctx)
		removeOrphanDataDirs(cmd.ErrOrStderr(), root, func() ([]string, error) {
			return promContainerNames(ctx)
		})

		// Check if container already exists for this run
		containerName := promContainerName(runID)
		if containerExists(ctx, containerName) {
			port, _ := getContainerPort(ctx, containerName)
			_, _ = fmt.Fprintf(cmd.OutOrStdout(), "Prometheus running at http://localhost:%s\n", port)
			return nil
		}

		if err := claimRunDir(dataDir); err != nil {
			return err
		}
		started := false
		defer func() {
			if !started {
				removePromData(cmd.ErrOrStderr(), dataDir)
			}
		}()

		// 1. Check cache for previously downloaded archive
		appCache := CacheFrom(ctx)
		cacheKey := cache.PrometheusLogKey(runID)
		archivePath := cachedArchivePath(appCache, cacheKey)
		downloaded := archivePath == ""

		if downloaded {
			// 2. List logs and find the monitor-set archive
			log.Debug().Str("run_id", runID).Msg("listing logs to find monitor-set archive")
			monitorLog, err := findMonitorSetLog(ctx, client, runID)
			if err != nil {
				return fmt.Errorf("finding monitor-set log: %w", err)
			}
			log.Info().Str("log_name", monitorLog).Msg("found monitor-set archive")
			archivePath, err = childPath(dataDir, monitorLog)
			if err != nil {
				return fmt.Errorf("monitor-set log name: %w", err)
			}

			// 3. Download the archive
			pluginName, err := ResolveRunType(ctx, client, runID)
			if err != nil {
				return fmt.Errorf("resolving run type: %w", err)
			}

			route := fmt.Sprintf(api.TestRunLogDownload, pluginName, runID, monitorLog)
			req, err := client.NewRequest(ctx, "GET", route, nil)
			if err != nil {
				return fmt.Errorf("building download request: %w", err)
			}

			resp, err := client.DoStream(req)
			if err != nil {
				return fmt.Errorf("downloading log: %w", err)
			}
			defer func() { _ = resp.Body.Close() }()

			if resp.StatusCode < 200 || resp.StatusCode >= 300 {
				return fmt.Errorf("server returned %d: %s", resp.StatusCode, http.StatusText(resp.StatusCode))
			}

			archiveFile, err := os.Create(archivePath)
			if err != nil {
				return fmt.Errorf("creating archive file: %w", err)
			}
			if _, err := io.Copy(archiveFile, resp.Body); err != nil {
				_ = archiveFile.Close()
				return fmt.Errorf("saving archive: %w", err)
			}
			if err := archiveFile.Close(); err != nil {
				return fmt.Errorf("saving archive: %w", err)
			}
		} else {
			_ = cache.Set(appCache, cacheKey, filepath.Base(archivePath), "", cache.TTLPrometheusLog)
		}

		// 4. Extract outer archive to temp dir
		tempDir, err := os.MkdirTemp("", "argus-prom-download-*")
		if err != nil {
			return fmt.Errorf("creating temp dir: %w", err)
		}
		defer func() { _ = os.RemoveAll(tempDir) }()

		if err := extractTarZstFile(archivePath, tempDir); err != nil {
			return fmt.Errorf("extracting outer archive: %w", err)
		}

		// Keep the verified archive in the cache for the next start
		if downloaded {
			if err := cacheArchive(appCache, cacheKey, archivePath); err != nil {
				_, _ = fmt.Fprintf(cmd.ErrOrStderr(), "warning: could not cache the monitor-set archive: %v\n", err)
			}
		}

		// 5. Find prometheus_data_*.tar.zst in extracted content
		promArchive, err := findPromDataArchive(tempDir)
		if err != nil {
			return err
		}
		log.Info().Str("path", promArchive).Msg("found prometheus data archive")

		// 6. Extract TSDB data to the run's data directory
		if err := extractTarZstFile(promArchive, dataDir); err != nil {
			return fmt.Errorf("extracting prometheus data: %w", err)
		}

		// Prometheus snapshots nest TSDB blocks inside a timestamped directory
		// (e.g. 20260426T074320Z-xxxx/). Prometheus expects blocks directly
		// under --storage.tsdb.path, so flatten the snapshot wrapper.
		if err := flattenSnapshotDir(dataDir); err != nil {
			return fmt.Errorf("flattening snapshot directory: %w", err)
		}

		// 7. Write minimal prometheus.yml
		configPath := filepath.Join(dataDir, "prometheus.yml")
		if err := writePromConfig(configPath, promConfig); err != nil {
			return err
		}

		// 8. Start Docker container
		dockerArgs := promDockerRunArgs(containerName, dataDir, configPath, os.Getuid(), os.Getgid())
		output, err := exec.CommandContext(ctx, "docker", dockerArgs...).CombinedOutput()
		if err != nil {
			return fmt.Errorf("docker run failed: %w\n%s", err, string(output))
		}
		started = true

		// Store run ID metadata for list command
		if err := os.WriteFile(filepath.Join(dataDir, "run_id"), []byte(runID), 0o644); err != nil {
			_, _ = fmt.Fprintf(cmd.ErrOrStderr(), "warning: could not record the run ID: %v\n", err)
		}

		// Get assigned port
		port, err := getContainerPort(ctx, containerName)
		if err != nil {
			return fmt.Errorf("getting container port: %w", err)
		}

		_, _ = fmt.Fprintf(cmd.OutOrStdout(), "Prometheus running at http://localhost:%s\n", port)
		return nil
	},
}

// ---------------------------------------------------------------------------
// Subcommand: run prometheus stop
// ---------------------------------------------------------------------------

var promStopCmd = &cobra.Command{
	Use:   "stop",
	Short: "Stop and remove Prometheus container(s)",
	RunE: func(cmd *cobra.Command, _ []string) error {
		cmd.SilenceUsage = true
		ctx := cmd.Context()

		if err := checkDocker(); err != nil {
			return err
		}

		all, _ := cmd.Flags().GetBool("all")
		runID, _ := cmd.Flags().GetString("run-id")

		if !all && runID == "" {
			return fmt.Errorf("either --run-id or --all is required")
		}

		if all {
			return stopAllContainers(ctx, cmd)
		}

		dir, err := promRunDir(promDataRoot(), runID)
		if err != nil {
			return err
		}

		containerName := promContainerName(runID)
		output, err := exec.CommandContext(ctx, "docker", "rm", "-f", containerName).CombinedOutput()
		if err != nil {
			return fmt.Errorf("stopping container %s: %w\n%s", containerName, err, string(output))
		}
		_, _ = fmt.Fprintf(cmd.OutOrStdout(), "Stopped and removed %s\n", containerName)

		removePromData(cmd.ErrOrStderr(), dir)
		return nil
	},
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

// PromContainerEntry represents a running Prometheus container for tabular output.
type PromContainerEntry struct {
	Container string `json:"container"`
	RunID     string `json:"run_id"`
	Port      string `json:"port"`
}

func fileExists(path string) bool {
	_, err := os.Stat(path)
	return err == nil
}

// removePromData removes a run's data directory, or the whole data root, and
// warns on w about anything left behind.
func removePromData(w io.Writer, dir string) {
	if err := os.RemoveAll(dir); err != nil {
		_, _ = fmt.Fprintf(w, "warning: could not remove prometheus data: %v\n", err)
	}
}

// removeOrphanDataDirs removes the data directories under root whose container
// is gone. It lists the containers after it scans the directories: run_id is
// written once the container exists, so a run_id the scan saw has its
// container in the list.
func removeOrphanDataDirs(w io.Writer, root string, listContainers func() ([]string, error)) {
	entries, err := os.ReadDir(root)
	if err != nil {
		if !errors.Is(err, os.ErrNotExist) {
			_, _ = fmt.Fprintf(w, "warning: could not list prometheus data: %v\n", err)
		}
		return
	}
	var candidates []string
	for _, e := range entries {
		if !e.IsDir() {
			continue
		}
		// A directory without run_id belongs to a start that has not created
		// its container yet, unless that start is long gone.
		if !fileExists(filepath.Join(root, e.Name(), "run_id")) {
			info, err := e.Info()
			if err != nil || time.Since(info.ModTime()) < promMaxTTL {
				continue
			}
		}
		candidates = append(candidates, e.Name())
	}
	if len(candidates) == 0 {
		return
	}
	containers, err := listContainers()
	if err != nil {
		_, _ = fmt.Fprintf(w, "warning: skipping prometheus data cleanup: %v\n", err)
		return
	}
	for _, name := range candidates {
		if !slices.Contains(containers, promContainerName(name)) {
			removePromData(w, filepath.Join(root, name))
		}
	}
}

// claimRunDir creates a run's data directory and fails when it exists: another
// start of the run holds it, or the sweep could not remove what it holds.
func claimRunDir(dir string) error {
	if err := os.MkdirAll(filepath.Dir(dir), 0o755); err != nil {
		return fmt.Errorf("creating data directory: %w", err)
	}
	if err := os.Mkdir(dir, 0o755); errors.Is(err, fs.ErrExist) {
		return fmt.Errorf("%s already exists: another start of this run may be in progress, "+
			"otherwise remove it (files an older argus left as nobody need sudo rm -rf)", dir)
	} else if err != nil {
		return fmt.Errorf("creating data directory: %w", err)
	}
	return nil
}

// cachedArchivePath returns the monitor-set archive held by the cache entry
// at key, or "" when the entry or its archive is missing.
func cachedArchivePath(c *cache.Cache, key string) string {
	name, _, err := cache.Get[string](c, key)
	if err != nil {
		return ""
	}
	dir, err := c.EntryDir(key)
	if err != nil {
		return ""
	}
	archive, err := childPath(dir, name)
	if err != nil || !fileExists(archive) {
		return ""
	}
	return archive
}

// cacheArchive moves a downloaded archive into the cache entry at key, so it
// expires and clears with the entry. It removes the archive when the cache is
// disabled.
func cacheArchive(c *cache.Cache, key, archivePath string) error {
	dir, err := c.EntryDir(key)
	if errors.Is(err, cache.ErrDisabled) {
		return os.Remove(archivePath)
	}
	if err != nil {
		return err
	}
	name := filepath.Base(archivePath)
	if err := cache.Set(c, key, name, "", cache.TTLPrometheusLog); err != nil {
		return err
	}
	return os.Rename(archivePath, filepath.Join(dir, name))
}

func extractTarZstFile(path, dest string) error {
	f, err := os.Open(path)
	if err != nil {
		return err
	}
	defer func() { _ = f.Close() }()
	return extractTarZst(f, dest)
}

func checkDocker() error {
	if _, err := exec.LookPath("docker"); err != nil {
		return fmt.Errorf("docker not found in PATH; please install Docker to use this command")
	}
	return nil
}

func promContainerName(runID string) string {
	// Use first 8 chars of run ID for brevity
	short := runID
	if len(short) > 8 {
		short = short[:8]
	}
	return promContainerPrefix + short
}

// childPath returns root/name when name is a single path element, so the path
// cannot leave root.
func childPath(root, name string) (string, error) {
	p := filepath.Join(root, name)
	if !filepath.IsLocal(name) || filepath.Dir(p) != root || filepath.Base(p) != name {
		return "", fmt.Errorf("%q is not a single path element", name)
	}
	return p, nil
}

// promDataRoot is the directory that holds one data directory per run.
func promDataRoot() string {
	return filepath.Join(config.CacheDir(), "prometheus")
}

// promRunDir returns the data directory of runID under root.
func promRunDir(root, runID string) (string, error) {
	dir, err := childPath(root, runID)
	if err != nil {
		return "", fmt.Errorf("invalid run ID: %w", err)
	}
	return dir, nil
}

func readRunIDFromDataDir(containerName string) string {
	// Container name is "argus-prom-XXXXXXXX"; enumerate data dirs to find matching run_id
	promBase := promDataRoot()
	entries, err := os.ReadDir(promBase)
	if err != nil {
		return ""
	}
	for _, e := range entries {
		if !e.IsDir() {
			continue
		}
		runIDFile := filepath.Join(promBase, e.Name(), "run_id")
		data, err := os.ReadFile(runIDFile)
		if err != nil {
			continue
		}
		runID := strings.TrimSpace(string(data))
		if promContainerName(runID) == containerName {
			return runID
		}
	}
	return ""
}

// promContainerNames lists the names of all argus prometheus containers,
// running or not.
func promContainerNames(ctx context.Context) ([]string, error) {
	raw, err := exec.CommandContext(ctx, "docker", "ps", "-a",
		"--filter", "name="+promContainerPrefix,
		"--format", "{{.Names}}",
	).Output()
	if err != nil {
		return nil, fmt.Errorf("docker ps: %w", err)
	}
	return strings.Fields(string(raw)), nil
}

func containerExists(ctx context.Context, name string) bool {
	out, err := exec.CommandContext(ctx, "docker", "ps", "-a", "-q", "--filter", "name=^/"+name+"$").Output()
	return err == nil && len(strings.TrimSpace(string(out))) > 0
}

func getContainerPort(ctx context.Context, name string) (string, error) {
	out, err := exec.CommandContext(ctx, "docker", "port", name, "9090/tcp").Output()
	if err != nil {
		return "", err
	}
	// Output format: "0.0.0.0:XXXXX\n" or "[::]:XXXXX\n"
	line := strings.TrimSpace(string(out))
	parts := strings.Split(line, ":")
	if len(parts) < 2 {
		return line, nil
	}
	return parts[len(parts)-1], nil
}

func stopAllContainers(ctx context.Context, cmd *cobra.Command) error {
	out, err := exec.CommandContext(ctx, "docker", "ps", "-a", "-q", "--filter", "name="+promContainerPrefix).Output()
	if err != nil {
		return fmt.Errorf("listing containers: %w", err)
	}

	ids := strings.Fields(string(out))
	if len(ids) == 0 {
		_, _ = fmt.Fprintln(cmd.OutOrStdout(), "No argus prometheus containers found.")
	} else {
		args := append([]string{"rm", "-f"}, ids...)
		output, err := exec.CommandContext(ctx, "docker", args...).CombinedOutput()
		if err != nil {
			return fmt.Errorf("removing containers: %w\n%s", err, string(output))
		}
		_, _ = fmt.Fprintln(cmd.OutOrStdout(), "All argus prometheus containers stopped and removed.")
	}

	removePromData(cmd.ErrOrStderr(), promDataRoot())
	return nil
}

func pruneOldContainers(ctx context.Context) {
	out, err := exec.CommandContext(ctx, "docker", "ps", "-a",
		"--filter", "name="+promContainerPrefix,
		"--format", "json",
	).Output()
	if err != nil || len(out) == 0 {
		return
	}

	type dockerPsEntry struct {
		Names     string `json:"Names"`
		CreatedAt string `json:"CreatedAt"`
	}

	scanner := bufio.NewScanner(strings.NewReader(string(out)))
	for scanner.Scan() {
		var entry dockerPsEntry
		if err := json.Unmarshal(scanner.Bytes(), &entry); err != nil {
			continue
		}
		// Docker CreatedAt format: "2026-05-25 10:30:00 +0000 UTC"
		created, err := time.Parse("2006-01-02 15:04:05 -0700 MST", entry.CreatedAt)
		if err != nil {
			continue
		}
		if time.Since(created) > promMaxTTL {
			_ = exec.CommandContext(ctx, "docker", "rm", "-f", entry.Names).Run()
		}
	}
}

func findMonitorSetLog(ctx context.Context, client *api.Client, runID string) (string, error) {
	runType, err := ResolveRunType(ctx, client, runID)
	if err != nil {
		return "", err
	}

	handler, ok := RunTypeHandlers[runType]
	if !ok {
		return "", fmt.Errorf("unknown run type %q", runType)
	}

	route := fmt.Sprintf(api.TestRunGet, runType, runID)
	req, err := client.NewRequest(ctx, "GET", route, nil)
	if err != nil {
		return "", err
	}

	run, err := handler(client, req)
	if err != nil {
		return "", err
	}

	entries, err := runLogEntries(run)
	if err != nil {
		return "", err
	}

	for _, entry := range entries {
		if strings.HasPrefix(entry.Name, "monitor-set") || strings.Contains(entry.Name, "monitor-set") {
			return entry.Name, nil
		}
	}

	return "", fmt.Errorf("no monitor-set archive found in logs for run %s", runID)
}

func findPromDataArchive(dir string) (string, error) {
	var found string
	err := filepath.Walk(dir, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		if !info.IsDir() && strings.HasPrefix(info.Name(), "prometheus_data_") && strings.HasSuffix(info.Name(), ".tar.zst") {
			found = path
			return filepath.SkipAll
		}
		return nil
	})
	if err != nil && err != filepath.SkipAll {
		return "", fmt.Errorf("searching for prometheus data: %w", err)
	}
	if found == "" {
		return "", fmt.Errorf("no prometheus_data_*.tar.zst found in extracted logs")
	}
	return found, nil
}

// flattenSnapshotDir detects if TSDB blocks are nested inside a snapshot
// subdirectory and moves them up to the data directory root. Prometheus
// snapshots wrap blocks in a timestamped directory (e.g. 20260426T074320Z-...)
// but Prometheus expects blocks directly under its --storage.tsdb.path.
func flattenSnapshotDir(dataDir string) error {
	entries, err := os.ReadDir(dataDir)
	if err != nil {
		return fmt.Errorf("reading data dir: %w", err)
	}

	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}

		candidateDir := filepath.Join(dataDir, entry.Name())

		// Check if this directory contains TSDB blocks (subdirs with meta.json)
		subEntries, err := os.ReadDir(candidateDir)
		if err != nil {
			continue
		}

		hasBlocks := false
		for _, sub := range subEntries {
			if sub.IsDir() {
				metaPath := filepath.Join(candidateDir, sub.Name(), "meta.json")
				if _, err := os.Stat(metaPath); err == nil {
					hasBlocks = true
					break
				}
			}
		}

		if !hasBlocks {
			continue
		}

		// Move all entries from the snapshot directory up to dataDir. TSDB
		// blocks are identity-addressed by ULID and namespaced per run, so a
		// pre-existing destination (from an earlier flatten of this same
		// run, or a leftover from an interrupted one) is safe to replace.
		for _, sub := range subEntries {
			src := filepath.Join(candidateDir, sub.Name())
			dst := filepath.Join(dataDir, sub.Name())
			if _, err := os.Stat(dst); err == nil {
				if err := os.RemoveAll(dst); err != nil {
					return fmt.Errorf("removing existing %s before re-extraction: %w", dst, err)
				}
			} else if !errors.Is(err, os.ErrNotExist) {
				return fmt.Errorf("checking existing %s before re-extraction: %w", dst, err)
			}
			if err := os.Rename(src, dst); err != nil {
				return fmt.Errorf("moving %s to %s: %w", src, dst, err)
			}
		}

		// Remove the now-empty snapshot directory
		_ = os.Remove(candidateDir)
		return nil // only one snapshot directory expected
	}

	return nil
}

func writePromConfig(configPath, contents string) error {
	if err := os.WriteFile(configPath, []byte(contents), 0o644); err != nil {
		return fmt.Errorf("writing prometheus config: %w", err)
	}
	return nil
}

// promDockerRunArgs returns the docker run arguments that start Prometheus as
// the calling user on the run's data directory.
func promDockerRunArgs(containerName, dataDir, configPath string, uid, gid int) []string {
	args := []string{"run", "-d", "--name", containerName}
	// os.Getuid reports -1 on Windows, where the container keeps the image's user.
	if uid != -1 {
		args = append(args, "--user", fmt.Sprintf("%d:%d", uid, gid))
	}
	// z relabels the mounts so an SELinux-enforcing host lets the container read them.
	return append(args,
		"-v", dataDir+":/prometheus:z",
		"-v", configPath+":/etc/prometheus/prometheus.yml:ro,z",
		"-p", "0:9090",
		promImage,
		"--config.file=/etc/prometheus/prometheus.yml",
		"--storage.tsdb.path=/prometheus",
		"--storage.tsdb.retention.time=90d",
		"--storage.tsdb.no-lockfile",
		"--web.listen-address=:9090",
	)
}

// ---------------------------------------------------------------------------
// Registration
// ---------------------------------------------------------------------------

func init() {
	// prometheus start
	promStartCmd.Flags().String("run-id", "", "Run UUID (required)")
	_ = promStartCmd.MarkFlagRequired("run-id")

	// prometheus stop
	promStopCmd.Flags().String("run-id", "", "Run UUID")
	promStopCmd.Flags().Bool("all", false, "Stop all argus prometheus containers")

	prometheusCmd.AddCommand(promListCmd, promStartCmd, promStopCmd)
	rootCmd.AddCommand(prometheusCmd)
}
