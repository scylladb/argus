package main

import (
	"context"
	"errors"
	"fmt"
	"os"
	"os/signal"
	"syscall"

	"github.com/scylladb/argus/cli/cmd"
)

const (
	FailureExitCode   = 1
	TimeoutExitCode   = 124
	InterruptExitCode = 130
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

	path, upgraded := cmd.AutoUpgrade(ctx, os.Args, os.Stderr)
	// A signal during the update check stops the command before it starts.
	if ctx.Err() != nil {
		cancel()
		os.Exit(InterruptExitCode)
	}
	if upgraded {
		env := append(os.Environ(), cmd.EnvUpgradedFrom+"="+version)
		// Exec returns only on failure. The command then runs in this process.
		if err := syscall.Exec(path, os.Args, env); err != nil {
			_, _ = fmt.Fprintf(os.Stderr, "argus: cannot start the upgraded binary: %v\n", err)
		}
	}

	if err := cmd.ExecuteContext(ctx); err != nil && !errors.Is(err, context.Canceled) {
		cancel()

		if errors.Is(err, context.DeadlineExceeded) {
			os.Exit(TimeoutExitCode)
		}

		os.Exit(FailureExitCode)
	}
}
