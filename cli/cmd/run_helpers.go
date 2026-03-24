package cmd

import (
	"context"
	"encoding/json"
	"fmt"
	"strconv"
	"time"

	"github.com/scylladb/argus/cli/internal/api"
	"github.com/scylladb/argus/cli/internal/cache"
	"github.com/scylladb/argus/cli/internal/models"
)

// RunInfo wraps the typed run data with its detected Argus plugin type.
type RunInfo struct {
	SCT     *models.SCTTestRun // non-nil if type is "scylla-cluster-tests"
	Generic *models.GenericRun // non-nil if type is "generic"
	Type    string             // "scylla-cluster-tests" or "generic"
}

// IsSCT returns true if the run is an SCT run.
func (r *RunInfo) IsSCT() bool { return r.Type == "scylla-cluster-tests" }

// fetchRunInfo tries SCT first, then generic. Caches the raw response.
func fetchRunInfo(ctx context.Context, client *api.Client, c *cache.Cache, runID string) (*RunInfo, error) {
	cacheKey := fmt.Sprintf("run_info_%s.json", runID)
	typeKey := fmt.Sprintf("run_type_%s", runID)

	// Try cache first.
	if data := c.Get(cacheKey); data != nil {
		argusType := "generic"
		if t := c.Get(typeKey); t != nil {
			argusType = string(t)
		}
		return unmarshalRunInfo(data, argusType)
	}

	log := LoggerFrom(ctx)

	// Try SCT first, then generic.
	var lastErr error
	for _, argusType := range []string{"scylla-cluster-tests", "generic"} {
		path := fmt.Sprintf("/api/v1/run/%s/%s", argusType, runID)
		req, err := client.NewRequest(ctx, "GET", path, nil)
		if err != nil {
			return nil, err
		}

		log.Trace().Str("type", argusType).Str("url", req.URL.String()).Msg("trying run type")

		resp, doErr := client.Do(req)
		if doErr != nil {
			log.Debug().Err(doErr).Str("type", argusType).Msg("request failed")
			lastErr = doErr
			continue
		}
		defer resp.Body.Close()

		if resp.StatusCode != 200 {
			lastErr = fmt.Errorf("HTTP %d for %s", resp.StatusCode, argusType)
			log.Debug().Int("status", resp.StatusCode).Str("type", argusType).Msg("non-200 response")
			continue
		}

		var raw json.RawMessage
		var envelope models.APIResponse[json.RawMessage]

		dec := json.NewDecoder(resp.Body)
		if err := dec.Decode(&envelope); err != nil {
			log.Debug().Err(err).Str("type", argusType).Msg("failed to decode envelope")
			lastErr = err
			continue
		}
		if envelope.IsError() {
			body, _ := envelope.DecodeError()
			lastErr = fmt.Errorf("API error for %s: %s", argusType, body.Message)
			log.Debug().Str("type", argusType).Str("exception", body.Exception).Str("message", body.Message).Msg("API error")
			continue
		}
		raw, err = envelope.Decode()
		if err != nil {
			log.Debug().Err(err).Str("type", argusType).Msg("failed to decode response")
			lastErr = err
			continue
		}

		log.Debug().Str("type", argusType).Msg("run found")
		_ = c.Set(cacheKey, []byte(raw))
		_ = c.Set(typeKey, []byte(argusType))
		return unmarshalRunInfo([]byte(raw), argusType)
	}

	if lastErr != nil {
		return nil, fmt.Errorf("run %s not found: %w", runID, lastErr)
	}
	return nil, fmt.Errorf("run %s not found (tried scylla-cluster-tests and generic)", runID)
}

func unmarshalRunInfo(data []byte, argusType string) (*RunInfo, error) {
	info := &RunInfo{Type: argusType}
	if argusType == "scylla-cluster-tests" {
		var sct models.SCTTestRun
		if err := json.Unmarshal(data, &sct); err != nil {
			return nil, fmt.Errorf("parsing SCT run: %w", err)
		}
		info.SCT = &sct
	} else {
		var gen models.GenericRun
		if err := json.Unmarshal(data, &gen); err != nil {
			return nil, fmt.Errorf("parsing generic run: %w", err)
		}
		info.Generic = &gen
	}
	return info, nil
}

// fetchEventsBySeverity fetches events for a single severity level.
func fetchEventsBySeverity(ctx context.Context, client *api.Client, runID string, severity string, limit int, beforeUnix int64) ([]models.SCTEvent, error) {
	path := fmt.Sprintf("/api/v1/client/sct/%s/events/%s/get?limit=%d", runID, severity, limit)
	if beforeUnix > 0 {
		path += fmt.Sprintf("&before=%d", beforeUnix)
	}

	req, err := client.NewRequest(ctx, "GET", path, nil)
	if err != nil {
		return nil, err
	}

	events, err := api.DoJSON[[]models.SCTEvent](client, req)
	if err != nil {
		return nil, fmt.Errorf("fetching %s events: %w", severity, err)
	}
	return events, nil
}

// parseTimeFlag parses a time flag value as unix timestamp or RFC3339.
// Returns 0 for empty input.
func parseTimeFlag(s string) (int64, error) {
	if s == "" {
		return 0, nil
	}
	if ts, err := strconv.ParseInt(s, 10, 64); err == nil {
		return ts, nil
	}
	if t, err := time.Parse(time.RFC3339, s); err == nil {
		return t.Unix(), nil
	}
	return 0, fmt.Errorf("invalid time %q: expected unix timestamp or RFC3339 (e.g. 2026-03-20T10:00:00Z)", s)
}

// isValidUUID checks if s looks like a UUID (xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx).
func isValidUUID(s string) bool {
	if len(s) != 36 {
		return false
	}
	for i, c := range s {
		if i == 8 || i == 13 || i == 18 || i == 23 {
			if c != '-' {
				return false
			}
		} else if !((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F')) {
			return false
		}
	}
	return true
}

// parseRunID validates and returns the run ID argument.
func parseRunID(arg string) (string, error) {
	if !isValidUUID(arg) {
		return "", fmt.Errorf("invalid run_id %q: not a valid UUID", arg)
	}
	return arg, nil
}

// formatTimestamp formats a unix timestamp (int64/float64) or ISO string
// to a human-readable UTC format.
func formatTimestamp(v any) string {
	switch t := v.(type) {
	case float64:
		if t <= 0 {
			return ""
		}
		return time.Unix(int64(t), 0).UTC().Format("2006-01-02 15:04:05 UTC")
	case int64:
		if t <= 0 {
			return ""
		}
		return time.Unix(t, 0).UTC().Format("2006-01-02 15:04:05 UTC")
	case string:
		if t == "" {
			return ""
		}
		for _, layout := range []string{
			"2006-01-02T15:04:05.000Z",
			"2006-01-02T15:04:05Z",
			time.RFC3339,
		} {
			if parsed, err := time.Parse(layout, t); err == nil {
				return parsed.UTC().Format("2006-01-02 15:04:05 UTC")
			}
		}
		return t
	default:
		return ""
	}
}

// parseEventTimestamp parses the Ts field from an SCTEvent into a unix timestamp.
func parseEventTimestamp(ts string) (int64, error) {
	if ts == "" {
		return 0, nil
	}
	for _, layout := range []string{
		"2006-01-02T15:04:05.000Z",
		"2006-01-02T15:04:05Z",
		time.RFC3339,
	} {
		if parsed, err := time.Parse(layout, ts); err == nil {
			return parsed.Unix(), nil
		}
	}
	return 0, fmt.Errorf("cannot parse event timestamp %q", ts)
}
