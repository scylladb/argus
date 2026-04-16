package cmd

import (
	"context"
	"net/http"
	"os"
	"sync"
	"testing"

	"github.com/scylladb/argus/cli/internal/config"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

var rootTestEnvMu sync.Mutex

func withRootTestEnv(t *testing.T, disable bool, env map[string]string) {
	t.Helper()

	rootTestEnvMu.Lock()
	t.Cleanup(func() {
		rootTestEnvMu.Unlock()
	})

	origDisable := disableCf
	disableCf = disable
	t.Cleanup(func() {
		disableCf = origDisable
	})

	type oldVal struct {
		v  string
		ok bool
	}
	old := make(map[string]oldVal, len(env))
	for k, v := range env {
		ov, ok := os.LookupEnv(k)
		old[k] = oldVal{v: ov, ok: ok}
		if v == "" {
			require.NoError(t, os.Unsetenv(k))
			continue
		}
		require.NoError(t, os.Setenv(k, v))
	}

	t.Cleanup(func() {
		for k, ov := range old {
			if ov.ok {
				_ = os.Setenv(k, ov.v)
				continue
			}
			_ = os.Unsetenv(k)
		}
	})
}

func TestBuildAPIClientRaw_DisableCloudflareBypassesCFHeaders(t *testing.T) {
	t.Parallel()

	withRootTestEnv(t, true, map[string]string{
		"ARGUS_CF_ACCESS_CLIENT_ID":     "cf-id",
		"ARGUS_CF_ACCESS_CLIENT_SECRET": "cf-secret",
		"ARGUS_AUTH_TOKEN":              "new-token",
		"ARGUS_TOKEN":                   "legacy-token",
	})

	cfg := &config.Config{URL: "https://argus.scylladb.com", UseCf: true}
	client, err := buildAPIClientRaw(context.Background(), cfg)
	require.NoError(t, err)

	req, err := client.NewRequest(context.Background(), http.MethodGet, "/api/v1/version", nil)
	require.NoError(t, err)

	assert.Equal(t, "token new-token", req.Header.Get("Authorization"))
	assert.Empty(t, req.Header.Get("CF-Access-Client-Id"))
	assert.Empty(t, req.Header.Get("CF-Access-Client-Secret"))
	_, err = req.Cookie("CF_Authorization")
	assert.Error(t, err)
}

func TestBuildAPIClientRaw_ARGUSAUTHTokenPreferred(t *testing.T) {
	t.Parallel()

	withRootTestEnv(t, false, map[string]string{
		"ARGUS_AUTH_TOKEN":              "preferred-token",
		"ARGUS_TOKEN":                   "fallback-token",
		"ARGUS_CF_ACCESS_CLIENT_ID":     "",
		"ARGUS_CF_ACCESS_CLIENT_SECRET": "",
	})

	cfg := &config.Config{URL: "https://argus.scylladb.com", UseCf: false}
	client, err := buildAPIClientRaw(context.Background(), cfg)
	require.NoError(t, err)

	req, err := client.NewRequest(context.Background(), http.MethodGet, "/api/v1/version", nil)
	require.NoError(t, err)

	assert.Equal(t, "token preferred-token", req.Header.Get("Authorization"))
}
