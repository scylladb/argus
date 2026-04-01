package discussions_test

import (
	"encoding/json"
	"testing"

	"github.com/scylladb/argus/cli/cmd/discussions"
	"github.com/scylladb/argus/cli/internal/api"
	"github.com/scylladb/argus/cli/internal/models"
	"github.com/spf13/cobra"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// --------------------------------------------------------------------------
// ParseMentions
// --------------------------------------------------------------------------

func TestParseMentions_Empty(t *testing.T) {
	t.Parallel()
	c := &cobra.Command{}
	c.Flags().String("mention", "", "")
	got := discussions.ParseMentions(c)
	assert.Nil(t, got)
}

func TestParseMentions_Single(t *testing.T) {
	t.Parallel()
	c := &cobra.Command{}
	c.Flags().String("mention", "", "")
	require.NoError(t, c.Flags().Set("mention", "user-1"))
	got := discussions.ParseMentions(c)
	assert.Equal(t, []string{"user-1"}, got)
}

func TestParseMentions_Multiple(t *testing.T) {
	t.Parallel()
	c := &cobra.Command{}
	c.Flags().String("mention", "", "")
	require.NoError(t, c.Flags().Set("mention", "user-1, user-2,user-3"))
	got := discussions.ParseMentions(c)
	assert.Equal(t, []string{"user-1", "user-2", "user-3"}, got)
}

func TestParseMentions_IgnoresEmptySegments(t *testing.T) {
	t.Parallel()
	c := &cobra.Command{}
	c.Flags().String("mention", "", "")
	require.NoError(t, c.Flags().Set("mention", "user-1,,, user-2,"))
	got := discussions.ParseMentions(c)
	assert.Equal(t, []string{"user-1", "user-2"}, got)
}

// --------------------------------------------------------------------------
// CommentSubmitRequest serialisation
// --------------------------------------------------------------------------

func TestCommentSubmitRequest_JSON(t *testing.T) {
	t.Parallel()
	req := models.CommentSubmitRequest{
		Message:   "test message",
		Reactions: map[string]int{"thumbsup": 1},
		Mentions:  []string{"user-1", "user-2"},
	}

	raw, err := json.Marshal(req)
	require.NoError(t, err)

	var got models.CommentSubmitRequest
	require.NoError(t, json.Unmarshal(raw, &got))
	assert.Equal(t, req, got)
}

func TestCommentSubmitRequest_EmptyMentions(t *testing.T) {
	t.Parallel()
	req := models.CommentSubmitRequest{
		Message:   "no mentions",
		Reactions: map[string]int{},
		Mentions:  []string{},
	}

	raw, err := json.Marshal(req)
	require.NoError(t, err)

	// Ensure mentions serialises as [] not null.
	assert.Contains(t, string(raw), `"mentions":[]`)
}

// --------------------------------------------------------------------------
// API route constants
// --------------------------------------------------------------------------

func TestRouteConstants_Format(t *testing.T) {
	t.Parallel()

	assert.Contains(t, api.TestRunCommentSubmit, "/comments/submit")
	assert.Contains(t, api.TestRunCommentUpdate, "/comment/%s/update")
	assert.Contains(t, api.TestRunCommentDelete, "/comment/%s/delete")
}
