package cmd

// Exports of unexported context helpers for use in package-level tests.
var (
	ContextWithLogger    = contextWithLogger
	ContextWithConfig    = contextWithConfig
	ContextWithAPIClient = contextWithAPIClient
	ContextWithOutputter = contextWithOutputter
	ContextWithCleanup   = contextWithCleanup
)
