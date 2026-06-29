package cmd

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	"github.com/scylladb/argus/cli/internal/api"
	"github.com/scylladb/argus/cli/internal/cache"
	"github.com/scylladb/argus/cli/internal/logging"
	"github.com/scylladb/argus/cli/internal/models"
	"github.com/spf13/cobra"
)

const (
	promContainerPrefix = "argus-prom-"
	promMaxTTL          = 1 * time.Hour
	promImage           = "prom/prometheus:latest"
)

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

		// Get container names
		raw, err := exec.CommandContext(cmd.Context(), "docker", "ps", "-a",
			"--filter", "name="+promContainerPrefix,
			"--format", "{{.Names}}",
		).Output()
		if err != nil {
			return fmt.Errorf("docker ps: %w", err)
		}

		names := strings.Fields(strings.TrimSpace(string(raw)))
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

		if err := checkDocker(); err != nil {
			return err
		}

		// Prune stale containers
		pruneOldContainers(ctx)

		// Check if container already exists for this run
		containerName := promContainerName(runID)
		if containerExists(ctx, containerName) {
			port, _ := getContainerPort(ctx, containerName)
			_, _ = fmt.Fprintf(cmd.OutOrStdout(), "Prometheus running at http://localhost:%s\n", port)
			return nil
		}

		// 1. Check cache for previously downloaded archive
		appCache := CacheFrom(ctx)
		cacheKey := cache.PrometheusLogKey(runID)
		dataDir, err := promDataDir(runID)
		if err != nil {
			return fmt.Errorf("creating data directory: %w", err)
		}

		cachedLogName, _, cacheErr := cache.Get[string](appCache, cacheKey)
		cachedArchive := filepath.Join(dataDir, cachedLogName)
		haveCached := cacheErr == nil && cachedLogName != "" && fileExists(cachedArchive)

		if !haveCached {
			// 2. List logs and find the monitor-set archive
			log.Debug().Str("run_id", runID).Msg("listing logs to find monitor-set archive")
			monitorLog, err := findMonitorSetLog(ctx, client, runID)
			if err != nil {
				return fmt.Errorf("finding monitor-set log: %w", err)
			}
			log.Info().Str("log_name", monitorLog).Msg("found monitor-set archive")
			cachedLogName = monitorLog
			cachedArchive = filepath.Join(dataDir, monitorLog)

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

			// Save archive to data dir for future reuse
			archiveFile, err := os.Create(cachedArchive)
			if err != nil {
				return fmt.Errorf("creating archive file: %w", err)
			}
			if _, err := io.Copy(archiveFile, resp.Body); err != nil {
				_ = archiveFile.Close()
				return fmt.Errorf("saving archive: %w", err)
			}
			_ = archiveFile.Close()
		}

		// 4. Extract outer archive to temp dir
		tempDir, err := os.MkdirTemp("", "argus-prom-download-*")
		if err != nil {
			return fmt.Errorf("creating temp dir: %w", err)
		}
		defer func() { _ = os.RemoveAll(tempDir) }()

		archiveReader, err := os.Open(cachedArchive)
		if err != nil {
			return fmt.Errorf("opening cached archive: %w", err)
		}
		defer func() { _ = archiveReader.Close() }()

		if err := extractTarZst(archiveReader, tempDir); err != nil {
			return fmt.Errorf("extracting outer archive: %w", err)
		}

		// 5. Find prometheus_data_*.tar.zst in extracted content
		promArchive, err := findPromDataArchive(tempDir)
		if err != nil {
			return err
		}
		log.Info().Str("path", promArchive).Msg("found prometheus data archive")

		// 6. Extract TSDB data to persistent directory
		promFile, err := os.Open(promArchive)
		if err != nil {
			return fmt.Errorf("opening prometheus archive: %w", err)
		}
		defer func() { _ = promFile.Close() }()

		if err := extractTarZst(promFile, dataDir); err != nil {
			return fmt.Errorf("extracting prometheus data: %w", err)
		}

		// Prometheus snapshots nest TSDB blocks inside a timestamped directory
		// (e.g. 20260426T074320Z-xxxx/). Prometheus expects blocks directly
		// under --storage.tsdb.path, so flatten the snapshot wrapper.
		if err := flattenSnapshotDir(dataDir); err != nil {
			return fmt.Errorf("flattening snapshot directory: %w", err)
		}

		// Make data dir writable by the prometheus container user (uid 65534)
		_ = chmodRecursive(dataDir, 0777)

		// 7. Write minimal prometheus.yml
		configPath := filepath.Join(dataDir, "prometheus.yml")
		promConfig := `global:
  scrape_interval: 15s
  evaluation_interval: 15s
`
		if err := os.WriteFile(configPath, []byte(promConfig), 0644); err != nil {
			return fmt.Errorf("writing prometheus config: %w", err)
		}

		// 8. Start Docker container
		dockerArgs := []string{
			"run", "-d",
			"--name", containerName,
			"-v", dataDir + ":/prometheus",
			"-v", configPath + ":/etc/prometheus/prometheus.yml:ro",
			"-p", "0:9090",
			promImage,
			"--config.file=/etc/prometheus/prometheus.yml",
			"--storage.tsdb.path=/prometheus",
			"--storage.tsdb.retention.time=90d",
			"--storage.tsdb.no-lockfile",
			"--web.listen-address=:9090",
		}

		output, err := exec.CommandContext(ctx, "docker", dockerArgs...).CombinedOutput()
		if err != nil {
			return fmt.Errorf("docker run failed: %w\n%s", err, string(output))
		}

		// Get assigned port
		port, err := getContainerPort(ctx, containerName)
		if err != nil {
			return fmt.Errorf("getting container port: %w", err)
		}

		// Store run ID metadata for list command
		writeRunIDFile(runID)

		// Write cache entry now that everything succeeded
		_ = cache.Set(appCache, cacheKey, cachedLogName, "", cache.TTLPrometheusLog)

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

		containerName := promContainerName(runID)
		output, err := exec.CommandContext(ctx, "docker", "rm", "-f", containerName).CombinedOutput()
		if err != nil {
			return fmt.Errorf("stopping container %s: %w\n%s", containerName, err, string(output))
		}
		_, _ = fmt.Fprintf(cmd.OutOrStdout(), "Stopped and removed %s\n", containerName)

		// Clean up extracted data but preserve the cached archive
		if dir, err := promDataDir(runID); err == nil {
			cleanDataDir(dir)
		}
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

// cleanDataDir removes all contents of dir except .tar.zst archive files and the run_id marker.
func cleanDataDir(dir string) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return
	}
	for _, e := range entries {
		name := e.Name()
		if strings.HasSuffix(name, ".tar.zst") || name == "run_id" {
			continue
		}
		_ = os.RemoveAll(filepath.Join(dir, name))
	}
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

func promDataDir(runID string) (string, error) {
	cacheDir, err := os.UserCacheDir()
	if err != nil {
		return "", fmt.Errorf("getting user cache dir: %w", err)
	}
	dir := filepath.Join(cacheDir, "argus-cli", "prometheus", runID)
	if err := os.MkdirAll(dir, 0755); err != nil {
		return "", fmt.Errorf("creating prometheus data dir: %w", err)
	}
	return dir, nil
}

func readRunIDFromDataDir(containerName string) string {
	// Container name is "argus-prom-XXXXXXXX"; enumerate data dirs to find matching run_id
	cacheDir, err := os.UserCacheDir()
	if err != nil {
		return ""
	}
	promBase := filepath.Join(cacheDir, "argus-cli", "prometheus")
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

func writeRunIDFile(runID string) {
	dir, err := promDataDir(runID)
	if err != nil {
		return
	}
	_ = os.WriteFile(filepath.Join(dir, "run_id"), []byte(runID), 0644)
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

	ids := strings.TrimSpace(string(out))
	if ids == "" {
		_, _ = fmt.Fprintln(cmd.OutOrStdout(), "No argus prometheus containers found.")
		return nil
	}

	args := append([]string{"rm", "-f"}, strings.Fields(ids)...)
	output, err := exec.CommandContext(ctx, "docker", args...).CombinedOutput()
	if err != nil {
		return fmt.Errorf("removing containers: %w\n%s", err, string(output))
	}
	_, _ = fmt.Fprintln(cmd.OutOrStdout(), "All argus prometheus containers stopped and removed.")

	// Clean up all data directories
	cacheDir, err := os.UserCacheDir()
	if err == nil {
		_ = os.RemoveAll(filepath.Join(cacheDir, "argus-cli", "prometheus"))
	}
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

		// Move all entries from the snapshot directory up to dataDir
		for _, sub := range subEntries {
			src := filepath.Join(candidateDir, sub.Name())
			dst := filepath.Join(dataDir, sub.Name())
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

func chmodRecursive(dir string, mode os.FileMode) error {
	return filepath.Walk(dir, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		return os.Chmod(path, mode)
	})
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
