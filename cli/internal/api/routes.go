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
	TestRunComments      = "/api/v1/run/%s/comments"                  // GET  – list comments for a run (run_id)
	CommentGet           = "/api/v1/comment/%s/get"                   // GET  – single comment (comment_id)
	TestRunCommentSubmit = "/api/v1/test/%s/run/%s/comments/submit"   // POST – submit a comment (test_id, run_id)
	TestRunCommentUpdate = "/api/v1/test/%s/run/%s/comment/%s/update" // POST – update a comment (test_id, run_id, comment_id)
	TestRunCommentDelete = "/api/v1/test/%s/run/%s/comment/%s/delete" // POST – delete a comment (test_id, run_id, comment_id)

	// Pytest result routes
	TestRunPytestResults = "/api/v1/run/%s/pytest/results" // GET  – pytest results for a run (run_id)

	// Log file routes
	TestRunLogDownload = "/testrun/tests/%s/%s/log/%s/download" // GET  – download log file, 302 to S3 (plugin_name, run_id, log_name)

	// SCT-specific routes (mounted under /api/v1/client/sct/)
	SCTEventsGet        = "/api/v1/client/sct/%s/events/get"    // GET – events (run_id); query: severity, limit, before, after
	SCTEventsBySeverity = "/api/v1/client/sct/%s/events/%s/get" // GET – events by severity (run_id, severity); query: limit, before, after
	SCTNemesisGet       = "/api/v1/client/sct/%s/nemesis/get"   // GET – nemesis records (run_id); query: before, after
)
