package models_test

import (
	"encoding/json"
	"testing"

	"github.com/scylladb/argus/cli/internal/models"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// =========================================================================
// KVTabular tests
// =========================================================================

// --------------------------------------------------------------------------
// Flat struct
// --------------------------------------------------------------------------

type flat struct {
	Name  string  `json:"name"`
	Count int     `json:"count"`
	Score float64 `json:"score"`
	OK    bool    `json:"ok"`
}

func TestKVTabular_FlatStruct(t *testing.T) {
	v := flat{Name: "alpha", Count: 42, Score: 3.14, OK: true}
	tab := models.NewKVTabular(v)

	assert.Equal(t, []string{"Key", "Value"}, tab.Headers())

	rows := tab.Rows()
	require.Len(t, rows, 4)
	assert.Equal(t, []string{"name", "alpha"}, rows[0])
	assert.Equal(t, []string{"count", "42"}, rows[1])
	assert.Equal(t, []string{"score", "3.14"}, rows[2])
	assert.Equal(t, []string{"ok", "true"}, rows[3])
}

// --------------------------------------------------------------------------
// Embedded struct (like RunBase inside SCTTestRun)
// --------------------------------------------------------------------------

type base struct {
	ID     string `json:"id"`
	Status string `json:"status"`
}

type extended struct {
	base
	Extra string `json:"extra"`
}

func TestKVTabular_EmbeddedStruct(t *testing.T) {
	v := extended{base: base{ID: "abc-123", Status: "passed"}, Extra: "info"}
	tab := models.NewKVTabular(v)

	rows := tab.Rows()
	require.Len(t, rows, 3)
	// Embedded fields are flattened – no "base." prefix.
	assert.Equal(t, []string{"id", "abc-123"}, rows[0])
	assert.Equal(t, []string{"status", "passed"}, rows[1])
	assert.Equal(t, []string{"extra", "info"}, rows[2])
}

// --------------------------------------------------------------------------
// Nested struct – dot notation
// --------------------------------------------------------------------------

type inner struct {
	ImageID      string `json:"image_id"`
	InstanceType string `json:"instance_type"`
}

type outer struct {
	Name string `json:"name"`
	Node inner  `json:"node"`
}

func TestKVTabular_NestedStruct(t *testing.T) {
	v := outer{Name: "test", Node: inner{ImageID: "ami-123", InstanceType: "i3.xlarge"}}
	tab := models.NewKVTabular(v)

	rows := tab.Rows()
	require.Len(t, rows, 3)
	assert.Equal(t, []string{"name", "test"}, rows[0])
	assert.Equal(t, []string{"node.image_id", "ami-123"}, rows[1])
	assert.Equal(t, []string{"node.instance_type", "i3.xlarge"}, rows[2])
}

// --------------------------------------------------------------------------
// Pointer to struct (nil and non-nil)
// --------------------------------------------------------------------------

type withPtrStruct struct {
	Name string `json:"name"`
	Node *inner `json:"node"`
}

func TestKVTabular_PointerStruct_NonNil(t *testing.T) {
	v := withPtrStruct{Name: "test", Node: &inner{ImageID: "ami-456", InstanceType: "m5.large"}}
	tab := models.NewKVTabular(v)

	rows := tab.Rows()
	require.Len(t, rows, 3)
	assert.Equal(t, []string{"name", "test"}, rows[0])
	assert.Equal(t, []string{"node.image_id", "ami-456"}, rows[1])
	assert.Equal(t, []string{"node.instance_type", "m5.large"}, rows[2])
}

func TestKVTabular_PointerStruct_Nil(t *testing.T) {
	v := withPtrStruct{Name: "test", Node: nil}
	tab := models.NewKVTabular(v)

	rows := tab.Rows()
	require.Len(t, rows, 1)
	assert.Equal(t, []string{"name", "test"}, rows[0])
}

// --------------------------------------------------------------------------
// Slice of scalars
// --------------------------------------------------------------------------

type withSlice struct {
	Name  string   `json:"name"`
	Files []string `json:"files"`
}

func TestKVTabular_SliceOfScalars(t *testing.T) {
	v := withSlice{Name: "test", Files: []string{"a.yaml", "b.yaml"}}
	tab := models.NewKVTabular(v)

	rows := tab.Rows()
	require.Len(t, rows, 3)
	assert.Equal(t, []string{"name", "test"}, rows[0])
	assert.Equal(t, []string{"files.0", "a.yaml"}, rows[1])
	assert.Equal(t, []string{"files.1", "b.yaml"}, rows[2])
}

func TestKVTabular_SliceEmpty(t *testing.T) {
	v := withSlice{Name: "test", Files: []string{}}
	tab := models.NewKVTabular(v)

	rows := tab.Rows()
	require.Len(t, rows, 1)
	assert.Equal(t, []string{"name", "test"}, rows[0])
}

// --------------------------------------------------------------------------
// Slice of structs
// --------------------------------------------------------------------------

type pkg struct {
	Name    string `json:"name"`
	Version string `json:"version"`
}

type withStructSlice struct {
	Packages []pkg `json:"packages"`
}

func TestKVTabular_SliceOfStructs(t *testing.T) {
	v := withStructSlice{Packages: []pkg{
		{Name: "scylla-server", Version: "5.4.0"},
		{Name: "scylla-tools", Version: "5.4.1"},
	}}
	tab := models.NewKVTabular(v)

	rows := tab.Rows()
	require.Len(t, rows, 4)
	assert.Equal(t, []string{"packages.0.name", "scylla-server"}, rows[0])
	assert.Equal(t, []string{"packages.0.version", "5.4.0"}, rows[1])
	assert.Equal(t, []string{"packages.1.name", "scylla-tools"}, rows[2])
	assert.Equal(t, []string{"packages.1.version", "5.4.1"}, rows[3])
}

// --------------------------------------------------------------------------
// Map
// --------------------------------------------------------------------------

type withMap struct {
	Name string            `json:"name"`
	Meta map[string]string `json:"meta"`
}

func TestKVTabular_Map(t *testing.T) {
	v := withMap{Name: "test", Meta: map[string]string{"region": "us-east-1", "env": "prod"}}
	tab := models.NewKVTabular(v)

	rows := tab.Rows()
	require.Len(t, rows, 3)
	assert.Equal(t, []string{"name", "test"}, rows[0])
	// Map keys are sorted.
	assert.Equal(t, []string{"meta.env", "prod"}, rows[1])
	assert.Equal(t, []string{"meta.region", "us-east-1"}, rows[2])
}

func TestKVTabular_MapEmpty(t *testing.T) {
	v := withMap{Name: "test", Meta: map[string]string{}}
	tab := models.NewKVTabular(v)

	rows := tab.Rows()
	require.Len(t, rows, 1)
	assert.Equal(t, []string{"name", "test"}, rows[0])
}

// --------------------------------------------------------------------------
// json:"-" fields are excluded
// --------------------------------------------------------------------------

type withIgnored struct {
	Visible string `json:"visible"`
	Hidden  string `json:"-"`
}

func TestKVTabular_JSONDashSkipped(t *testing.T) {
	v := withIgnored{Visible: "yes", Hidden: "no"}
	tab := models.NewKVTabular(v)

	rows := tab.Rows()
	require.Len(t, rows, 1)
	assert.Equal(t, []string{"visible", "yes"}, rows[0])
}

// --------------------------------------------------------------------------
// Scalar pointer field
// --------------------------------------------------------------------------

type withScalarPtr struct {
	Name  string `json:"name"`
	Value *int   `json:"value"`
}

func TestKVTabular_ScalarPointer_NonNil(t *testing.T) {
	val := 99
	v := withScalarPtr{Name: "test", Value: &val}
	tab := models.NewKVTabular(v)

	rows := tab.Rows()
	require.Len(t, rows, 2)
	assert.Equal(t, []string{"name", "test"}, rows[0])
	assert.Equal(t, []string{"value", "99"}, rows[1])
}

func TestKVTabular_ScalarPointer_Nil(t *testing.T) {
	v := withScalarPtr{Name: "test", Value: nil}
	tab := models.NewKVTabular(v)

	rows := tab.Rows()
	require.Len(t, rows, 1)
	assert.Equal(t, []string{"name", "test"}, rows[0])
}

// --------------------------------------------------------------------------
// MarshalJSON – passthrough to original value
// --------------------------------------------------------------------------

func TestKVTabular_MarshalJSON(t *testing.T) {
	v := flat{Name: "alpha", Count: 42, Score: 3.14, OK: true}
	tab := models.NewKVTabular(v)

	raw, err := json.Marshal(tab)
	require.NoError(t, err)

	// Should produce the same JSON as marshalling v directly.
	expected, _ := json.Marshal(v)
	assert.JSONEq(t, string(expected), string(raw))
}

// --------------------------------------------------------------------------
// RunMeta integration
// --------------------------------------------------------------------------

func TestKVTabular_RunMeta(t *testing.T) {
	v := models.RunMeta{
		ID:                  "11111111-1111-1111-1111-111111111111",
		TestID:              "22222222-2222-2222-2222-222222222222",
		Status:              models.TestStatusPassed,
		StartTime:           "2024-06-15T10:00:00.000Z",
		BuildID:             "test-build",
		InvestigationStatus: models.TestInvestigationStatusNotInvestigated,
		Heartbeat:           1718445000,
	}
	tab := models.NewKVTabular(v)

	assert.Equal(t, []string{"Key", "Value"}, tab.Headers())

	rows := tab.Rows()
	// RunMeta has 12 fields, all scalar → 12 rows.
	require.Len(t, rows, 12)
	assert.Equal(t, "id", rows[0][0])
	assert.Equal(t, "11111111-1111-1111-1111-111111111111", rows[0][1])
}

// =========================================================================
// TabularSlice tests (multi-column wide table for lists)
// =========================================================================

func TestTabularSlice(t *testing.T) {
	items := []flat{
		{Name: "a", Count: 1, Score: 1.1, OK: true},
		{Name: "b", Count: 2, Score: 2.2, OK: false},
	}
	tab := models.NewTabularSlice(items)

	assert.Equal(t, []string{"Name", "Count", "Score", "Ok"}, tab.Headers())

	rows := tab.Rows()
	require.Len(t, rows, 2)
	assert.Equal(t, []string{"a", "1", "1.1", "true"}, rows[0])
	assert.Equal(t, []string{"b", "2", "2.2", "false"}, rows[1])
}

func TestTabularSlice_Empty(t *testing.T) {
	tab := models.NewTabularSlice([]flat{})

	assert.Equal(t, []string{"Name", "Count", "Score", "Ok"}, tab.Headers())
	assert.Empty(t, tab.Rows())
}

func TestTabularSlice_MarshalJSON(t *testing.T) {
	items := []flat{
		{Name: "a", Count: 1, Score: 1.1, OK: true},
	}
	tab := models.NewTabularSlice(items)

	raw, err := json.Marshal(tab)
	require.NoError(t, err)

	expected, _ := json.Marshal(items)
	assert.JSONEq(t, string(expected), string(raw))
}

func TestTabularSlice_RunMeta(t *testing.T) {
	items := []models.RunMeta{
		{
			ID:                  "11111111-1111-1111-1111-111111111111",
			TestID:              "22222222-2222-2222-2222-222222222222",
			GroupID:             "33333333-3333-3333-3333-333333333333",
			ReleaseID:           "44444444-4444-4444-4444-444444444444",
			Status:              models.TestStatusPassed,
			StartTime:           "2024-06-15T10:00:00.000Z",
			BuildJobURL:         "https://jenkins.example.com/job/test/1",
			BuildID:             "test-build",
			Assignee:            "",
			EndTime:             "2024-06-15T10:30:00.000Z",
			InvestigationStatus: models.TestInvestigationStatusNotInvestigated,
			Heartbeat:           1718445000,
		},
	}
	tab := models.NewTabularSlice(items)

	headers := tab.Headers()
	assert.Contains(t, headers, "Id")
	assert.Contains(t, headers, "Status")
	assert.Contains(t, headers, "Build Job Url")

	rows := tab.Rows()
	require.Len(t, rows, 1)
	assert.Equal(t, "11111111-1111-1111-1111-111111111111", rows[0][0])
}
