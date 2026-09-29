package cmd

import (
	"context"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/rs/zerolog"
	"github.com/scylladb/argus/cli/internal/api"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// earlyAnswer answers every request without reading its body, like a server
// that rejects an upload early.
type earlyAnswer struct {
	status      int
	contentType string
	body        string
}

func (e earlyAnswer) RoundTrip(req *http.Request) (*http.Response, error) {
	_ = req.Body.Close()
	contentType := e.contentType
	if contentType == "" {
		contentType = "text/plain"
	}
	return &http.Response{
		StatusCode: e.status,
		Header:     http.Header{"Content-Type": []string{contentType}},
		Body:       io.NopCloser(strings.NewReader(e.body)),
		Request:    req,
	}, nil
}

// An upload the server answers before it reads the body reports the server's
// answer, not the closed pipe it leaves behind.
func TestUploadReplay_EarlyAnswerReportsServerError(t *testing.T) {
	file := filepath.Join(t.TempDir(), "run.jsonl")
	require.NoError(t, os.WriteFile(file, []byte(`{"a":1}`+"\n"), 0o600))

	client, err := api.New("https://argus.example.com",
		api.WithHTTPClient(&http.Client{Transport: earlyAnswer{status: http.StatusRequestEntityTooLarge}}))
	require.NoError(t, err)

	_, err = uploadReplay(context.Background(), client, []string{file}, false, false, true, zerolog.Nop())
	require.Error(t, err)
	assert.ErrorContains(t, err, "413")
	assert.NotErrorIs(t, err, io.ErrClosedPipe)
}

// A success answer to an upload the server did not read in full is an error.
func TestUploadReplay_EarlySuccessIsAnError(t *testing.T) {
	file := filepath.Join(t.TempDir(), "run.jsonl")
	require.NoError(t, os.WriteFile(file, []byte(`{"a":1}`+"\n"), 0o600))

	client, err := api.New("https://argus.example.com",
		api.WithHTTPClient(&http.Client{Transport: earlyAnswer{
			status:      http.StatusOK,
			contentType: "application/json",
			body:        `{"status":"ok","response":{"total":1,"succeeded":1}}`,
		}}))
	require.NoError(t, err)

	_, err = uploadReplay(context.Background(), client, []string{file}, false, false, true, zerolog.Nop())
	require.ErrorIs(t, err, io.ErrClosedPipe)
	assert.ErrorContains(t, err, "whole archive")
}
