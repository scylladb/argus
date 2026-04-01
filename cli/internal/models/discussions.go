package models

// Comment mirrors the ArgusTestRunComment Cassandra model.
//
// Field notes:
//   - PostedAt is an integer epoch (seconds).
//   - Mentions is a list of UUID strings.
//   - Reactions is a map of emoji string → count.
type Comment struct {
	ID        string         `json:"id"`
	TestRunID string         `json:"test_run_id"`
	UserID    string         `json:"user_id"`
	ReleaseID string         `json:"release_id"`
	TestID    string         `json:"test_id"`
	PostedAt  int64          `json:"posted_at"`
	Message   string         `json:"message"`
	Mentions  []string       `json:"mentions"`
	Reactions map[string]int `json:"reactions"`
}

// CommentListResponse is the response payload for the comment-list endpoint.
// The backend wraps this in the standard APIResponse envelope.
type CommentListResponse = []Comment

// CommentSubmitRequest is the JSON body for submitting or updating a comment.
type CommentSubmitRequest struct {
	Message   string         `json:"message"`
	Reactions map[string]int `json:"reactions"`
	Mentions  []string       `json:"mentions"`
}
