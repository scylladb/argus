// Package models contains typed Go request/response structs for the Argus backend API.
//
// The backend always returns HTTP 200. The top-level shape is:
//
//	{"status": "ok",    "response": <payload>}
//	{"status": "error", "response": {"trace_id": "...", "exception": "...", "message": "...", "arguments": [...]}}
package models

import "encoding/json"

// APIResponse is the generic envelope returned by every Argus API endpoint.
// Use [APIResponse.IsError] to distinguish success from failure before
// unmarshalling [APIResponse.Response] into the expected payload type T.
type APIResponse[T any] struct {
	Status   string          `json:"status"`
	Response json.RawMessage `json:"response"`
}

// IsError reports whether the backend returned a status of "error".
func (r *APIResponse[T]) IsError() bool {
	return r.Status != "ok"
}

// Decode unmarshals the response payload into T and returns it together with
// any JSON decoding error.
func (r *APIResponse[T]) Decode() (T, error) {
	var v T
	err := json.Unmarshal(r.Response, &v)
	return v, err
}

// DecodeError unmarshals the response payload as an [ErrorBody].
// Call this only when [APIResponse.IsError] is true.
func (r *APIResponse[T]) DecodeError() (ErrorBody, error) {
	var e ErrorBody
	err := json.Unmarshal(r.Response, &e)
	return e, err
}

// ErrorBody is the payload inside an error envelope.
type ErrorBody struct {
	TraceID   string   `json:"trace_id"`
	Exception string   `json:"exception"`
	Message   string   `json:"message"`
	Arguments []string `json:"arguments"`
}
