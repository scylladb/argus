package cmd

import (
	"fmt"
	"os"
	"path/filepath"

	"github.com/scylladb/argus/cli/internal/api"
	"github.com/spf13/cobra"
)

// LogListView is the list of available log archive names.
type LogListView struct {
	Logs []string `json:"logs"`
}

// Headers implements output.Tabular.
func (v *LogListView) Headers() []string { return []string{"Log Name"} }

// Rows implements output.Tabular.
func (v *LogListView) Rows() [][]string {
	rows := make([][]string, 0, len(v.Logs))
	for _, name := range v.Logs {
		rows = append(rows, []string{name})
	}
	return rows
}

// DownloadResultView is the result of a log download.
type DownloadResultView struct {
	Downloaded string `json:"downloaded"`
	SizeBytes  int64  `json:"size_bytes"`
}

// Headers implements output.Tabular.
func (v *DownloadResultView) Headers() []string { return []string{"Downloaded", "Size (bytes)"} }

// Rows implements output.Tabular.
func (v *DownloadResultView) Rows() [][]string {
	return [][]string{{v.Downloaded, fmt.Sprintf("%d", v.SizeBytes)}}
}

var (
	logNameFlag     string
	downloadDirFlag string
)

var runLogsCmd = &cobra.Command{
	Use:   "logs <run_id>",
	Short: "List or download run logs (SCT only)",
	Long: `List available log archives or download a specific one. SCT runs only.

Without flags, outputs a JSON array of downloadable log archive names.
With --log-name and --download, fetches a pre-signed URL from Argus
and downloads the archive to the specified directory.`,
	Args: cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		ctx := cmd.Context()
		client := APIClientFrom(ctx)
		out := OutputterFrom(ctx)
		c := CacheFrom(ctx)

		runID, err := parseRunID(args[0])
		if err != nil {
			return err
		}

		if downloadDirFlag != "" && logNameFlag == "" {
			return fmt.Errorf("--log-name is required when using --download")
		}
		if logNameFlag != "" && downloadDirFlag == "" {
			return fmt.Errorf("--download is required when using --log-name")
		}

		info, err := fetchRunInfo(ctx, client, c, runID)
		if err != nil {
			return err
		}
		if !info.IsSCT() {
			return fmt.Errorf("log listing is only supported for SCT runs")
		}

		// Download mode.
		if downloadDirFlag != "" {
			path := fmt.Sprintf("/api/v1/tests/%s/%s/log/%s/download", info.Type, runID, logNameFlag)
			downloadURL, err := api.DoRedirect(client, ctx, "GET", path)
			if err != nil {
				return fmt.Errorf("getting download URL: %w", err)
			}

			if err := os.MkdirAll(downloadDirFlag, 0o755); err != nil {
				return fmt.Errorf("creating download directory: %w", err)
			}

			fileName := logNameFlag
			if filepath.Ext(fileName) == "" {
				fileName += ".zst"
			}
			dst := filepath.Join(downloadDirFlag, fileName)
			size, err := api.DownloadFile(downloadURL, dst)
			if err != nil {
				return fmt.Errorf("downloading log: %w", err)
			}

			return out.Write(&DownloadResultView{Downloaded: dst, SizeBytes: size})
		}

		// List mode.
		r := info.SCT
		names := make([]string, 0, len(r.Logs))
		for _, entry := range r.Logs {
			if len(entry) == 0 {
				continue
			}
			name := entry[0]
			if filepath.Ext(name) == "" {
				name += ".zst"
			}
			names = append(names, name)
		}

		return out.Write(&LogListView{Logs: names})
	},
}

func init() {
	runLogsCmd.Flags().StringVar(&logNameFlag, "log-name", "", "name of the log archive to download")
	runLogsCmd.Flags().StringVar(&downloadDirFlag, "download", "", "directory to download the log to")
}
