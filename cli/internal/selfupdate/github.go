package selfupdate

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"os"
	"strings"
)

// DefaultAPIBase is the GitHub REST API that lists the CLI releases.
const DefaultAPIBase = "https://api.github.com"

const (
	perPage      = 100
	releasesPath = "/repos/scylladb/argus/releases"
	tagPrefix    = "cli/v"
	// maxPages bounds the release list requests of one check.
	maxPages = 5
)

var (
	// ErrReleaseList is returned when GitHub does not return the release list.
	ErrReleaseList = errors.New("selfupdate: listing the releases")
	// ErrUnsupportedPlatform is returned for an OS that the release matrix does not ship.
	ErrUnsupportedPlatform = errors.New("selfupdate: no release for this platform")
)

type ghAsset struct {
	Name string `json:"name"`
	URL  string `json:"browser_download_url"`
}

type ghRelease struct {
	TagName    string    `json:"tag_name"`
	Draft      bool      `json:"draft"`
	Prerelease bool      `json:"prerelease"`
	Assets     []ghAsset `json:"assets"`
}

// assetOS returns the OS name that the release archives use.
func assetOS(goos string) (string, error) {
	switch goos {
	case "linux":
		return "linux", nil
	case "darwin":
		return "macOS", nil
	default:
		return "", fmt.Errorf("%w: %s", ErrUnsupportedPlatform, goos)
	}
}

// ArchiveName returns the name of the release archive for a version and a platform.
func ArchiveName(version, goos, goarch string) (string, error) {
	osName, err := assetOS(goos)
	if err != nil {
		return "", err
	}
	return fmt.Sprintf("argus_%s_%s_%s.tar.gz", version, osName, goarch), nil
}

func githubToken() string {
	if token := os.Getenv("GITHUB_TOKEN"); token != "" {
		return token
	}
	return os.Getenv("GH_TOKEN")
}

// fetchPage returns one page of the release list. It sends token when it is not empty.
func fetchPage(ctx context.Context, url string, client *http.Client, token string) ([]ghRelease, int, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, 0, fmt.Errorf("%w: %w", ErrReleaseList, err)
	}
	req.Header.Set("Accept", "application/vnd.github+json")
	if token != "" {
		req.Header.Set("Authorization", "Bearer "+token)
	}

	resp, err := client.Do(req)
	if err != nil {
		return nil, 0, fmt.Errorf("%w: %w", ErrReleaseList, err)
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusOK {
		return nil, resp.StatusCode, fmt.Errorf("%w: status %d", ErrReleaseList, resp.StatusCode)
	}

	var raw []ghRelease
	if err = json.NewDecoder(resp.Body).Decode(&raw); err != nil {
		return nil, resp.StatusCode, fmt.Errorf("%w: %w", ErrReleaseList, err)
	}
	return raw, resp.StatusCode, nil
}

// ListReleases returns the CLI releases of scylladb/argus that ship an archive for goos and
// goarch. Drafts, backend releases and releases without a checksum file are left out.
//
// GitHub lists the newest releases first. ListReleases reads the next page only while the pages
// before it hold no stable CLI release for this platform, and it reads at most maxPages pages.
// Every pre-release newer than that stable release sits on an earlier page, so the caller sees
// each release that Select can choose. When GitHub refuses the token with 401, ListReleases
// sends the request again without the token.
func ListReleases(ctx context.Context, apiBase string, client *http.Client, goos, goarch string) ([]Release, error) {
	if _, err := assetOS(goos); err != nil {
		return nil, err
	}

	token := githubToken()
	releases := make([]Release, 0)
	for page := 1; page <= maxPages; page++ {
		url := fmt.Sprintf("%s%s?per_page=%d&page=%d", strings.TrimSuffix(apiBase, "/"), releasesPath, perPage, page)
		raw, status, err := fetchPage(ctx, url, client, token)
		if status == http.StatusUnauthorized && token != "" {
			token = ""
			raw, _, err = fetchPage(ctx, url, client, token)
		}
		if err != nil {
			return nil, err
		}

		foundStable := false
		for _, r := range raw {
			version, ok := strings.CutPrefix(r.TagName, tagPrefix)
			if !ok || r.Draft {
				continue
			}
			if release, ok := platformRelease(r, version, goos, goarch); ok {
				releases = append(releases, release)
				foundStable = foundStable || (!release.Prerelease && !IsPrerelease(version))
			}
		}
		if foundStable || len(raw) < perPage {
			break
		}
	}
	return releases, nil
}

// platformRelease returns the release with the archive URL of goos and goarch and the checksum
// URL. The boolean is false when the release does not ship both assets.
func platformRelease(r ghRelease, version, goos, goarch string) (Release, bool) {
	archive, _ := ArchiveName(version, goos, goarch)
	checksums := fmt.Sprintf("argus_%s_checksums.txt", version)
	release := Release{Version: version, Prerelease: r.Prerelease}
	for _, a := range r.Assets {
		switch a.Name {
		case archive:
			release.ArchiveURL = a.URL
		case checksums:
			release.ChecksumURL = a.URL
		}
	}
	return release, release.ArchiveURL != "" && release.ChecksumURL != ""
}
