// Package models – reflection-based Tabular helpers.
//
// [KVTabular] renders a single struct as a two-column Key / Value table using
// dot-notation to flatten nested structs, indexed notation for slices, and
// map-key notation for maps.
//
// [ReflectTabularSlice] renders a slice of structs as a traditional
// multi-column table where each element is a row and only simple (scalar)
// fields become columns.
//
// Both types implement json.Marshaler so that the JSON outputter serialises the
// original value, not the wrapper.
package models

import (
	"encoding/json"
	"fmt"
	"reflect"
	"sort"
	"strings"
	"unicode"
)

// --------------------------------------------------------------------------
// Public constructors
// --------------------------------------------------------------------------

// NewKVTabular wraps a single value as a two-column (Key, Value) table.
// Struct fields are flattened recursively using dot notation:
//
//	cloud_setup.db_node.image_id  →  ami-12345
//	packages.0.name               →  scylla-server
//
// T should be a struct (or embed structs); non-struct types produce a single
// row whose key is the type name.
func NewKVTabular[T any](v T) *KVTabular[T] {
	return &KVTabular[T]{val: v}
}

// NewTabularSlice wraps a slice of values so it satisfies [output.Tabular].
// Each element becomes one row; only scalar fields become columns.
func NewTabularSlice[T any](v []T) *ReflectTabularSlice[T] {
	return &ReflectTabularSlice[T]{vals: v}
}

// --------------------------------------------------------------------------
// KVTabular – single value, Key/Value output
// --------------------------------------------------------------------------

// KVTabular adapts a single struct value to [output.Tabular] using
// two-column Key/Value output with recursive dot-notation flattening.
type KVTabular[T any] struct{ val T }

// Headers implements output.Tabular.
func (*KVTabular[T]) Headers() []string { return []string{"Key", "Value"} }

// Rows implements output.Tabular.
func (kv *KVTabular[T]) Rows() [][]string {
	pairs := flattenValue("", reflect.ValueOf(kv.val))
	rows := make([][]string, len(pairs))
	for i, p := range pairs {
		rows[i] = []string{p.key, p.value}
	}
	return rows
}

// MarshalJSON implements json.Marshaler so that the JSON outputter serialises
// the wrapped value directly, not the KVTabular wrapper struct.
func (kv *KVTabular[T]) MarshalJSON() ([]byte, error) {
	return json.Marshal(kv.val)
}

// --------------------------------------------------------------------------
// ReflectTabularSlice – slice of values, multi-column output
// --------------------------------------------------------------------------

// ReflectTabularSlice adapts a slice of struct values to [output.Tabular].
type ReflectTabularSlice[T any] struct{ vals []T }

// Headers implements output.Tabular.
func (*ReflectTabularSlice[T]) Headers() []string {
	var zero T
	return structHeaders(reflect.TypeOf(zero))
}

// Rows implements output.Tabular.
func (r *ReflectTabularSlice[T]) Rows() [][]string {
	rows := make([][]string, 0, len(r.vals))
	for i := range r.vals {
		rows = append(rows, structRow(reflect.ValueOf(r.vals[i])))
	}
	return rows
}

// MarshalJSON implements json.Marshaler so that the JSON outputter serialises
// the wrapped slice directly, not the wrapper struct.
func (r *ReflectTabularSlice[T]) MarshalJSON() ([]byte, error) {
	return json.Marshal(r.vals)
}

// --------------------------------------------------------------------------
// Key/Value flattening internals
// --------------------------------------------------------------------------

// kvPair is a single flattened key/value entry.
type kvPair struct {
	key   string
	value string
}

// joinKey builds a dotted key path, skipping empty prefixes.
func joinKey(prefix, name string) string {
	if prefix == "" {
		return name
	}
	return prefix + "." + name
}

// jsonFieldName extracts the JSON field name from a struct field tag.
// Returns the Go field name when no json tag is present.
func jsonFieldName(sf reflect.StructField) string {
	tag := sf.Tag.Get("json")
	if tag == "" || tag == "-" {
		return sf.Name
	}
	name, _, _ := strings.Cut(tag, ",")
	if name == "" {
		return sf.Name
	}
	return name
}

// flattenValue recursively walks v and produces a flat list of kvPair entries.
// prefix is the dotted path accumulated so far.
func flattenValue(prefix string, v reflect.Value) []kvPair {
	// Dereference interfaces and pointers.
	for v.Kind() == reflect.Interface || v.Kind() == reflect.Pointer {
		if v.IsNil() {
			return nil
		}
		v = v.Elem()
	}

	switch v.Kind() {
	case reflect.Struct:
		return flattenStruct(prefix, v)
	case reflect.Slice, reflect.Array:
		return flattenSlice(prefix, v)
	case reflect.Map:
		return flattenMap(prefix, v)
	default:
		// Scalar value.
		return []kvPair{{key: prefix, value: fmt.Sprint(v.Interface())}}
	}
}

// flattenStruct iterates over exported struct fields, flattening embedded
// structs transparently (no extra prefix) and recursing into nested ones.
func flattenStruct(prefix string, v reflect.Value) []kvPair {
	t := v.Type()
	var pairs []kvPair
	for i := range t.NumField() {
		sf := t.Field(i)
		fv := v.Field(i)

		// Anonymous (embedded) struct – flatten without adding a prefix.
		// Check this before the IsExported guard because embedded types
		// with unexported names (e.g. `base`) report IsExported() == false
		// yet their fields are still promotable and accessible.
		if sf.Anonymous {
			pairs = append(pairs, flattenValue(prefix, fv)...)
			continue
		}

		if !sf.IsExported() {
			continue
		}
		tag := sf.Tag.Get("json")
		if tag == "-" {
			continue
		}

		fieldKey := joinKey(prefix, jsonFieldName(sf))
		pairs = append(pairs, flattenValue(fieldKey, fv)...)
	}
	return pairs
}

// flattenSlice handles slices and arrays.  Each element gets an index suffix
// (e.g. "packages.0").
func flattenSlice(prefix string, v reflect.Value) []kvPair {
	if v.Len() == 0 {
		return nil
	}
	var pairs []kvPair
	for i := range v.Len() {
		elemKey := fmt.Sprintf("%s.%d", prefix, i)
		pairs = append(pairs, flattenValue(elemKey, v.Index(i))...)
	}
	return pairs
}

// flattenMap handles maps.  Keys are sorted lexicographically for stable
// output.  Each entry gets the map key as a suffix (e.g. "meta.region").
func flattenMap(prefix string, v reflect.Value) []kvPair {
	if v.Len() == 0 {
		return nil
	}

	// Collect and sort keys.
	keys := make([]string, 0, v.Len())
	keyMap := make(map[string]reflect.Value, v.Len())
	for _, k := range v.MapKeys() {
		s := fmt.Sprint(k.Interface())
		keys = append(keys, s)
		keyMap[s] = k
	}
	sort.Strings(keys)

	var pairs []kvPair
	for _, ks := range keys {
		elemKey := joinKey(prefix, ks)
		pairs = append(pairs, flattenValue(elemKey, v.MapIndex(keyMap[ks]))...)
	}
	return pairs
}

// --------------------------------------------------------------------------
// Multi-column (slice) table internals
// --------------------------------------------------------------------------

// isSimpleKind reports whether k represents a type that can be meaningfully
// printed as a single table cell (numbers, strings, booleans).
func isSimpleKind(k reflect.Kind) bool {
	switch k {
	case reflect.Bool,
		reflect.Int, reflect.Int8, reflect.Int16, reflect.Int32, reflect.Int64,
		reflect.Uint, reflect.Uint8, reflect.Uint16, reflect.Uint32, reflect.Uint64,
		reflect.Float32, reflect.Float64,
		reflect.String:
		return true
	}
	return false
}

// tableFields returns the list of exported, "simple" struct fields that should
// appear as table columns.  Embedded structs are flattened via
// [reflect.VisibleFields].
func tableFields(t reflect.Type) []reflect.StructField {
	for t.Kind() == reflect.Pointer {
		t = t.Elem()
	}
	if t.Kind() != reflect.Struct {
		return nil
	}

	var fields []reflect.StructField
	for _, sf := range reflect.VisibleFields(t) {
		if !sf.IsExported() || sf.Anonymous {
			continue
		}
		tag := sf.Tag.Get("json")
		if tag == "-" {
			continue
		}

		kind := sf.Type.Kind()
		if kind == reflect.Pointer {
			kind = sf.Type.Elem().Kind()
		}

		if !isSimpleKind(kind) {
			continue
		}

		fields = append(fields, sf)
	}
	return fields
}

// structHeaders builds the header row from the struct type's json tags.
func structHeaders(t reflect.Type) []string {
	fields := tableFields(t)
	headers := make([]string, len(fields))
	for i, sf := range fields {
		headers[i] = fieldDisplayName(sf)
	}
	return headers
}

// structRow builds a single data row from a struct value.
func structRow(v reflect.Value) []string {
	for v.Kind() == reflect.Pointer {
		if v.IsNil() {
			return nil
		}
		v = v.Elem()
	}
	fields := tableFields(v.Type())
	row := make([]string, len(fields))
	for i, sf := range fields {
		fv := v.FieldByIndex(sf.Index)
		if fv.Kind() == reflect.Pointer {
			if fv.IsNil() {
				row[i] = ""
				continue
			}
			fv = fv.Elem()
		}
		row[i] = fmt.Sprint(fv.Interface())
	}
	return row
}

// fieldDisplayName derives a human-readable column header from a struct field.
func fieldDisplayName(sf reflect.StructField) string {
	tag := sf.Tag.Get("json")
	name := ""
	if tag != "" {
		name, _, _ = strings.Cut(tag, ",")
	}
	if name == "" || name == "-" {
		name = sf.Name
	}
	return snakeToTitle(name)
}

// snakeToTitle converts a snake_case identifier to Title Case.
func snakeToTitle(s string) string {
	parts := strings.Split(s, "_")
	for i, p := range parts {
		if p == "" {
			continue
		}
		runes := []rune(p)
		runes[0] = unicode.ToUpper(runes[0])
		parts[i] = string(runes)
	}
	return strings.Join(parts, " ")
}
