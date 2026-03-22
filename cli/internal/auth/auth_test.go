package auth_test

import (
	"bytes"
	"context"
	"os"
	"os/exec"
	"path/filepath"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/scylladb/argus/cli/internal/auth"
)

// TestMain allows this test binary to act as a fake cloudflared executable
// when the FAKE_CLOUDFLARED env var is set.  This avoids any dependency on
// external binaries while still exercising the real os/exec path.
func TestMain(m *testing.M) {
	switch os.Getenv("FAKE_CLOUDFLARED") {
	case "exit0":
		// Simulate a successful run.
		os.Exit(0)
	case "exit1":
		// Simulate a failure.
		os.Exit(1)
	case "hang":
		// Block until killed.
		select {}
	}

	os.Exit(m.Run())
}

// selfExe returns the path to the currently running test binary, which we
// re-invoke with FAKE_CLOUDFLARED set to act as the fake cloudflared.
func selfExe(t *testing.T) string {
	t.Helper()
	exe, err := os.Executable()
	require.NoError(t, err)
	return exe
}

// fakeCloudflareService builds an auth.CloudflareService that uses the test
// binary itself as the cloudflared binary, with FAKE_CLOUDFLARED controlling
// its behaviour.
func fakeCloudflareService(t *testing.T, mode string, extraOpts ...auth.CloudflareOption) *auth.CloudflareService {
	t.Helper()

	// Copy the test binary into a temp dir under the expected name so exec
	// can find it by absolute path without any PATH dependency.
	dir := t.TempDir()
	dst := filepath.Join(dir, "cloudflared")

	src, err := os.ReadFile(selfExe(t))
	require.NoError(t, err)
	require.NoError(t, os.WriteFile(dst, src, 0o755))

	// Inject the mode into the subprocess environment.
	t.Setenv("FAKE_CLOUDFLARED", mode)

	opts := append([]auth.CloudflareOption{auth.WithBinaryPath(dst)}, extraOpts...)
	return auth.NewCloudflareService(dst, opts...)
}

// ---- tests -----------------------------------------------------------------

// TestRun_ExitsCleanly verifies that Run returns nil when the process exits 0.
func TestRun_ExitsCleanly(t *testing.T) {
	svc := fakeCloudflareService(t, "exit0")
	err := svc.Run(t.Context())
	require.NoError(t, err)
}

// TestRun_ExitsWithError verifies that Run returns an error wrapping
// ErrProcessExited when the process exits non-zero.
func TestRun_ExitsWithError(t *testing.T) {
	svc := fakeCloudflareService(t, "exit1")
	err := svc.Run(t.Context())
	require.Error(t, err)
	assert.ErrorIs(t, err, auth.ErrProcessExited)
}

// TestRun_ContextCancelled verifies that cancelling the context stops the
// process and Run returns the context error, not ErrProcessExited.
func TestRun_ContextCancelled(t *testing.T) {
	var buf bytes.Buffer
	svc := fakeCloudflareService(t, "hang",
		auth.WithStdout(&buf),
		auth.WithStderr(&buf),
	)

	ctx, cancel := context.WithCancel(t.Context())

	// Start Run in a goroutine and cancel shortly after.
	errc := make(chan error, 1)
	go func() { errc <- svc.Run(ctx) }()

	// Give the process a moment to actually start before cancelling.
	time.Sleep(50 * time.Millisecond)
	cancel()

	select {
	case err := <-errc:
		require.Error(t, err)
		assert.ErrorIs(t, err, context.Canceled)
		assert.NotErrorIs(t, err, auth.ErrProcessExited)
	case <-time.After(10 * time.Second):
		t.Fatal("Run did not return after context cancellation")
	}
}

// TestRun_StdoutStderr verifies that the child process's output is forwarded
// to the configured writers. We use a tiny shell script written to a temp file
// rather than the self-exe trick, since we need actual output.
func TestRun_StdoutStderr(t *testing.T) {
	t.Parallel()
	// Build a tiny helper binary that just prints to stdout and stderr.
	dir := t.TempDir()
	src := filepath.Join(dir, "printer.go")
	require.NoError(t, os.WriteFile(src, []byte(`package main

import (
	"fmt"
	"os"
)

func main() {
	fmt.Fprintln(os.Stdout, "hello stdout")
	fmt.Fprintln(os.Stderr, "hello stderr")
}
`), 0o644))

	binPath := filepath.Join(dir, "printer")
	out, err := exec.Command("go", "build", "-o", binPath, src).CombinedOutput()
	require.NoError(t, err, "failed to build printer helper: %s", out)

	var stdout, stderr bytes.Buffer
	svc := auth.NewCloudflareService(binPath,
		auth.WithStdout(&stdout),
		auth.WithStderr(&stderr),
	)

	require.NoError(t, svc.Run(t.Context()))
	assert.Equal(t, "hello stdout\n", stdout.String())
	assert.Equal(t, "hello stderr\n", stderr.String())
}
