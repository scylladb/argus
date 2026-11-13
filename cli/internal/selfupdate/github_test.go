package selfupdate_test

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/scylladb/argus/cli/internal/selfupdate"
)

const releasesJSON = `[
  {"tag_name": "cli/v0.6.0-rc1", "draft": false, "prerelease": true, "assets": [
    {"name": "argus_0.6.0-rc1_linux_amd64.tar.gz", "browser_download_url": "https://dl/0.6.0-rc1/linux_amd64"},
    {"name": "argus_0.6.0-rc1_checksums.txt", "browser_download_url": "https://dl/0.6.0-rc1/sums"}]},
  {"tag_name": "cli/v0.7.0", "draft": true, "prerelease": false, "assets": [
    {"name": "argus_0.7.0_linux_amd64.tar.gz", "browser_download_url": "https://dl/0.7.0/linux_amd64"},
    {"name": "argus_0.7.0_checksums.txt", "browser_download_url": "https://dl/0.7.0/sums"}]},
  {"tag_name": "v0.16.7", "draft": false, "prerelease": false, "assets": []},
  {"tag_name": "cli/v0.5.1", "draft": false, "prerelease": false, "assets": [
    {"name": "argus_0.5.1_macOS_arm64.tar.gz", "browser_download_url": "https://dl/0.5.1/macOS_arm64"},
    {"name": "argus_0.5.1_checksums.txt", "browser_download_url": "https://dl/0.5.1/sums"}]},
  {"tag_name": "cli/v0.5.0", "draft": false, "prerelease": false, "assets": [
    {"name": "argus_0.5.0_linux_amd64.tar.gz", "browser_download_url": "https://dl/0.5.0/linux_amd64"},
    {"name": "argus_0.5.0_checksums.txt", "browser_download_url": "https://dl/0.5.0/sums"}]}
]`

func releaseServer(t *testing.T, status int, gotAuth *string) *httptest.Server {
	t.Helper()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		assert.Equal(t, "/repos/scylladb/argus/releases", r.URL.Path)
		assert.Equal(t, "100", r.URL.Query().Get("per_page"))
		if gotAuth != nil {
			*gotAuth = r.Header.Get("Authorization")
		}
		w.WriteHeader(status)
		_, _ = w.Write([]byte(releasesJSON))
	}))
	t.Cleanup(srv.Close)
	return srv
}

func TestListReleases_KeepsCLIReleasesForThePlatform(t *testing.T) {
	t.Setenv("GITHUB_TOKEN", "")
	t.Setenv("GH_TOKEN", "")
	srv := releaseServer(t, http.StatusOK, nil)

	got, err := selfupdate.ListReleases(context.Background(), srv.URL, srv.Client(), "linux", "amd64")
	require.NoError(t, err)

	assert.Equal(t, []selfupdate.Release{
		{Version: "0.6.0-rc1", Prerelease: true, ArchiveURL: "https://dl/0.6.0-rc1/linux_amd64", ChecksumURL: "https://dl/0.6.0-rc1/sums"},
		{Version: "0.5.0", ArchiveURL: "https://dl/0.5.0/linux_amd64", ChecksumURL: "https://dl/0.5.0/sums"},
	}, got)
}

func TestListReleases_MacOSAssetName(t *testing.T) {
	srv := releaseServer(t, http.StatusOK, nil)

	got, err := selfupdate.ListReleases(context.Background(), srv.URL, srv.Client(), "darwin", "arm64")
	require.NoError(t, err)

	require.Len(t, got, 1)
	assert.Equal(t, "0.5.1", got[0].Version)
	assert.Equal(t, "https://dl/0.5.1/macOS_arm64", got[0].ArchiveURL)
}

func TestListReleases_SendsToken(t *testing.T) {
	t.Setenv("GITHUB_TOKEN", "")
	t.Setenv("GH_TOKEN", "gh-secret")
	var auth string
	srv := releaseServer(t, http.StatusOK, &auth)

	_, err := selfupdate.ListReleases(context.Background(), srv.URL, srv.Client(), "linux", "amd64")
	require.NoError(t, err)
	assert.Equal(t, "Bearer gh-secret", auth)

	t.Setenv("GITHUB_TOKEN", "github-secret")
	_, err = selfupdate.ListReleases(context.Background(), srv.URL, srv.Client(), "linux", "amd64")
	require.NoError(t, err)
	assert.Equal(t, "Bearer github-secret", auth)
}

func TestListReleases_NoTokenSendsNoHeader(t *testing.T) {
	t.Setenv("GITHUB_TOKEN", "")
	t.Setenv("GH_TOKEN", "")
	auth := "unset"
	srv := releaseServer(t, http.StatusOK, &auth)

	_, err := selfupdate.ListReleases(context.Background(), srv.URL, srv.Client(), "linux", "amd64")
	require.NoError(t, err)
	assert.Empty(t, auth)
}

func TestListReleases_RateLimited(t *testing.T) {
	srv := releaseServer(t, http.StatusForbidden, nil)

	_, err := selfupdate.ListReleases(context.Background(), srv.URL, srv.Client(), "linux", "amd64")
	require.ErrorIs(t, err, selfupdate.ErrReleaseList)
}

func TestListReleases_RetriesWithoutARefusedToken(t *testing.T) {
	t.Setenv("GITHUB_TOKEN", "expired")
	var auths []string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		auths = append(auths, r.Header.Get("Authorization"))
		if r.Header.Get("Authorization") != "" {
			w.WriteHeader(http.StatusUnauthorized)
			return
		}
		_, _ = w.Write([]byte(releasesJSON))
	}))
	t.Cleanup(srv.Close)

	got, err := selfupdate.ListReleases(context.Background(), srv.URL, srv.Client(), "linux", "amd64")
	require.NoError(t, err)

	assert.Len(t, got, 2)
	assert.Equal(t, []string{"Bearer expired", ""}, auths)
}

// backendPage returns a full page of backend releases, with no CLI release on it.
func backendPage(t *testing.T) []byte {
	t.Helper()
	page := make([]map[string]any, 0, 100)
	for i := range 100 {
		page = append(page, map[string]any{"tag_name": fmt.Sprintf("v0.%d.0", i), "assets": []any{}})
	}
	body, err := json.Marshal(page)
	require.NoError(t, err)
	return body
}

func TestListReleases_ReadsTheNextPageUntilACLIRelease(t *testing.T) {
	t.Setenv("GITHUB_TOKEN", "")
	t.Setenv("GH_TOKEN", "")
	backend := backendPage(t)
	var pages []string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		page := r.URL.Query().Get("page")
		pages = append(pages, page)
		switch page {
		case "1":
			_, _ = w.Write(backend)
		case "2":
			_, _ = w.Write([]byte(releasesJSON))
		default:
			t.Errorf("unexpected page %s", page)
		}
	}))
	t.Cleanup(srv.Close)

	got, err := selfupdate.ListReleases(context.Background(), srv.URL, srv.Client(), "linux", "amd64")
	require.NoError(t, err)

	assert.Equal(t, []string{"1", "2"}, pages)
	assert.Len(t, got, 2)
}

func TestListReleases_StopsAfterMaxPages(t *testing.T) {
	t.Setenv("GITHUB_TOKEN", "")
	t.Setenv("GH_TOKEN", "")
	backend := backendPage(t)
	calls := 0
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		calls++
		_, _ = w.Write(backend)
	}))
	t.Cleanup(srv.Close)

	got, err := selfupdate.ListReleases(context.Background(), srv.URL, srv.Client(), "linux", "amd64")
	require.NoError(t, err)

	assert.Empty(t, got)
	assert.Equal(t, 5, calls)
}

func TestListReleases_ReadsPastAPageWithOnlyAPrerelease(t *testing.T) {
	t.Setenv("GITHUB_TOKEN", "")
	t.Setenv("GH_TOKEN", "")
	page1 := make([]map[string]any, 0, 100)
	page1 = append(page1, map[string]any{
		"tag_name": "cli/v0.7.0-rc.1", "prerelease": true,
		"assets": []map[string]string{
			{"name": "argus_0.7.0-rc.1_linux_amd64.tar.gz", "browser_download_url": "https://dl/rc/linux_amd64"},
			{"name": "argus_0.7.0-rc.1_checksums.txt", "browser_download_url": "https://dl/rc/sums"},
		},
	})
	for i := range 99 {
		page1 = append(page1, map[string]any{"tag_name": fmt.Sprintf("v0.%d.0", i), "assets": []any{}})
	}
	body1, err := json.Marshal(page1)
	require.NoError(t, err)
	body2 := []byte(`[{"tag_name": "cli/v0.6.0", "prerelease": false, "assets": [
		{"name": "argus_0.6.0_linux_amd64.tar.gz", "browser_download_url": "https://dl/0.6.0/linux_amd64"},
		{"name": "argus_0.6.0_checksums.txt", "browser_download_url": "https://dl/0.6.0/sums"}]}]`)
	var pages []string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		page := r.URL.Query().Get("page")
		pages = append(pages, page)
		switch page {
		case "1":
			_, _ = w.Write(body1)
		case "2":
			_, _ = w.Write(body2)
		default:
			t.Errorf("unexpected page %s", page)
		}
	}))
	t.Cleanup(srv.Close)

	got, err := selfupdate.ListReleases(context.Background(), srv.URL, srv.Client(), "linux", "amd64")
	require.NoError(t, err)

	assert.Equal(t, []string{"1", "2"}, pages)
	best, ok := selfupdate.Select("0.5.0", got, false)
	require.True(t, ok)
	assert.Equal(t, "0.6.0", best.Version)
}
