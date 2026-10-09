package models_test

import (
	"encoding/json"
	"testing"

	"github.com/scylladb/argus/cli/internal/models"
	"github.com/scylladb/argus/cli/internal/output"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestRawJSON_MarshalsAsSent(t *testing.T) {
	t.Parallel()
	in := `{"zeta":1,"alpha":null,"big":3903313650}`

	out, err := json.Marshal(models.RawJSON(in))

	require.NoError(t, err)
	assert.Equal(t, in, string(out))
}

func TestRawJSON_EmptyMarshalsToNull(t *testing.T) {
	t.Parallel()
	out, err := json.Marshal(models.RawJSON(nil))

	require.NoError(t, err)
	assert.Equal(t, "null", string(out))
}

func TestRawJSON_Rows(t *testing.T) {
	t.Parallel()
	raw := models.RawJSON(`{"links":[],"issue":null,"meta":{},"labels":[{"id":3903313650,"name":"repair"}],"ok":true}`)
	var _ output.Tabular = raw

	assert.Equal(t, []string{"Key", "Value"}, raw.Headers())
	assert.Equal(t, [][]string{
		{"issue", "null"},
		{"labels.0.id", "3903313650"},
		{"labels.0.name", "repair"},
		{"links", "[]"},
		{"meta", "{}"},
		{"ok", "true"},
	}, raw.Rows())
}

func TestRawJSON_RowsOfInvalidJSON(t *testing.T) {
	t.Parallel()
	assert.Equal(t, [][]string{{"", "not json"}}, models.RawJSON("not json").Rows())
}
