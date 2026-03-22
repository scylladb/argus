// Package output provides a format-agnostic printing abstraction for the
// Argus CLI.  Commands receive an [Outputter] and call Write; the concrete
// implementation decides whether to render JSON or a human-readable table.
package output

import "io"

// Tabular is implemented by any value that can describe itself as a table:
// a header row and zero or more data rows, each as a slice of strings.
//
// Commands that want text-table support should make their result types
// implement this interface.  The JSON renderer ignores it and marshals the
// value directly.
type Tabular interface {
	// Headers returns the column titles for the table.
	Headers() []string
	// Rows returns the data rows; each inner slice corresponds to one table row.
	Rows() [][]string
}

// Outputter writes a value to the configured destination in the
// implementation-specific format.
//
// v must be JSON-serialisable.  For text output, v should also implement
// [Tabular]; if it does not, the text renderer falls back to JSON.
type Outputter interface {
	// Write renders v to the underlying [io.Writer].
	Write(v any) error
}

// New returns the appropriate [Outputter] for the requested format.
//
//	out := output.New(os.Stdout, useText)
func New(w io.Writer, text bool) Outputter {
	if text {
		return newText(w)
	}

	return newJSON(w)
}
