package api

// Routes for Argus API endpoints.
// Path-parameter placeholders use %s for fmt.Sprintf substitution.
const (
	// Receive version information
	ArgusVersion = "/api/v1/version"

	// User token route
	// GET – returns (or generates on first call) the caller's Argus API token.
	// Requires an active session cookie or an existing Authorization: token header.
	UserToken = "/api/v1/user/token"

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
	TestRunLogDownload = "/api/v1/tests/%s/%s/log/%s/download" // GET  – download log file, 302 to S3 (plugin_name, run_id, log_name)

	// SCT event routes (scylla-cluster-tests plugin)
	// Mounted at /api/v1/client/sct/ via: api(url_prefix=/api/v1) → client_api(url_prefix=/client) → sct_api(url_prefix=/sct)
	SCTEventsGet             = "/api/v1/client/sct/%s/events/get"      // GET  – paginated SCT events (run_id); params: limit, before, severity[]
	SCTEventsBySeverity      = "/api/v1/client/sct/%s/events/%s/get"   // GET  – SCT events filtered by severity (run_id, severity)
	SCTEventsCountBySeverity = "/api/v1/client/sct/%s/events/%s/count" // GET  – count SCT events by severity (run_id, severity)
	// Note: there is no GET nemesis endpoint. Nemesis data is embedded in the
	// full run response (SCTTestRun.NemesisData) from TestRunGet.

	// SSH tunnel routes – client (proxy host / AuthorizedKeysCommand)
	SSHKeysList = "/api/v1/client/ssh/keys"   // GET  – plain-text authorized_keys; called by AuthorizedKeysCommand
	SSHTunnel   = "/api/v1/client/ssh/tunnel" // POST – register public key and receive proxy config

	// SSH tunnel routes – admin (requires Admin role)
	AdminProxyTunnelConfig    = "/admin/api/v1/proxy-tunnel/config"            // GET  – one active config (tunnel_id query param optional); POST – create
	AdminProxyTunnelConfigs   = "/admin/api/v1/proxy-tunnel/configs"           // GET  – all configs (active_only query param optional)
	AdminProxyTunnelSetActive = "/admin/api/v1/proxy-tunnel/config/%s/active" // POST   – enable/disable a config (tunnel_id)
	AdminProxyTunnelDelete    = "/admin/api/v1/proxy-tunnel/config/%s"        // DELETE – permanently remove a config (tunnel_id)
	AdminSSHKeys              = "/admin/api/v1/ssh/keys"                       // GET  – list all registered keys with metadata
	AdminSSHKeyDelete         = "/admin/api/v1/ssh/keys/%s"                   // DELETE – revoke a key (key_id)

)
