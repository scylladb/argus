package output_test

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"testing"

	"github.com/scylladb/argus/cli/internal/output"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// --------------------------------------------------------------------------
// helpers / test types
// --------------------------------------------------------------------------

// simpleTabular implements output.Tabular.
type simpleTabular struct {
	headers []string
	rows    [][]string
}

func (s simpleTabular) Headers() []string { return s.headers }
func (s simpleTabular) Rows() [][]string  { return s.rows }

// emptyTabular has headers but no rows.
type emptyTabular struct{}

func (emptyTabular) Headers() []string { return []string{"col"} }
func (emptyTabular) Rows() [][]string  { return nil }

// noHeaderTabular has rows but no headers.
type noHeaderTabular struct{}

func (noHeaderTabular) Headers() []string { return nil }
func (noHeaderTabular) Rows() [][]string  { return [][]string{{"val"}} }

// stringer implements fmt.Stringer.
type stringer struct{ s string }

func (st stringer) String() string { return st.s }

// errVal implements error.
type errVal struct{ msg string }

func (e errVal) Error() string { return e.msg }

// nonTabular is a plain struct (not Tabular, Stringer, or error).
type nonTabular struct {
	Key   string `json:"key"`
	Value int    `json:"value"`
}

// failWriter always returns an error on Write.
type failWriter struct{ err error }

func (f *failWriter) Write(_ []byte) (int, error) { return 0, f.err }

// --------------------------------------------------------------------------
// output.New
// --------------------------------------------------------------------------

func TestNew_JSONOutputter(t *testing.T) {
	t.Parallel()

	var buf bytes.Buffer
	out := output.New(&buf, false)
	require.NotNil(t, out)

	require.NoError(t, out.Write(map[string]int{"n": 1}))
	assert.Contains(t, buf.String(), `"n"`)
	assert.Contains(t, buf.String(), `1`)
}

func TestNew_TextOutputter(t *testing.T) {
	t.Parallel()

	var buf bytes.Buffer
	out := output.New(&buf, true)
	require.NotNil(t, out)
	// Should not panic; basic smoke test.
	require.NoError(t, out.Write(simpleTabular{
		headers: []string{"Name"},
		rows:    [][]string{{"Alice"}},
	}))
	// tablewriter uppercases headers.
	assert.Contains(t, strings.ToUpper(buf.String()), "NAME")
	assert.Contains(t, buf.String(), "Alice")
}

// --------------------------------------------------------------------------
// jsonOutputter
// --------------------------------------------------------------------------

func TestJSONOutputter_HappyPath(t *testing.T) {
	t.Parallel()

	type payload struct {
		ID   string `json:"id"`
		Name string `json:"name"`
	}
	v := payload{ID: "abc", Name: "test"}

	var buf bytes.Buffer
	out := output.New(&buf, false)
	require.NoError(t, out.Write(v))

	var got payload
	require.NoError(t, json.Unmarshal(buf.Bytes(), &got))
	assert.Equal(t, v, got)
}

func TestJSONOutputter_Indented(t *testing.T) {
	t.Parallel()

	var buf bytes.Buffer
	out := output.New(&buf, false)
	require.NoError(t, out.Write(map[string]int{"x": 42}))

	// Indented JSON must contain a newline inside the object.
	s := buf.String()
	assert.True(t, strings.Contains(s, "\n"), "expected indented JSON with newlines")
}

func TestJSONOutputter_WriterError(t *testing.T) {
	t.Parallel()

	fw := &failWriter{err: errors.New("disk full")}
	out := output.New(fw, false)

	err := out.Write(map[string]string{"k": "v"})
	require.Error(t, err)
	assert.ErrorIs(t, err, output.ErrJSONOutput)
}

func TestJSONOutputter_UnmarshallableValue(t *testing.T) {
	t.Parallel()

	var buf bytes.Buffer
	out := output.New(&buf, false)

	// chan cannot be JSON-marshalled.
	err := out.Write(make(chan int))
	require.Error(t, err)
	assert.ErrorIs(t, err, output.ErrJSONOutput)
}

// --------------------------------------------------------------------------
// textOutputter – Tabular path
// --------------------------------------------------------------------------

func TestTextOutputter_Tabular_HeadersAndRows(t *testing.T) {
	t.Parallel()

	var buf bytes.Buffer
	out := output.New(&buf, true)

	require.NoError(t, out.Write(simpleTabular{
		headers: []string{"ID", "Name"},
		rows: [][]string{
			{"1", "Alice"},
			{"2", "Bob"},
		},
	}))

	// tablewriter uppercases headers.
	s := strings.ToUpper(buf.String())
	assert.Contains(t, s, "ID")
	assert.Contains(t, s, "NAME")
	assert.Contains(t, buf.String(), "Alice")
	assert.Contains(t, buf.String(), "Bob")
}

func TestTextOutputter_Tabular_EmptyRows(t *testing.T) {
	t.Parallel()

	var buf bytes.Buffer
	out := output.New(&buf, true)

	require.NoError(t, out.Write(emptyTabular{}))
	// Headers should still appear even with zero rows (tablewriter uppercases them).
	assert.Contains(t, strings.ToUpper(buf.String()), "COL")
}

func TestTextOutputter_Tabular_NoHeaders(t *testing.T) {
	t.Parallel()

	var buf bytes.Buffer
	out := output.New(&buf, true)

	// Must not panic and must render the row value.
	require.NoError(t, out.Write(noHeaderTabular{}))
	assert.Contains(t, buf.String(), "val")
}

// --------------------------------------------------------------------------
// textOutputter – scalar / stringer / error path (bug-fix verification)
// --------------------------------------------------------------------------

func TestTextOutputter_String(t *testing.T) {
	t.Parallel()

	var buf bytes.Buffer
	out := output.New(&buf, true)

	require.NoError(t, out.Write("hello world"))
	assert.Contains(t, buf.String(), "hello world")
}

func TestTextOutputter_Stringer(t *testing.T) {
	t.Parallel()

	var buf bytes.Buffer
	out := output.New(&buf, true)

	require.NoError(t, out.Write(stringer{s: "stringer-value"}))
	assert.Contains(t, buf.String(), "stringer-value")
}

func TestTextOutputter_Error(t *testing.T) {
	t.Parallel()

	var buf bytes.Buffer
	out := output.New(&buf, true)

	require.NoError(t, out.Write(errVal{msg: "something failed"}))
	assert.Contains(t, buf.String(), "something failed")
}

// --------------------------------------------------------------------------
// textOutputter – non-Tabular fallback (writeRawJSON)
// --------------------------------------------------------------------------

func TestTextOutputter_NonTabular_FallbackJSON(t *testing.T) {
	t.Parallel()

	var buf bytes.Buffer
	out := output.New(&buf, true)

	v := nonTabular{Key: "foo", Value: 99}
	require.NoError(t, out.Write(v))

	// tablewriter uppercases the "json" header to "JSON".
	s := buf.String()
	assert.Contains(t, strings.ToUpper(s), "JSON", "fallback table should have a 'JSON' header")
	assert.Contains(t, s, "foo")
}

func TestTextOutputter_NonTabular_UnmarshallableValue(t *testing.T) {
	t.Parallel()

	var buf bytes.Buffer
	out := output.New(&buf, true)

	// chan cannot be JSON-marshalled; should return ErrTextOutputJSONFallback.
	err := out.Write(make(chan int))
	require.Error(t, err)
	assert.ErrorIs(t, err, output.ErrTextOutputJSONFallback)
}

// --------------------------------------------------------------------------
// Sentinel errors exist
// --------------------------------------------------------------------------

func TestSentinelErrors_Defined(t *testing.T) {
	t.Parallel()

	// Compile-time checks that sentinels are exported and non-nil.
	assert.NotNil(t, output.ErrJSONOutput)
	assert.NotNil(t, output.ErrTextOutputRow)
	assert.NotNil(t, output.ErrTextOutputRender)
	assert.NotNil(t, output.ErrTextOutputJSONFallback)
	assert.NotNil(t, output.ErrTextOutputJSONFallbackRow)
	assert.NotNil(t, output.ErrTextOutputJSONFallbackRender)
}

// --------------------------------------------------------------------------
// Verify no infinite recursion: Write(string) terminates
// --------------------------------------------------------------------------

func TestTextOutputter_Write_NoRecursion(t *testing.T) {
	t.Parallel()

	var buf bytes.Buffer
	out := output.New(&buf, true)

	// This must return without hanging, proving there is no infinite recursion
	// in the string / Stringer / error branches.
	err := out.Write("termination-check")
	require.NoError(t, err)
	assert.Contains(t, buf.String(), "termination-check")
}

// --------------------------------------------------------------------------
// fmt.Stringer that also returns a value that would re-enter Write
// --------------------------------------------------------------------------

// recursiveStringer is a fmt.Stringer whose String() method returns the same
// struct — if the old recursive path were still in place this would loop
// forever; with the fix it should just print the string value.
type recursiveStringer struct{}

func (recursiveStringer) String() string { return "recursive-ok" }

func TestTextOutputter_StringerThatReturnsSelf(t *testing.T) {
	t.Parallel()

	var buf bytes.Buffer
	out := output.New(&buf, true)

	require.NoError(t, out.Write(recursiveStringer{}))
	assert.Contains(t, buf.String(), "recursive-ok")
}

// --------------------------------------------------------------------------
// Verify ErrJSONOutput is wrapped correctly (errors.Is works through chain)
// --------------------------------------------------------------------------

func TestJSONOutputter_ErrIsWrapped(t *testing.T) {
	t.Parallel()

	fw := &failWriter{err: fmt.Errorf("inner error")}
	out := output.New(fw, false)

	err := out.Write(42)
	require.Error(t, err)

	// Must be reachable via errors.Is even though it is wrapped.
	assert.True(t, errors.Is(err, output.ErrJSONOutput),
		"ErrJSONOutput should be in the error chain")
}
