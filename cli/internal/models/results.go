package models

import (
	"fmt"
	"strings"
)

// ResultCatalogEntry is a single result-table name in the cross-test catalog.
// Columns are merged (union, first-definition-wins) across every test
// reporting a table with this name, since the same table name can carry
// slightly different columns across tests.
type ResultCatalogEntry struct {
	Name      string             `json:"name"`
	TestCount int                `json:"test_count"`
	Columns   []ResultColumnMeta `json:"columns"`
}

// ResultCatalogResponse is the response from the results catalog endpoint.
type ResultCatalogResponse []ResultCatalogEntry

// Headers implements the Tabular interface for ResultCatalogResponse.
func (ResultCatalogResponse) Headers() []string {
	return []string{"Name", "Test Count", "Columns"}
}

// Rows implements the Tabular interface for ResultCatalogResponse.
func (r ResultCatalogResponse) Rows() [][]string {
	rows := make([][]string, 0, len(r))
	for _, entry := range r {
		colNames := make([]string, 0, len(entry.Columns))
		for _, col := range entry.Columns {
			colNames = append(colNames, col.Name)
		}
		rows = append(rows, []string{
			entry.Name,
			fmt.Sprint(entry.TestCount),
			strings.Join(colNames, ", "),
		})
	}
	return rows
}

// GenericResultCell is a single flattened cell from a generic result table,
// as returned by the cross-test results search endpoint. Every field is
// scalar, so tabular rendering is delegated to [ReflectTabularSlice] via
// [NewTabularSlice] instead of a hand-written Headers()/Rows() pair.
type GenericResultCell struct {
	TestID       string  `json:"test_id"`
	Table        string  `json:"table"`
	RunID        string  `json:"run_id"`
	Column       string  `json:"column"`
	Row          string  `json:"row"`
	Value        float64 `json:"value"`
	Status       string  `json:"status"`
	SutTimestamp string  `json:"sut_timestamp"`
}

// ResultSearchResponse is the response from the cross-test results search endpoint.
type ResultSearchResponse struct {
	Total int                 `json:"total"`
	Cells []GenericResultCell `json:"cells"`
}

// Headers implements the Tabular interface for ResultSearchResponse.
func (ResultSearchResponse) Headers() []string {
	return NewTabularSlice([]GenericResultCell(nil)).Headers()
}

// Rows implements the Tabular interface for ResultSearchResponse.
func (r ResultSearchResponse) Rows() [][]string {
	return NewTabularSlice(r.Cells).Rows()
}
