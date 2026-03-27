package api

// Routes for Argus API endpoints.
// Path-parameter placeholders use %s for fmt.Sprintf substitution.
const (
	// Receive version information
	ArgusVersion = "/api/v1/version"

	// Test run routes
	TestRunsList        = "/api/v1/test/%s/runs"            // GET  – list runs for a test (test_id)
	TestRunGetType      = "/api/v1/run/%s/type"             // GET  – run type (run_id)
	TestRunGet          = "/api/v1/run/%s/%s"               // GET  – single run (run_type, run_id)
	TestRunActivity     = "/api/v1/run/%s/activity"         // GET  – activity log (run_id)
	TestRunFetchResults = "/api/v1/run/%s/%s/fetch_results" // GET  – result tables (test_id, run_id)

	// Comment routes
	TestRunComments = "/api/v1/run/%s/comments" // GET  – list comments for a run (run_id)
	CommentGet      = "/api/v1/comment/%s/get"  // GET  – single comment (comment_id)

	// Pytest result routes
	TestRunPytestResults = "/api/v1/run/%s/pytest/results" // GET  – pytest results for a run (run_id)
)
