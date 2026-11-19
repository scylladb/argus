package selfupdate

import "testing"

// SetMaxArchiveBytes sets the archive size limit for the duration of the test.
func SetMaxArchiveBytes(t *testing.T, n int64) {
	t.Helper()
	prev := maxArchiveBytes
	maxArchiveBytes = n
	t.Cleanup(func() { maxArchiveBytes = prev })
}

// WithEUID sets the effective user ID that the Updater compares with the owner of the binary.
func WithEUID(euid int) Option { return func(u *Updater) { u.geteuid = func() int { return euid } } }
