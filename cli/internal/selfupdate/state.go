package selfupdate

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"syscall"
	"time"
)

const (
	stateFile = "upgrade.json"
	lockFile  = "upgrade.lock"
	dayLayout = "2006-01-02"
	// lockPollInterval is the time between two attempts to take a held lock.
	lockPollInterval = 100 * time.Millisecond
)

// ErrState is returned when the state directory or the state file cannot be written.
var ErrState = errors.New("selfupdate: state")

type state struct {
	// LastCheck is the local calendar date of the last daily check.
	LastCheck string `json:"last_check"`
}

// readState returns the saved state. A missing or unreadable file gives the zero state.
func readState(dir string) state {
	var st state
	data, err := os.ReadFile(filepath.Join(dir, stateFile))
	if err != nil {
		return state{}
	}
	if err = json.Unmarshal(data, &st); err != nil {
		return state{}
	}
	return st
}

func writeState(dir string, st state) error {
	data, err := json.Marshal(st)
	if err != nil {
		return fmt.Errorf("%w: %w", ErrState, err)
	}
	tmp, err := os.CreateTemp(dir, ".upgrade-*.json")
	if err != nil {
		return fmt.Errorf("%w: %w", ErrState, err)
	}
	defer func() { _ = os.Remove(tmp.Name()) }()
	if _, err = tmp.Write(data); err != nil {
		_ = tmp.Close()
		return fmt.Errorf("%w: %w", ErrState, err)
	}
	if err = tmp.Close(); err != nil {
		return fmt.Errorf("%w: %w", ErrState, err)
	}
	if err = os.Rename(tmp.Name(), filepath.Join(dir, stateFile)); err != nil {
		return fmt.Errorf("%w: %w", ErrState, err)
	}
	return nil
}

// tryLock takes the exclusive lock of the state directory without waiting. It returns a nil
// release function when another process holds the lock.
func tryLock(dir string) (func(), error) {
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return nil, fmt.Errorf("%w: %w", ErrState, err)
	}
	f, err := os.OpenFile(filepath.Join(dir, lockFile), os.O_CREATE|os.O_RDWR, 0o600)
	if err != nil {
		return nil, fmt.Errorf("%w: %w", ErrState, err)
	}
	return tryFlock(f)
}

// tryLockBinaryDir takes the exclusive lock of the directory of the binary without waiting.
// Every user that can write to the directory takes the same lock, so one update at a time
// replaces the binary. It returns a nil release function when another process holds the lock.
func tryLockBinaryDir(dir string) (func(), error) {
	f, err := os.Open(dir)
	if err != nil {
		return nil, fmt.Errorf("%w: %w", ErrInstall, err)
	}
	return tryFlock(f)
}

// waitLockBinaryDir takes the lock of tryLockBinaryDir. It waits while another process holds
// the lock, and it stops when ctx ends.
func waitLockBinaryDir(ctx context.Context, dir string) (func(), error) {
	ticker := time.NewTicker(lockPollInterval)
	defer ticker.Stop()
	for {
		unlock, err := tryLockBinaryDir(dir)
		if err != nil || unlock != nil {
			return unlock, err
		}
		select {
		case <-ctx.Done():
			return nil, fmt.Errorf("%w: waiting for the update lock of %s: %w", ErrInstall, dir, ctx.Err())
		case <-ticker.C:
		}
	}
}

// tryFlock takes an exclusive flock on f without waiting, and closes f when it cannot.
func tryFlock(f *os.File) (func(), error) {
	if err := syscall.Flock(int(f.Fd()), syscall.LOCK_EX|syscall.LOCK_NB); err != nil {
		_ = f.Close()
		if errors.Is(err, syscall.EWOULDBLOCK) {
			return nil, nil
		}
		return nil, fmt.Errorf("%w: %w", ErrState, err)
	}
	return func() {
		_ = syscall.Flock(int(f.Fd()), syscall.LOCK_UN)
		_ = f.Close()
	}, nil
}
