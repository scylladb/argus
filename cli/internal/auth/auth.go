package auth

import (
	"context"
	"errors"
	"io"
	"os"
	"os/exec"
	"time"
)

const (
	// killGrace is the window between SIGTERM and SIGKILL when the caller's
	// context is cancelled.
	killGrace = 5 * time.Second
)

// Sentinel errors returned by the auth package.
var (
	// ErrStartingProcess is returned when the cloudflared process cannot be
	// started.
	ErrStartingProcess = errors.New("auth: starting cloudflared process")

	// ErrProcessExited is returned when cloudflared exits with a non-zero
	// status code.
	ErrProcessExited = errors.New("auth: cloudflared process exited with error")
)

type CloudflareService struct {
	// binaryPath is the path to the cloudflared executable.
	binaryPath string

	// stdout and stderr are the writers the child process writes to.
	// They default to os.Stdout / os.Stderr.
	stdout io.Writer
	stderr io.Writer
}

// CloudflareOption is a functional option for [NewCloudflareService].
type CloudflareOption func(*CloudflareService)

// WithBinaryPath overrides the path to the cloudflared binary.
// Primarily useful in tests to inject a fake executable.
func WithBinaryPath(p string) CloudflareOption {
	return func(s *CloudflareService) { s.binaryPath = p }
}

// WithStdout redirects the child process's stdout to w.
func WithStdout(w io.Writer) CloudflareOption {
	return func(s *CloudflareService) { s.stdout = w }
}

// WithStderr redirects the child process's stderr to w.
func WithStderr(w io.Writer) CloudflareOption {
	return func(s *CloudflareService) { s.stderr = w }
}

// NewCloudflareService constructs a CloudflareService that will run the
// cloudflared binary at binaryPath to open a Cloudflare Access tunnel.
func NewCloudflareService(binaryPath string, opts ...CloudflareOption) *CloudflareService {
	s := &CloudflareService{
		binaryPath: binaryPath,
		stdout:     os.Stdout,
		stderr:     os.Stderr,
	}

	for _, o := range opts {
		o(s)
	}

	return s
}

func (s *CloudflareService) Run(ctx context.Context) error {
	cmd := exec.CommandContext(ctx, s.binaryPath) //nolint:gosec // binaryPath is resolved by CloudflaredService, not user input
	cmd.Stdout = s.stdout
	cmd.Stderr = s.stderr

	// Replace the default behaviour of exec.CommandContext, which sends
	// SIGKILL immediately when ctx is done.  We want a graceful shutdown
	// window first.
	cmd.Cancel = func() error {
		if cmd.Process == nil {
			return nil
		}
		return cmd.Process.Signal(os.Interrupt)
	}
	cmd.WaitDelay = killGrace

	if err := cmd.Start(); err != nil {
		return errors.Join(ErrStartingProcess, err)
	}

	if err := cmd.Wait(); err != nil {
		// Context cancellation: the process was killed on our behalf — treat
		// that as a clean stop rather than an error.
		if ctx.Err() != nil {
			return ctx.Err()
		}
		return errors.Join(ErrProcessExited, err)
	}

	return nil
}
