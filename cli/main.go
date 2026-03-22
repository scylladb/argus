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

func main() {
	ctx, cancel := signal.NotifyContext(context.Background(),
		os.Interrupt,
		syscall.SIGTERM,
		syscall.SIGINT,
	)
	defer cancel()

	if err := cmd.ExecuteContext(ctx); err != nil && !errors.Is(err, context.Canceled) {
		cancel()

		if errors.Is(err, context.DeadlineExceeded) {
			os.Exit(TimeoutExitCode)
		}

		os.Exit(FailureExitCode)
	}
}
