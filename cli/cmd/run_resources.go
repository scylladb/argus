package cmd

import (
	"fmt"

	"github.com/spf13/cobra"
)

// ResourceView is a single cloud resource for output.
type ResourceView struct {
	Name            string `json:"name"`
	ResourceType    string `json:"resource_type"`
	InstanceType    string `json:"instance_type,omitempty"`
	PrivateIP       string `json:"private_ip,omitempty"`
	PublicIP        string `json:"public_ip,omitempty"`
	DC              string `json:"dc,omitempty"`
	Rack            string `json:"rack,omitempty"`
	Provider        string `json:"provider,omitempty"`
	Shards          int    `json:"shards,omitempty"`
	CreationTime    string `json:"creation_time,omitempty"`
	TerminationTime string `json:"termination_time,omitempty"`
}

// ResourceListView wraps a slice of ResourceView for output.
type ResourceListView struct {
	Resources []ResourceView `json:"resources"`
}

// Headers implements output.Tabular.
func (v *ResourceListView) Headers() []string {
	return []string{"Name", "Type", "InstanceType", "PrivateIP", "PublicIP", "DC", "Rack"}
}

// Rows implements output.Tabular.
func (v *ResourceListView) Rows() [][]string {
	rows := make([][]string, 0, len(v.Resources))
	for _, r := range v.Resources {
		rows = append(rows, []string{
			r.Name, r.ResourceType, r.InstanceType,
			r.PrivateIP, r.PublicIP, r.DC, r.Rack,
		})
	}
	return rows
}

var runResourcesCmd = &cobra.Command{
	Use:   "resources <run_id>",
	Short: "Allocated cloud resources: nodes, IPs, types (SCT only)",
	Long: `List all allocated cloud resources for an SCT run.

Each resource includes: name, type (db/loader/monitor/sct-runner),
instance type, private/public IPs, datacenter, rack, and
creation/termination times.`,
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
		if !info.IsSCT() {
			return fmt.Errorf("resources are only available for SCT runs")
		}

		r := info.SCT
		result := make([]ResourceView, 0, len(r.AllocatedResources))
		for _, res := range r.AllocatedResources {
			rv := ResourceView{
				Name:         res.Name,
				ResourceType: res.ResourceType,
			}
			if ii := res.InstanceInfo; ii != nil {
				rv.InstanceType = ii.InstanceType
				rv.PrivateIP = ii.PrivateIP
				rv.PublicIP = ii.PublicIP
				rv.DC = ii.DCName
				rv.Rack = ii.RackName
				rv.Provider = ii.Provider
				rv.Shards = ii.ShardsAmount
				rv.CreationTime = formatTimestamp(ii.CreationTime)
				rv.TerminationTime = formatTimestamp(ii.TerminationTime)
			}
			result = append(result, rv)
		}

		return out.Write(&ResourceListView{Resources: result})
	},
}
