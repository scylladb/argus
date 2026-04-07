package models

import (
	"encoding/json"
	"fmt"
	"sort"
	"strings"
	"time"
)

// ---------------------------------------------------------------------------
// Shared enumerations
// ---------------------------------------------------------------------------

// TestStatus mirrors argus.common.enums.TestStatus.
type TestStatus string

const (
	TestStatusCreated    TestStatus = "created"
	TestStatusRunning    TestStatus = "running"
	TestStatusFailed     TestStatus = "failed"
	TestStatusTestError  TestStatus = "test_error"
	TestStatusError      TestStatus = "error"
	TestStatusPassed     TestStatus = "passed"
	TestStatusAborted    TestStatus = "aborted"
	TestStatusNotPlanned TestStatus = "not_planned"
	TestStatusNotRun     TestStatus = "not_run"
)

// TestInvestigationStatus mirrors argus.common.enums.TestInvestigationStatus.
type TestInvestigationStatus string

const (
	TestInvestigationStatusNotInvestigated TestInvestigationStatus = "not_investigated"
	TestInvestigationStatusInProgress      TestInvestigationStatus = "in_progress"
	TestInvestigationStatusInvestigated    TestInvestigationStatus = "investigated"
	TestInvestigationStatusIgnored         TestInvestigationStatus = "ignored"
)

// SCTEventSeverity mirrors argus.backend.plugins.sct.testrun.SCTEventSeverity.
type SCTEventSeverity string

const (
	SCTEventSeverityCritical SCTEventSeverity = "CRITICAL"
	SCTEventSeverityError    SCTEventSeverity = "ERROR"
	SCTEventSeverityWarning  SCTEventSeverity = "WARNING"
	SCTEventSeverityNormal   SCTEventSeverity = "NORMAL"
	SCTEventSeverityDebug    SCTEventSeverity = "DEBUG"
)

// ResourceState mirrors argus.common.enums.ResourceState.
type ResourceState string

const (
	ResourceStateRunning    ResourceState = "running"
	ResourceStateStopped    ResourceState = "stopped"
	ResourceStateTerminated ResourceState = "terminated"
)

// ---------------------------------------------------------------------------
// SCT UDTs (argus/backend/plugins/sct/udt.py)
// ---------------------------------------------------------------------------

// PackageVersion corresponds to the PackageVersion_v2 Cassandra UDT.
// Serialised via ArgusJSONProvider.default() → dict.
type PackageVersion struct {
	Name       string `json:"name"`
	Version    string `json:"version"`
	Date       string `json:"date"`
	RevisionID string `json:"revision_id"`
	BuildID    string `json:"build_id"`
}

// CloudInstanceDetails corresponds to the CloudInstanceDetails_v3 Cassandra UDT.
type CloudInstanceDetails struct {
	Provider          string `json:"provider"`
	InstanceType      string `json:"instance_type"`
	Region            string `json:"region"`
	PublicIP          string `json:"public_ip"`
	PrivateIP         string `json:"private_ip"`
	DCName            string `json:"dc_name"`
	RackName          string `json:"rack_name"`
	CreationTime      int64  `json:"creation_time"`
	TerminationTime   int64  `json:"termination_time"`
	TerminationReason string `json:"termination_reason"`
	ShardsAmount      int    `json:"shards_amount"`
}

// CloudNodesInfo corresponds to the CloudNodesInfo Cassandra UDT.
type CloudNodesInfo struct {
	ImageID      string `json:"image_id"`
	InstanceType string `json:"instance_type"`
	NodeAmount   int    `json:"node_amount"`
	PostBehavior string `json:"post_behaviour"`
}

// CloudSetupDetails corresponds to the CloudSetupDetails Cassandra UDT.
type CloudSetupDetails struct {
	DBNode      *CloudNodesInfo `json:"db_node"`
	LoaderNode  *CloudNodesInfo `json:"loader_node"`
	MonitorNode *CloudNodesInfo `json:"monitor_node"`
	Backend     string          `json:"backend"`
}

// CloudResource corresponds to the CloudResource_v3 Cassandra UDT.
type CloudResource struct {
	Name         string                `json:"name"`
	State        ResourceState         `json:"state"`
	ResourceType string                `json:"resource_type"`
	InstanceInfo *CloudInstanceDetails `json:"instance_info"`
}

// EventsBySeverity corresponds to the EventsBySeverity Cassandra UDT.
type EventsBySeverity struct {
	Severity    SCTEventSeverity `json:"severity"`
	EventAmount int              `json:"event_amount"`
	LastEvents  []string         `json:"last_events"`
}

// NodeDescription corresponds to the NodeDescription Cassandra UDT.
type NodeDescription struct {
	Name   string `json:"name"`
	IP     string `json:"ip"`
	Shards int    `json:"shards"`
}

// NemesisRunInfo corresponds to the NemesisRunInfo Cassandra UDT.
type NemesisRunInfo struct {
	ClassName  string           `json:"class_name"`
	Name       string           `json:"name"`
	Duration   int              `json:"duration"`
	TargetNode *NodeDescription `json:"target_node"`
	Status     string           `json:"status"`
	StartTime  int64            `json:"start_time"`
	EndTime    int64            `json:"end_time"`
	StackTrace string           `json:"stack_trace"`
}

// PerformanceHDRHistogram corresponds to the PerformanceHDRHistogram Cassandra UDT.
type PerformanceHDRHistogram struct {
	StartTime       int     `json:"start_time"`
	EndTime         float64 `json:"end_time"`
	Percentile50    float32 `json:"percentile_50"`
	Percentile90    float32 `json:"percentile_90"`
	Percentile95    float32 `json:"percentile_95"`
	Percentile99    float32 `json:"percentile_99"`
	Percentile999   float32 `json:"percentile_99_9"`
	Percentile9999  float32 `json:"percentile_99_99"`
	Percentile99999 float32 `json:"percentile_99_999"`
	Stddev          float32 `json:"stddev"`
}

// ---------------------------------------------------------------------------
// PluginModelBase fields (shared by every run type)
// ---------------------------------------------------------------------------

// LogEntry represents a single log file attached to a test run.
type LogEntry struct {
	Name string `json:"name"`
	URL  string `json:"url"`
}

// RunBase contains the fields from PluginModelBase that every plugin run
// shares. All UUID fields are serialised as strings by ArgusJSONProvider.
// Datetime fields use ISO-8601 with milliseconds.
type RunBase struct {
	BuildID             string                  `json:"build_id"`
	StartTime           string                  `json:"start_time"`
	ID                  string                  `json:"id"`
	ReleaseID           string                  `json:"release_id"`
	GroupID             string                  `json:"group_id"`
	TestID              string                  `json:"test_id"`
	Assignee            string                  `json:"assignee"`
	Status              TestStatus              `json:"status"`
	InvestigationStatus TestInvestigationStatus `json:"investigation_status"`
	Heartbeat           int64                   `json:"heartbeat"`
	EndTime             string                  `json:"end_time"`
	BuildJobURL         string                  `json:"build_job_url"`
	ProductVersion      string                  `json:"product_version"`
}

// ---------------------------------------------------------------------------
// SCTTestRun (argus/backend/plugins/sct/testrun.py)
// ---------------------------------------------------------------------------

// SCTJunitReport is a single JUnit XML report attached to an SCTTestRun.
// It is injected by get_run_response and not stored in the run table itself.
type SCTJunitReport struct {
	TestID   string `json:"test_id"`
	FileName string `json:"file_name"`
	Report   string `json:"report"`
}

// SCTEvent mirrors the sct_event Cassandra table.
type SCTEvent struct {
	RunID             string           `json:"run_id"`
	Severity          SCTEventSeverity `json:"severity"`
	Ts                string           `json:"ts"`
	EventID           string           `json:"event_id"`
	EventType         string           `json:"event_type"`
	Message           string           `json:"message"`
	DuplicateID       string           `json:"duplicate_id"`
	Node              string           `json:"node"`
	ReceivedTimestamp string           `json:"received_timestamp"`
	NemesisName       string           `json:"nemesis_name"`
	Duration          float32          `json:"duration"`
	TargetNode        string           `json:"target_node"`
	NemesisStatus     string           `json:"nemesis_status"`
	KnownIssue        string           `json:"known_issue"`
}

// SCTTestRun is the full run response for the scylla-cluster-tests plugin.
// The logs field is [][]string (list of [log_name, log_url] 2-tuples).
// histograms is a list of map[string]PerformanceHDRHistogram.
type SCTTestRun struct {
	RunBase

	// Test Details
	TestName         string           `json:"test_name"`
	StressDuration   float32          `json:"stress_duration"`
	ScmRevisionID    string           `json:"scm_revision_id"`
	BranchName       string           `json:"branch_name"`
	OriginURL        string           `json:"origin_url"`
	StartedBy        string           `json:"started_by"`
	ConfigFiles      []string         `json:"config_files"`
	Packages         []PackageVersion `json:"packages"`
	ScyllaVersion    string           `json:"scylla_version"`
	VersionSource    string           `json:"version_source"`
	YAMLTestDuration int              `json:"yaml_test_duration"`

	// Logs: list of [log_name, log_url] tuples.
	Logs [][]string `json:"logs"`

	// Test Preset Resources
	SCTRunnerHost *CloudInstanceDetails `json:"sct_runner_host"`
	RegionName    []string              `json:"region_name"`
	CloudSetup    *CloudSetupDetails    `json:"cloud_setup"`

	// Test Runtime Resources
	AllocatedResources []CloudResource `json:"allocated_resources"`

	// Test Results
	Events      []EventsBySeverity `json:"events"`
	NemesisData []NemesisRunInfo   `json:"nemesis_data"`
	Screenshots []string           `json:"screenshots"`

	// Subtest
	SubtestName string `json:"subtest_name"`

	// Gemini fields
	OracleNodesCount        int    `json:"oracle_nodes_count"`
	OracleNodeAMIID         string `json:"oracle_node_ami_id"`
	OracleNodeInstanceType  string `json:"oracle_node_instance_type"`
	OracleNodeScyllaVersion string `json:"oracle_node_scylla_version"`
	GeminiCommand           string `json:"gemini_command"`
	GeminiVersion           string `json:"gemini_version"`
	GeminiStatus            string `json:"gemini_status"`
	GeminiSeed              string `json:"gemini_seed"`
	GeminiWriteOps          int    `json:"gemini_write_ops"`
	GeminiWriteErrors       int    `json:"gemini_write_errors"`
	GeminiReadOps           int    `json:"gemini_read_ops"`
	GeminiReadErrors        int    `json:"gemini_read_errors"`

	// Performance fields
	PerfOpRateAverage  float64 `json:"perf_op_rate_average"`
	PerfOpRateTotal    float64 `json:"perf_op_rate_total"`
	PerfAvgLatency99th float64 `json:"perf_avg_latency_99th"`
	PerfAvgLatencyMean float64 `json:"perf_avg_latency_mean"`
	PerfTotalErrors    float64 `json:"perf_total_errors"`
	StressCmd          string  `json:"stress_cmd"`

	// HDR histograms: list of map[op_name]histogram
	Histograms []map[string]PerformanceHDRHistogram `json:"histograms"`
	TestMethod string                               `json:"test_method"`

	// Injected by get_run_response
	JUnitReports []SCTJunitReport `json:"junit_reports"`
}

// ---------------------------------------------------------------------------
// GenericRun (argus/backend/plugins/generic/model.py)
// ---------------------------------------------------------------------------

// GenericRun is the full run response for the generic plugin.
// The logs field is a map[string]string (log_name → log_url).
type GenericRun struct {
	RunBase

	// Logs: map of log_name → log_url (different from SCT/DriverMatrix).
	Logs map[string]string `json:"logs"`

	StartedBy     string `json:"started_by"`
	SubType       string `json:"sub_type"`
	ScyllaVersion string `json:"scylla_version"`
}

// ---------------------------------------------------------------------------
// DriverMatrixRun (argus/backend/plugins/driver_matrix_tests/model.py)
// ---------------------------------------------------------------------------

// DriverTestCase mirrors the TestCase UDT.
type DriverTestCase struct {
	Name      string  `json:"name"`
	Status    string  `json:"status"`
	Time      float32 `json:"time"`
	ClassName string  `json:"classname"`
	Message   string  `json:"message"`
}

// DriverTestSuite mirrors the TestSuite UDT.
type DriverTestSuite struct {
	Name       string           `json:"name"`
	TestsTotal int              `json:"tests_total"`
	Failures   int              `json:"failures"`
	Disabled   int              `json:"disabled"`
	Skipped    int              `json:"skipped"`
	Passed     int              `json:"passed"`
	Errors     int              `json:"errors"`
	Time       float32          `json:"time"`
	Cases      []DriverTestCase `json:"cases"`
}

// DriverTestCollection mirrors the TestCollection UDT.
type DriverTestCollection struct {
	Name           string            `json:"name"`
	Driver         string            `json:"driver"`
	TestsTotal     int               `json:"tests_total"`
	FailureMessage string            `json:"failure_message"`
	Failures       int               `json:"failures"`
	Disabled       int               `json:"disabled"`
	Skipped        int               `json:"skipped"`
	Passed         int               `json:"passed"`
	Errors         int               `json:"errors"`
	Timestamp      string            `json:"timestamp"`
	Time           float32           `json:"time"`
	Suites         []DriverTestSuite `json:"suites"`
}

// DriverEnvironmentInfo mirrors the EnvironmentInfo UDT.
type DriverEnvironmentInfo struct {
	Key   string `json:"key"`
	Value string `json:"value"`
}

// DriverTestRun is the full run response for the driver-matrix-tests plugin.
// Logs are inherited as [][]string (same as PluginModelBase / SCT).
type DriverTestRun struct {
	RunBase

	// Logs: list of [log_name, log_url] tuples (inherited from PluginModelBase).
	Logs [][]string `json:"logs"`

	ScyllaVersion   string                  `json:"scylla_version"`
	TestCollection  []DriverTestCollection  `json:"test_collection"`
	EnvironmentInfo []DriverEnvironmentInfo `json:"environment_info"`
}

// ---------------------------------------------------------------------------
// SirenadaRun (argus/backend/plugins/sirenada/model.py)
// ---------------------------------------------------------------------------

// SirenadaTest mirrors the SirenadaTest UDT.
type SirenadaTest struct {
	TestName         string  `json:"test_name"`
	ClassName        string  `json:"class_name"`
	FileName         string  `json:"file_name"`
	BrowserType      string  `json:"browser_type"`
	ClusterType      string  `json:"cluster_type"`
	Status           string  `json:"status"`
	Duration         float32 `json:"duration"`
	Message          string  `json:"message"`
	StartTime        string  `json:"start_time"`
	StackTrace       string  `json:"stack_trace"`
	ScreenshotFile   string  `json:"screenshot_file"`
	S3FolderID       string  `json:"s3_folder_id"`
	RequestsFile     string  `json:"requests_file"`
	SirenadaTestID   string  `json:"sirenada_test_id"`
	SirenadaUser     string  `json:"sirenada_user"`
	SirenadaPassword string  `json:"sirenada_password"`
}

// SirenadaRun is the full run response for the sirenada plugin.
// The logs field is a map[string]string (log_name → log_url).
type SirenadaRun struct {
	RunBase

	// Logs: map of log_name → log_url (same override as GenericRun).
	Logs map[string]string `json:"logs"`

	ScyllaVersion   string   `json:"scylla_version"`
	Region          string   `json:"region"`
	SirenadaTestIDs []string `json:"sirenada_test_ids"`
	// s3_folder_ids is a list of (s3_folder_id, sirenada_test_id) tuples.
	S3FolderIDs [][]string     `json:"s3_folder_ids"`
	Browsers    []string       `json:"browsers"`
	Clusters    []string       `json:"clusters"`
	SCTTestID   string         `json:"sct_test_id"`
	Results     []SirenadaTest `json:"results"`
}

// ---------------------------------------------------------------------------
// Run details (lightweight view — no logs, events, resources, screenshots)
// ---------------------------------------------------------------------------

// SCTRunDetails is the basic view of an SCTTestRun as shown on the Argus
// Details page.  Heavy fields (logs, events, nemesis_data, screenshots,
// allocated_resources, histograms, junit_reports) are intentionally omitted;
// use the dedicated subcommands (run logs, run activity, run nemeses, etc.)
// to retrieve those.
type SCTRunDetails struct {
	RunBase

	TestName         string           `json:"test_name"`
	ScyllaVersion    string           `json:"scylla_version"`
	StartedBy        string           `json:"started_by"`
	BranchName       string           `json:"branch_name"`
	OriginURL        string           `json:"origin_url"`
	ConfigFiles      []string         `json:"config_files"`
	ScmRevisionID    string           `json:"scm_revision_id"`
	SubtestName      string           `json:"subtest_name"`
	StressDuration   float32          `json:"stress_duration"`
	YAMLTestDuration int              `json:"yaml_test_duration"`
	RegionName       []string         `json:"region_name"`
	Packages         []PackageVersion `json:"packages"`
}

// GenericRunDetails is the basic view of a GenericRun.
type GenericRunDetails struct {
	RunBase

	StartedBy     string `json:"started_by"`
	SubType       string `json:"sub_type"`
	ScyllaVersion string `json:"scylla_version"`
}

// DriverRunDetails is the basic view of a DriverTestRun.
type DriverRunDetails struct {
	RunBase

	ScyllaVersion string `json:"scylla_version"`
}

// SirenadaRunDetails is the basic view of a SirenadaRun.
type SirenadaRunDetails struct {
	RunBase

	ScyllaVersion string `json:"scylla_version"`
	Region        string `json:"region"`
	SCTTestID     string `json:"sct_test_id"`
}

// RunMeta contains the subset of fields returned by get_run_meta_by_build_id
// and get_run_meta_by_run_id queries.
type RunMeta struct {
	ID                  string                  `json:"id"`
	TestID              string                  `json:"test_id"`
	GroupID             string                  `json:"group_id"`
	ReleaseID           string                  `json:"release_id"`
	Status              TestStatus              `json:"status"`
	StartTime           string                  `json:"start_time"`
	BuildJobURL         string                  `json:"build_job_url"`
	BuildID             string                  `json:"build_id"`
	Assignee            string                  `json:"assignee"`
	EndTime             string                  `json:"end_time"`
	InvestigationStatus TestInvestigationStatus `json:"investigation_status"`
	Heartbeat           int64                   `json:"heartbeat"`
}

type RunType struct {
	RunType string `json:"run_type"`
}

// NemesisRecord is the CLI-facing model for a nemesis record returned by
// GET /api/v1/client/sct/<run_id>/nemesis/get.
type NemesisRecord struct {
	ClassName  string           `json:"class_name"`
	Name       string           `json:"name"`
	Duration   int              `json:"duration"`
	TargetNode *NodeDescription `json:"target_node"`
	Status     string           `json:"status"`
	StartTime  int64            `json:"start_time"`
	EndTime    int64            `json:"end_time"`
	StackTrace string           `json:"stack_trace"`
}

// ---------------------------------------------------------------------------
// Activity response (GET /run/<run_id>/activity)
// ---------------------------------------------------------------------------

// ActivityResponse is the response payload for the test-run activity endpoint.
// Events maps event IDs to their human-readable descriptions.
type ActivityResponse struct {
	RunID     string            `json:"run_id"`
	RawEvents json.RawMessage   `json:"raw_events"`
	Events    map[string]string `json:"events"`
}

// Headers implements output.Tabular for ActivityResponse.
func (ActivityResponse) Headers() []string {
	return []string{"Event Id", "Description"}
}

// Rows implements output.Tabular for ActivityResponse.  Events are sorted by
// key so that output is deterministic.
func (a ActivityResponse) Rows() [][]string {
	keys := make([]string, 0, len(a.Events))
	for k := range a.Events {
		keys = append(keys, k)
	}
	sort.Strings(keys)

	rows := make([][]string, 0, len(keys))
	for _, k := range keys {
		rows = append(rows, []string{k, a.Events[k]})
	}
	return rows
}

// ---------------------------------------------------------------------------
// Fetch results (GET /run/<test_id>/<run_id>/fetch_results)
// ---------------------------------------------------------------------------

// ResultCell is a single cell inside a ResultTable.
type ResultCell struct {
	Value  any    `json:"value"`
	Status string `json:"status"`
}

// ResultColumnMeta describes one column in a ResultTable.
type ResultColumnMeta struct {
	Name   string `json:"name"`
	Status string `json:"status"`
}

// ResultTable is one performance/result table returned by the fetch_results
// endpoint.  TableData is keyed as row-name → column-name → cell.
type ResultTable struct {
	Description string                           `json:"description"`
	TableData   map[string]map[string]ResultCell `json:"table_data"`
	Columns     []ResultColumnMeta               `json:"columns"`
	Rows        []string                         `json:"rows"`
	TableStatus string                           `json:"table_status"`
}

// Headers implements output.Tabular for ResultTable.  The first column is the
// row name; subsequent columns come from the table's Columns metadata.
func (rt ResultTable) Headers() []string {
	h := make([]string, 0, 1+len(rt.Columns))
	h = append(h, "Row")
	for _, c := range rt.Columns {
		h = append(h, c.Name)
	}
	return h
}

// Rows implements output.Tabular for ResultTable.  Row order follows
// rt.Rows; column order follows rt.Columns.
func (rt ResultTable) TableRows() [][]string {
	out := make([][]string, 0, len(rt.Rows))
	for _, rowName := range rt.Rows {
		row := make([]string, 0, 1+len(rt.Columns))
		row = append(row, rowName)
		colData := rt.TableData[rowName]
		for _, col := range rt.Columns {
			cell, ok := colData[col.Name]
			if !ok {
				row = append(row, "")
			} else {
				row = append(row, fmt.Sprint(cell.Value))
			}
		}
		out = append(out, row)
	}
	return out
}

// FetchResultsEnvelope is the non-standard envelope returned by the
// fetch_results endpoint.  Unlike other endpoints the payload key is "tables"
// rather than "response".
type FetchResultsEnvelope struct {
	Status string        `json:"status"`
	Tables []ResultTable `json:"tables"`
}

// FetchResultsResponse wraps []ResultTable to implement output.Tabular by
// rendering all tables sequentially.
type FetchResultsResponse struct {
	Tables []ResultTable
}

// Headers implements output.Tabular.  Uses the first table's headers or
// returns a single "Table" column when empty.
func (f FetchResultsResponse) Headers() []string {
	if len(f.Tables) == 0 {
		return []string{"Table"}
	}
	// Prefix with "Table" column to distinguish between tables.
	h := []string{"Table"}
	h = append(h, f.Tables[0].Headers()...)
	return h
}

// Rows implements output.Tabular.  Each result table's rows are emitted with
// the table description prepended as the first column.
func (f FetchResultsResponse) Rows() [][]string {
	var rows [][]string
	for _, tbl := range f.Tables {
		for _, r := range tbl.TableRows() {
			row := make([]string, 0, 1+len(r))
			row = append(row, tbl.Description)
			row = append(row, r...)
			rows = append(rows, row)
		}
	}
	return rows
}

// ---------------------------------------------------------------------------
// SCT events (GET /api/v1/sct/<run_id>/events/get)
// ---------------------------------------------------------------------------

// SCTEventsResponse is the response payload for the SCT events endpoint.
// Events is the list of individual SCT events returned by the server.
type SCTEventsResponse struct {
	RunID  string     `json:"run_id"`
	Events []SCTEvent `json:"response"`
}

// Headers implements output.Tabular for SCTEventsResponse.
func (SCTEventsResponse) Headers() []string {
	return []string{"Severity", "Timestamp", "Type", "Node", "Nemesis", "Message"}
}

// Rows implements output.Tabular for SCTEventsResponse.
func (r SCTEventsResponse) Rows() [][]string {
	rows := make([][]string, 0, len(r.Events))
	for _, e := range r.Events {
		msg := e.Message
		if len(msg) > 200 {
			msg = msg[:200] + "..."
		}
		rows = append(rows, []string{
			string(e.Severity),
			e.Ts,
			e.EventType,
			e.Node,
			e.NemesisName,
			msg,
		})
	}
	return rows
}

// MarshalJSON implements json.Marshaler so that the JSON outputter serialises
// the event list directly.
func (r SCTEventsResponse) MarshalJSON() ([]byte, error) {
	return json.Marshal(r.Events)
}

// ---------------------------------------------------------------------------
// NemesisResponse – nemesis summary extracted from a cached SCTTestRun
// ---------------------------------------------------------------------------

// NemesisResponse wraps the nemesis list from an SCTTestRun so it can be
// rendered as a table without re-fetching the full run.
type NemesisResponse struct {
	RunID   string           `json:"run_id"`
	Nemeses []NemesisRunInfo `json:"nemeses"`
}

// Headers implements output.Tabular for NemesisResponse.
func (NemesisResponse) Headers() []string {
	return []string{"Class", "Name", "Status", "Duration(s)", "Start Time", "End Time", "Target Node", "Stack Trace"}
}

// Rows implements output.Tabular for NemesisResponse.
func (n NemesisResponse) Rows() [][]string {
	rows := make([][]string, 0, len(n.Nemeses))
	for _, nem := range n.Nemeses {
		startStr := ""
		if nem.StartTime > 0 {
			startStr = time.Unix(nem.StartTime, 0).UTC().Format(time.RFC3339)
		}
		endStr := ""
		if nem.EndTime > 0 {
			endStr = time.Unix(nem.EndTime, 0).UTC().Format(time.RFC3339)
		}
		targetNode := ""
		if nem.TargetNode != nil {
			targetNode = nem.TargetNode.Name
			if nem.TargetNode.IP != "" {
				targetNode += " (" + nem.TargetNode.IP + ")"
			}
		}
		stackTrace := nem.StackTrace
		if len(stackTrace) > 120 {
			stackTrace = stackTrace[:120] + "..."
		}
		rows = append(rows, []string{
			nem.ClassName,
			nem.Name,
			nem.Status,
			fmt.Sprint(nem.Duration),
			startStr,
			endStr,
			targetNode,
			stackTrace,
		})
	}
	return rows
}

// MarshalJSON implements json.Marshaler.
func (n NemesisResponse) MarshalJSON() ([]byte, error) {
	return json.Marshal(n.Nemeses)
}

// ---------------------------------------------------------------------------
// RunDetails – structured "Details page" style output for run get
// ---------------------------------------------------------------------------

// RunDetails renders an SCTTestRun as two side-by-side sections mirroring the
// Argus web UI "Details" tab: Run Details on the left, System Information on
// the right.  Events and nemesis data are excluded — use the dedicated
// `run events` and `run nemesis` sub-commands instead.
type RunDetails struct {
	Run SCTTestRun
}

// Headers implements output.Tabular.
func (RunDetails) Headers() []string {
	return []string{"Field", "Value"}
}

// Rows implements output.Tabular.
func (d RunDetails) Rows() [][]string {
	r := d.Run

	// Duration: compute from start/end when available.
	duration := ""
	if r.StartTime != "" && r.EndTime != "" {
		if start, err1 := time.Parse("2006-01-02T15:04:05.000000", r.StartTime); err1 == nil {
			if end, err2 := time.Parse("2006-01-02T15:04:05.000000", r.EndTime); err2 == nil {
				dur := end.Sub(start).Round(time.Minute)
				duration = dur.String()
			}
		}
	}

	// Cloud setup summary.
	backend := ""
	region := strings.Join(r.RegionName, ", ")
	imageID := ""
	instanceType := ""
	nodeAmount := 0
	if r.CloudSetup != nil {
		backend = r.CloudSetup.Backend
		if r.CloudSetup.DBNode != nil {
			imageID = r.CloudSetup.DBNode.ImageID
			instanceType = r.CloudSetup.DBNode.InstanceType
			nodeAmount = r.CloudSetup.DBNode.NodeAmount
		}
	}

	// Event summary: count per severity.
	eventSummary := ""
	if len(r.Events) > 0 {
		parts := make([]string, 0, len(r.Events))
		for _, ev := range r.Events {
			parts = append(parts, fmt.Sprintf("%s: %d", ev.Severity, ev.EventAmount))
		}
		eventSummary = strings.Join(parts, "  |  ")
	}

	// Nemesis summary: count by status.
	nemesisSummary := ""
	if len(r.NemesisData) > 0 {
		statusCount := make(map[string]int)
		for _, nem := range r.NemesisData {
			statusCount[nem.Status]++
		}
		parts := make([]string, 0, len(statusCount))
		for status, count := range statusCount {
			parts = append(parts, fmt.Sprintf("%s: %d", status, count))
		}
		sort.Strings(parts)
		nemesisSummary = fmt.Sprintf("total: %d  (%s)", len(r.NemesisData), strings.Join(parts, ", "))
	}

	rows := [][]string{
		{"--- Run Details ---", ""},
		{"Release", r.ReleaseID},
		{"Group", r.GroupID},
		{"Test", r.TestName},
		{"Test Method", r.TestMethod},
		{"Id", r.ID},
		{"Status", string(r.Status)},
		{"Investigation Status", string(r.InvestigationStatus)},
		{"Start Time", r.StartTime},
		{"End Time", r.EndTime},
		{"Duration", duration},
		{"Custom Stress Duration", fmt.Sprint(r.StressDuration)},
		{"Started By", r.StartedBy},
		{"Build Job", r.BuildJobURL},
		{"Scylla Version", r.ScyllaVersion},
		{"Product Version", r.ProductVersion},
		{"--- System Information ---", ""},
		{"Backend", backend},
		{"Region", region},
		{"Image Id", imageID},
		{"SCT Commit SHA", r.ScmRevisionID},
		{"SCT Repository", r.OriginURL},
		{"SCT Branch Name", r.BranchName},
		{"Kernel Version", ""},
		{"Instance Type", instanceType},
		{"Node Amount", fmt.Sprint(nodeAmount)},
		{"--- Summary ---", ""},
		{"Events", eventSummary},
		{"Nemesis", nemesisSummary},
	}

	// Remove empty rows to keep output clean.
	out := rows[:0]
	for _, row := range rows {
		if row[0] != "" {
			out = append(out, row)
		}
	}
	return out
}

// MarshalJSON implements json.Marshaler so the JSON outputter serialises the
// underlying run directly.
func (d RunDetails) MarshalJSON() ([]byte, error) {
	return json.Marshal(d.Run)
}
