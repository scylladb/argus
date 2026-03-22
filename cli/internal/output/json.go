package output

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
)

// ErrJSONOutput is returned when the JSON encoder fails to marshal or write
// a value.
var ErrJSONOutput = errors.New("json output")

// jsonOutputter writes values as indented JSON.
type jsonOutputter struct {
	w   io.Writer
	enc *json.Encoder
}

func newJSON(w io.Writer) Outputter {
	enc := json.NewEncoder(w)
	enc.SetIndent("", "  ")

	return &jsonOutputter{w: w, enc: enc}
}

// Write marshals v to indented JSON and writes it to the underlying writer.
func (j *jsonOutputter) Write(v any) error {
	if err := j.enc.Encode(v); err != nil {
		return fmt.Errorf("%w: %w", ErrJSONOutput, err)
	}

	return nil
}
