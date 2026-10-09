package models

import (
	"bytes"
	"encoding/json"
	"fmt"
	"sort"
)

// RawJSON is a JSON value exactly as the API sent it. JSON output emits it
// unchanged. Text output is a two-column (Key, Value) table that flattens
// objects and arrays with dot notation, as [KVTabular] does, and prints null,
// [] and {} as written.
type RawJSON []byte

// MarshalJSON implements json.Marshaler. An empty value marshals to null.
func (r RawJSON) MarshalJSON() ([]byte, error) {
	if len(r) == 0 {
		return []byte("null"), nil
	}
	return r, nil
}

// Headers implements output.Tabular.
func (RawJSON) Headers() []string { return []string{"Key", "Value"} }

// Rows implements output.Tabular. Numbers print as written. A value that is not
// valid JSON prints as one row with an empty key.
func (r RawJSON) Rows() [][]string {
	dec := json.NewDecoder(bytes.NewReader(r))
	dec.UseNumber()
	var v any
	if err := dec.Decode(&v); err != nil {
		return [][]string{{"", string(r)}}
	}
	var rows [][]string
	flattenRawJSON("", v, &rows)
	return rows
}

// flattenRawJSON appends one row per scalar, null or empty container in v.
func flattenRawJSON(prefix string, v any, rows *[][]string) {
	switch v := v.(type) {
	case map[string]any:
		if len(v) == 0 {
			*rows = append(*rows, []string{prefix, "{}"})
			return
		}
		keys := make([]string, 0, len(v))
		for k := range v {
			keys = append(keys, k)
		}
		sort.Strings(keys)
		for _, k := range keys {
			flattenRawJSON(joinKey(prefix, k), v[k], rows)
		}
	case []any:
		if len(v) == 0 {
			*rows = append(*rows, []string{prefix, "[]"})
			return
		}
		for i, e := range v {
			flattenRawJSON(fmt.Sprintf("%s.%d", prefix, i), e, rows)
		}
	case nil:
		*rows = append(*rows, []string{prefix, "null"})
	default:
		*rows = append(*rows, []string{prefix, fmt.Sprint(v)})
	}
}
