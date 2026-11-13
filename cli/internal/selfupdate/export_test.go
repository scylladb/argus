package selfupdate

import "testing"

// SetMaxArchiveBytes sets the archive size limit for the duration of the test.
func SetMaxArchiveBytes(t *testing.T, n int64) {
	t.Helper()
	prev := maxArchiveBytes
	maxArchiveBytes = n
	t.Cleanup(func() { maxArchiveBytes = prev })
}

