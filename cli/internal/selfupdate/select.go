// Package selfupdate finds, selects and installs a newer release of the argus CLI.
package selfupdate

import (
	"strings"

	"golang.org/x/mod/semver"
)

// Release is one CLI release on GitHub.
type Release struct {
	// Version has no "v" and no "cli/" prefix, for example "0.6.0-rc.1".
	Version     string
	Prerelease  bool
	ArchiveURL  string
	ChecksumURL string
}

// canonical returns the form of v that the semver package reads, or "" when v is not a
// semantic version with major, minor and patch.
func canonical(v string) string {
	c := "v" + strings.TrimPrefix(v, "v")
	if !semver.IsValid(c) || semver.Canonical(c) != strings.SplitN(c, "+", 2)[0] {
		return ""
	}
	return c
}

// IsDev reports whether v is a local build: "dev", or any version that is not a full
// semantic version. A dev build never updates itself.
func IsDev(v string) bool {
	return canonical(v) == ""
}

// IsPrerelease reports whether v is a pre-release version, such as "0.6.0-rc.1".
func IsPrerelease(v string) bool {
	c := canonical(v)
	return c != "" && semver.Prerelease(c) != ""
}

// core returns the version without its pre-release and build parts, "v0.6.0" for
// "v0.6.0-rc.1+build.1".
func core(c string) string {
	return strings.TrimSuffix(semver.Canonical(c), semver.Prerelease(c))
}

// allowed reports whether candidate may replace current under the pre-release rules. A
// candidate is a pre-release when its version has a pre-release part or when GitHub marks the
// release as a pre-release.
func allowed(current, candidate string, candidatePrerelease, allowPrerelease bool) bool {
	if allowPrerelease || (!candidatePrerelease && semver.Prerelease(candidate) == "") {
		return true
	}
	return semver.Prerelease(current) != "" && core(current) == core(candidate)
}

// Select returns the newest release that may replace the current version.
//
// A stable build moves to stable releases only. A pre-release build also moves to a newer
// pre-release of the same version. A release that GitHub marks as a pre-release counts as a
// pre-release, also when its version has no pre-release part. allowPrerelease admits every newer pre-release. The
// boolean is false when no release qualifies.
func Select(current string, releases []Release, allowPrerelease bool) (Release, bool) {
	cur := canonical(current)
	if cur == "" {
		return Release{}, false
	}

	var (
		best      Release
		bestCanon string
	)
	for _, r := range releases {
		c := canonical(r.Version)
		if c == "" || semver.Compare(c, cur) <= 0 || !allowed(cur, c, r.Prerelease, allowPrerelease) {
			continue
		}
		if bestCanon == "" || semver.Compare(c, bestCanon) > 0 {
			best, bestCanon = r, c
		}
	}
	return best, bestCanon != ""
}
