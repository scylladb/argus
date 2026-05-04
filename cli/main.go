package main

import (
	"context"
	"errors"
	"os"
	"os/signal"
	"syscall"

	"github.com/scylladb/argus/cli/cmd"
)

const (
	FailureExitCode = 1
	TimeoutExitCode = 124
)

// Version metadata injected at build time via GoReleaser ldflags:
//
//	-X main.version={{ .Version }}
//	-X main.commit={{ .Commit }}
//	-X main.date={{ .Date }}
//
// When building locally (go build .) these remain at their zero values.
var (
	version = "dev"
	commit  = "none"
	date    = "unknown"
)

func main() {
	ctx, cancel := signal.NotifyContext(context.Background(),
		os.Interrupt,
		syscall.SIGTERM,
		syscall.SIGINT,
	)
	defer cancel()

	cmd.SetVersionInfo(version, commit, date)

	if err := cmd.ExecuteContext(ctx); err != nil && !errors.Is(err, context.Canceled) {
		cancel()

		if errors.Is(err, context.DeadlineExceeded) {
			os.Exit(TimeoutExitCode)
		}

		os.Exit(FailureExitCode)
	}
}
