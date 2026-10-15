package services

import "github.com/scylladb/argus/cli/internal/models"

// PytestStatuses are the pytest status values accepted by --status, in the
// order the backend enum defines them.
var PytestStatuses = []string{
	string(models.PytestStatusError),
	string(models.PytestStatusPassed),
	string(models.PytestStatusFailure),
	string(models.PytestStatusSkipped),
	string(models.PytestStatusXFailed),
	string(models.PytestStatusXPass),
	string(models.PytestStatusPassedError),
	string(models.PytestStatusFailureError),
	string(models.PytestStatusSkippedError),
	string(models.PytestStatusErrorError),
}

// DefaultPytestStatuses are the statuses the DTest tab shows by default: every
// status except passed, skipped, xfailed and xpass.
func DefaultPytestStatuses() []string {
	return []string{
		string(models.PytestStatusError),
		string(models.PytestStatusFailure),
		string(models.PytestStatusPassedError),
		string(models.PytestStatusFailureError),
		string(models.PytestStatusSkippedError),
		string(models.PytestStatusErrorError),
	}
}

// ParsePytestStatuses validates user-supplied pytest statuses
// (case-insensitive) against [PytestStatuses].
func ParsePytestStatuses(values []string) ([]string, error) {
	return parseEnum(values, PytestStatuses, "status")
}
