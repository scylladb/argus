package models_test

import (
	"encoding/json"
	"testing"

	"github.com/scylladb/argus/cli/internal/models"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// --------------------------------------------------------------------------
// helpers
// --------------------------------------------------------------------------

// buildEnvelope constructs the raw JSON for an APIResponse envelope.
func buildEnvelope(t *testing.T, status string, response any) []byte {
	t.Helper()
	raw, err := json.Marshal(response)
	require.NoError(t, err)
	env := struct {
		Status   string          `json:"status"`
		Response json.RawMessage `json:"response"`
	}{
		Status:   status,
		Response: raw,
	}
	b, err := json.Marshal(env)
	require.NoError(t, err)
	return b
}

// unmarshalEnvelope parses raw JSON into an APIResponse[T].
func unmarshalEnvelope[T any](t *testing.T, data []byte) *models.APIResponse[T] {
	t.Helper()
	var env models.APIResponse[T]
	require.NoError(t, json.Unmarshal(data, &env))
	return &env
}

// --------------------------------------------------------------------------
// APIResponse.IsError
// --------------------------------------------------------------------------

func TestAPIResponse_IsError_OK(t *testing.T) {
	t.Parallel()

	data := buildEnvelope(t, "ok", map[string]string{"id": "1"})
	env := unmarshalEnvelope[map[string]string](t, data)

	assert.False(t, env.IsError(), `status "ok" should not be an error`)
}

func TestAPIResponse_IsError_Error(t *testing.T) {
	t.Parallel()

	data := buildEnvelope(t, "error", models.ErrorBody{Message: "boom"})
	env := unmarshalEnvelope[map[string]string](t, data)

	assert.True(t, env.IsError(), `status "error" should be an error`)
}

func TestAPIResponse_IsError_OtherStatus(t *testing.T) {
	t.Parallel()

	// Any status that is not "ok" is treated as an error.
	data := buildEnvelope(t, "unknown", nil)
	env := unmarshalEnvelope[map[string]string](t, data)

	assert.True(t, env.IsError(), `non-"ok" status should be treated as an error`)
}

// --------------------------------------------------------------------------
// APIResponse.Decode
// --------------------------------------------------------------------------

type samplePayload struct {
	ID   string `json:"id"`
	Name string `json:"name"`
}

func TestAPIResponse_Decode_Success(t *testing.T) {
	t.Parallel()

	want := samplePayload{ID: "abc", Name: "test"}
	data := buildEnvelope(t, "ok", want)
	env := unmarshalEnvelope[samplePayload](t, data)

	got, err := env.Decode()
	require.NoError(t, err)
	assert.Equal(t, want, got)
}

func TestAPIResponse_Decode_TypeMismatch(t *testing.T) {
	t.Parallel()

	// The response contains a string, but we try to decode into a struct with
	// an int field that doesn't match — this should produce a JSON error.
	type strictInt struct {
		Count int `json:"count"`
	}
	// Provide a response where "count" is a string, not a number.
	data := buildEnvelope(t, "ok", map[string]string{"count": "not-a-number"})
	env := unmarshalEnvelope[strictInt](t, data)

	_, err := env.Decode()
	require.Error(t, err, "type mismatch should produce a JSON decode error")
}

func TestAPIResponse_Decode_MalformedJSON(t *testing.T) {
	t.Parallel()

	// Build an envelope where the response is a JSON number (123456) rather
	// than an object matching samplePayload — Decode must return an error.
	env := &models.APIResponse[samplePayload]{}
	require.NoError(t, json.Unmarshal([]byte(`{"status":"ok","response":123456}`), env))

	_, err := env.Decode()
	require.Error(t, err, "decoding a number as samplePayload should fail")
}

// --------------------------------------------------------------------------
// APIResponse.DecodeError
// --------------------------------------------------------------------------

func TestAPIResponse_DecodeError_Success(t *testing.T) {
	t.Parallel()

	wantBody := models.ErrorBody{
		TraceID:   "trace-123",
		Exception: "SomeException",
		Message:   "something went wrong",
		Arguments: []string{"arg1", "arg2"},
	}
	data := buildEnvelope(t, "error", wantBody)
	env := unmarshalEnvelope[samplePayload](t, data)

	got, err := env.DecodeError()
	require.NoError(t, err)
	assert.Equal(t, wantBody, got)
}

func TestAPIResponse_DecodeError_MalformedJSON(t *testing.T) {
	t.Parallel()

	// Build an envelope where the response is a number, not an ErrorBody object.
	data := buildEnvelope(t, "error", 42)
	env := unmarshalEnvelope[samplePayload](t, data)

	_, err := env.DecodeError()
	require.Error(t, err, "decoding a number as ErrorBody should fail")
}

// --------------------------------------------------------------------------
// ErrorBody JSON round-trip
// --------------------------------------------------------------------------

func TestErrorBody_JSONRoundTrip(t *testing.T) {
	t.Parallel()

	original := models.ErrorBody{
		TraceID:   "trace-456",
		Exception: "AnotherException",
		Message:   "detailed message",
		Arguments: []string{"a", "b", "c"},
	}

	raw, err := json.Marshal(original)
	require.NoError(t, err)

	var got models.ErrorBody
	require.NoError(t, json.Unmarshal(raw, &got))

	assert.Equal(t, original, got)
}

func TestErrorBody_JSONKeys(t *testing.T) {
	t.Parallel()

	b := models.ErrorBody{
		TraceID:   "tid",
		Exception: "Ex",
		Message:   "msg",
		Arguments: []string{"x"},
	}
	raw, err := json.Marshal(b)
	require.NoError(t, err)
	s := string(raw)

	// Verify the exact JSON key names used (from the struct tags).
	assert.Contains(t, s, `"trace_id"`)
	assert.Contains(t, s, `"exception"`)
	assert.Contains(t, s, `"message"`)
	assert.Contains(t, s, `"arguments"`)
}

func TestErrorBody_EmptyArguments(t *testing.T) {
	t.Parallel()

	original := models.ErrorBody{
		TraceID:   "t",
		Exception: "E",
		Message:   "m",
		Arguments: nil,
	}

	raw, err := json.Marshal(original)
	require.NoError(t, err)

	var got models.ErrorBody
	require.NoError(t, json.Unmarshal(raw, &got))

	// nil and empty slice are both acceptable here.
	assert.Equal(t, original.TraceID, got.TraceID)
	assert.Equal(t, original.Message, got.Message)
}
