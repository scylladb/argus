package models

// RunConfiguration mirrors the RunConfiguration Cassandra model.
//
// content holds the raw decoded text of the configuration file.
type RunConfiguration struct {
	RunID   string `json:"run_id"`
	Name    string `json:"name"`
	Content string `json:"content"`
}

// RunConfigParam mirrors the RunConfigParam Cassandra model.
// It stores individual key/value parameters associated with a run.
type RunConfigParam struct {
	Name  string `json:"name"`
	Value string `json:"value"`
	RunID string `json:"run_id"`
}

// RunConfigurationListResponse is the response payload for run-configuration
// list endpoints.
type RunConfigurationListResponse = []RunConfiguration

// RunConfigParamListResponse is the response payload for run-config-param
// list endpoints.
type RunConfigParamListResponse = []RunConfigParam
