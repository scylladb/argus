package cmd

import (
	"encoding/json"
	"fmt"

	"github.com/spf13/cobra"
)

// RunDetailsView is the output for "run details".
type RunDetailsView struct {
	RunID               string         `json:"run_id"`
	RunType             string         `json:"run_type"`
	Status              string         `json:"status"`
	StartTime           string         `json:"start_time"`
	EndTime             string         `json:"end_time"`
	TestMethod          string         `json:"test_method,omitempty"`
	SubtestName         string         `json:"subtest_name,omitempty"`
	ScyllaVersion       string         `json:"scylla_version,omitempty"`
	BuildID             string         `json:"build_id,omitempty"`
	BuildJobURL         string         `json:"build_job_url,omitempty"`
	BranchName          string         `json:"branch_name,omitempty"`
	InvestigationStatus string         `json:"investigation_status,omitempty"`
	StartedBy           string         `json:"started_by,omitempty"`
	ConfigFiles         []string       `json:"config_files,omitempty"`
	CloudSetup          any            `json:"cloud_setup,omitempty"`
	Region              []string       `json:"region,omitempty"`
	Packages            []packageEntry `json:"packages,omitempty"`
	EventGroupsCount    int            `json:"event_groups_count,omitempty"`
	NemesisCount        int            `json:"nemesis_count,omitempty"`
	LogsCount           int            `json:"logs_count,omitempty"`
	ResourcesCount      int            `json:"resources_count,omitempty"`
}

type packageEntry struct {
	Name       string `json:"name"`
	Version    string `json:"version,omitempty"`
	RevisionID string `json:"revision_id,omitempty"`
}

type cloudSetupView struct {
	Backend string            `json:"backend,omitempty"`
	DBNode  *nodeSetupSummary `json:"db_node,omitempty"`
	Loader  *nodeSetupSummary `json:"loader_node,omitempty"`
	Monitor *nodeSetupSummary `json:"monitor_node,omitempty"`
}

type nodeSetupSummary struct {
	Count        int    `json:"count,omitempty"`
	InstanceType string `json:"instance_type,omitempty"`
}

// Headers implements output.Tabular.
func (v *RunDetailsView) Headers() []string { return []string{"Field", "Value"} }

// Rows implements output.Tabular.
func (v *RunDetailsView) Rows() [][]string {
	rows := [][]string{
		{"run_id", v.RunID},
		{"run_type", v.RunType},
		{"status", v.Status},
		{"start_time", v.StartTime},
		{"end_time", v.EndTime},
	}
	add := func(label, val string) {
		if val != "" {
			rows = append(rows, []string{label, val})
		}
	}
	add("test_method", v.TestMethod)
	add("subtest_name", v.SubtestName)
	add("scylla_version", v.ScyllaVersion)
	add("build_id", v.BuildID)
	add("build_job_url", v.BuildJobURL)
	add("branch_name", v.BranchName)
	add("investigation_status", v.InvestigationStatus)
	add("started_by", v.StartedBy)
	if v.CloudSetup != nil {
		b, _ := json.Marshal(v.CloudSetup)
		rows = append(rows, []string{"cloud_setup", string(b)})
	}
	if len(v.Region) > 0 {
		b, _ := json.Marshal(v.Region)
		rows = append(rows, []string{"region", string(b)})
	}
	if len(v.Packages) > 0 {
		b, _ := json.Marshal(v.Packages)
		rows = append(rows, []string{"packages", string(b)})
	}
	if v.EventGroupsCount > 0 {
		rows = append(rows, []string{"event_groups_count", fmt.Sprintf("%d", v.EventGroupsCount)})
	}
	if v.NemesisCount > 0 {
		rows = append(rows, []string{"nemesis_count", fmt.Sprintf("%d", v.NemesisCount)})
	}
	if v.LogsCount > 0 {
		rows = append(rows, []string{"logs_count", fmt.Sprintf("%d", v.LogsCount)})
	}
	if v.ResourcesCount > 0 {
		rows = append(rows, []string{"resources_count", fmt.Sprintf("%d", v.ResourcesCount)})
	}
	return rows
}

var runDetailsCmd = &cobra.Command{
	Use:   "details <run_id>",
	Short: "Run summary: status, versions, timing, cloud setup",
	Long: `Show high-level run summary in an LLM-friendly format.

Includes: status, test method, scylla version, start/end times,
cloud backend, node counts/types, and installed packages.
Auto-detects run type (SCT vs DTest).`,
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

		info, err := fetchRunInfo(ctx, client, c, runID)
		if err != nil {
			return err
		}

		view := &RunDetailsView{
			RunID:   runID,
			RunType: info.Type,
		}

		if info.IsSCT() {
			r := info.SCT
			view.Status = string(r.Status)
			view.StartTime = formatTimestamp(r.StartTime)
			view.EndTime = formatTimestamp(r.EndTime)
			view.TestMethod = r.TestMethod
			view.SubtestName = r.SubtestName
			view.ScyllaVersion = r.ScyllaVersion
			view.BuildID = r.BuildID
			view.BuildJobURL = r.BuildJobURL
			view.BranchName = r.BranchName
			view.InvestigationStatus = string(r.InvestigationStatus)
			view.StartedBy = r.StartedBy
			view.ConfigFiles = r.ConfigFiles
			view.Region = r.RegionName
			view.EventGroupsCount = len(r.Events)
			view.NemesisCount = len(r.NemesisData)
			view.LogsCount = len(r.Logs)
			view.ResourcesCount = len(r.AllocatedResources)

			if r.CloudSetup != nil {
				cs := &cloudSetupView{Backend: r.CloudSetup.Backend}
				if n := r.CloudSetup.DBNode; n != nil {
					cs.DBNode = &nodeSetupSummary{Count: n.NodeAmount, InstanceType: n.InstanceType}
				}
				if n := r.CloudSetup.LoaderNode; n != nil {
					cs.Loader = &nodeSetupSummary{Count: n.NodeAmount, InstanceType: n.InstanceType}
				}
				if n := r.CloudSetup.MonitorNode; n != nil {
					cs.Monitor = &nodeSetupSummary{Count: n.NodeAmount, InstanceType: n.InstanceType}
				}
				view.CloudSetup = cs
			}

			for _, p := range r.Packages {
				view.Packages = append(view.Packages, packageEntry{
					Name: p.Name, Version: p.Version, RevisionID: p.RevisionID,
				})
			}
		} else {
			r := info.Generic
			view.Status = string(r.Status)
			view.StartTime = formatTimestamp(r.StartTime)
			view.EndTime = formatTimestamp(r.EndTime)
			view.ScyllaVersion = r.ScyllaVersion
			view.BuildID = r.BuildID
			view.BuildJobURL = r.BuildJobURL
			view.InvestigationStatus = string(r.InvestigationStatus)
			view.StartedBy = r.StartedBy
			view.LogsCount = len(r.Logs)
		}

		return out.Write(view)
	},
}
