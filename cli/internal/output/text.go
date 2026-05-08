package output

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"

	"github.com/olekukonko/tablewriter"
	"github.com/olekukonko/tablewriter/tw"
)

// Sentinel errors returned by the text outputter.
var (
	// ErrTextOutputRow is returned when appending a row to the table fails.
	ErrTextOutputRow = errors.New("text output row")

	// ErrTextOutputRender is returned when rendering the table fails.
	ErrTextOutputRender = errors.New("text output render")

	// ErrTextOutputJSONFallback is returned when marshalling a non-[Tabular]
	// value to JSON (for the raw-JSON fallback path) fails.
	ErrTextOutputJSONFallback = errors.New("text output (json fallback)")

	// ErrTextOutputJSONFallbackRow is returned when appending the JSON row to
	// the fallback table fails.
	ErrTextOutputJSONFallbackRow = errors.New("text output (json fallback) row")

	// ErrTextOutputJSONFallbackRender is returned when rendering the fallback
	// table fails.
	ErrTextOutputJSONFallbackRender = errors.New("text output (json fallback) render")
)

// textOutputter writes values as a human-readable table using tablewriter.
// If the value implements [Tabular] its Headers/Rows are used directly;
// otherwise the value is JSON-marshalled and the raw JSON is printed as a
// single-column table so output is never silently lost.
type textOutputter struct {
	w io.Writer
}

func newText(w io.Writer) Outputter {
	return &textOutputter{w: w}
}

// Write renders v as a text table.  v should implement [Tabular] for
// meaningful column output; non-Tabular values fall back to a raw JSON row.
func (t *textOutputter) Write(v any) error {
	// Multi-table values get one table per entry with a header line.
	if mt, ok := v.(MultiTabular); ok {
		return t.writeMulti(mt)
	}

	tab, ok := v.(Tabular)
	if !ok {
		switch v := v.(type) {
		case fmt.Stringer:
			_, err := fmt.Fprintln(t.w, v.String())
			return err
		case error:
			_, err := fmt.Fprintln(t.w, v.Error())
			return err
		case string:
			_, err := fmt.Fprintln(t.w, v)
			return err
		}

		return t.writeRawJSON(v)
	}

	table := tablewriter.NewTable(t.w)
	configureTableWidths(table)

	if headers := tab.Headers(); len(headers) > 0 {
		table.Header(headers)
	}

	for _, row := range tab.Rows() {
		if err := table.Append(row); err != nil {
			_ = table.Close()
			return fmt.Errorf("%w: %w", ErrTextOutputRow, err)
		}
	}

	if err := table.Render(); err != nil {
		_ = table.Close()
		return fmt.Errorf("%w: %w", ErrTextOutputRender, err)
	}

	return table.Close()
}

// writeRawJSON is the fallback path for values that do not implement Tabular.
func (t *textOutputter) writeRawJSON(v any) error {
	raw, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		return fmt.Errorf("%w: %w", ErrTextOutputJSONFallback, err)
	}

	table := tablewriter.NewTable(t.w)
	table.Header([]string{"json"})
	configureTableWidths(table)

	if err := table.Append([]string{string(raw)}); err != nil {
		return fmt.Errorf("%w: %w", ErrTextOutputJSONFallbackRow, err)
	}

	if err := table.Render(); err != nil {
		return fmt.Errorf("%w: %w", ErrTextOutputJSONFallbackRender, err)
	}

	return nil
}

// writeMulti renders a [MultiTabular] as a sequence of labelled tables.
func (t *textOutputter) writeMulti(mt MultiTabular) error {
	for i, nt := range mt.Tables() {
		if i > 0 {
			if _, err := fmt.Fprintln(t.w); err != nil {
				return fmt.Errorf("%w: %w", ErrTextOutputRow, err)
			}
		}
		if _, err := fmt.Fprintf(t.w, "\n## %s\n\n", nt.Name); err != nil {
			return fmt.Errorf("%w: %w", ErrTextOutputRow, err)
		}

		table := tablewriter.NewTable(t.w)
		configureTableWidths(table)

		if headers := nt.Tab.Headers(); len(headers) > 0 {
			table.Header(headers)
		}

		for _, row := range nt.Tab.Rows() {
			if err := table.Append(row); err != nil {
				_ = table.Close()
				return fmt.Errorf("%w: %w", ErrTextOutputRow, err)
			}
		}

		if err := table.Render(); err != nil {
			_ = table.Close()
			return fmt.Errorf("%w: %w", ErrTextOutputRender, err)
		}

		if err := table.Close(); err != nil {
			return err
		}
	}
	return nil
}

// colMaxWidth is the maximum character width for any single table column.
const colMaxWidth = 80

// configureTableWidths sets a per-column max width and enables word-wrapping
// on both headers and data rows so that long values are split across lines
// instead of breaking the table layout.
func configureTableWidths(table *tablewriter.Table) {
	table.Configure(func(cfg *tablewriter.Config) {
		cfg.Header.ColMaxWidths.Global = colMaxWidth
		cfg.Header.Formatting.AutoWrap = tw.WrapBreak
		cfg.Row.ColMaxWidths.Global = colMaxWidth
		cfg.Row.Formatting.AutoWrap = tw.WrapBreak
	})
}
