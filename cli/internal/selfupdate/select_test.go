package selfupdate_test

import (
	"testing"

	"github.com/stretchr/testify/assert"

	"github.com/scylladb/argus/cli/internal/selfupdate"
)

func releases(versions ...string) []selfupdate.Release {
	out := make([]selfupdate.Release, 0, len(versions))
	for _, v := range versions {
		out = append(out, selfupdate.Release{Version: v, Prerelease: selfupdate.IsPrerelease(v)})
	}
	return out
}

func TestSelect(t *testing.T) {
	cases := []struct {
		name            string
		current         string
		available       []string
		allowPrerelease bool
		want            string
		wantOK          bool
	}{
		{"stable to newer stable", "0.5.0", []string{"0.4.0", "0.6.0", "0.5.1"}, false, "0.6.0", true},
		{"stable skips a pre-release", "0.5.0", []string{"0.6.0-rc1"}, false, "", false},
		{"stable takes the newest stable over a pre-release", "0.5.0", []string{"0.5.1", "0.6.0-rc1"}, false, "0.5.1", true},
		{"stable with allowPrerelease takes a pre-release", "0.5.0", []string{"0.5.1", "0.6.0-rc1"}, true, "0.6.0-rc1", true},
		{"pre-release to the next pre-release of the same version", "0.6.0-rc1", []string{"0.6.0-rc2"}, false, "0.6.0-rc2", true},
		{"pre-release to the stable of the same version", "0.6.0-rc1", []string{"0.6.0-rc2", "0.6.0"}, false, "0.6.0", true},
		{"pre-release skips a pre-release of another version", "0.6.0-rc1", []string{"0.7.0-rc1"}, false, "", false},
		{"pre-release takes a newer stable", "0.6.0-rc1", []string{"0.7.0-rc1", "0.7.0"}, false, "0.7.0", true},
		{"pre-release with allowPrerelease takes another version", "0.6.0-rc1", []string{"0.7.0-rc1"}, true, "0.7.0-rc1", true},
		{"nothing newer", "0.6.0", []string{"0.5.0", "0.6.0", "0.6.0-rc2"}, true, "", false},
		{"empty list", "0.6.0", nil, true, "", false},
		{"pre-release with build metadata to the next pre-release", "0.6.0-rc1+build.1", []string{"0.6.0-rc2"}, false, "0.6.0-rc2", true},
		{"numeric pre-release identifiers compare as numbers", "0.6.0-rc.9", []string{"0.6.0-rc.10"}, false, "0.6.0-rc.10", true},
		{"invalid versions are skipped", "0.5.0", []string{"latest", "0.6", "0.5.1"}, false, "0.5.1", true},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got, ok := selfupdate.Select(tc.current, releases(tc.available...), tc.allowPrerelease)
			assert.Equal(t, tc.wantOK, ok)
			assert.Equal(t, tc.want, got.Version)
		})
	}
}

func TestSelect_GitHubPrereleaseFlag(t *testing.T) {
	flagged := []selfupdate.Release{{Version: "0.7.0", Prerelease: true}, {Version: "0.6.0"}}

	got, ok := selfupdate.Select("0.5.0", flagged, false)
	assert.True(t, ok)
	assert.Equal(t, "0.6.0", got.Version)

	got, ok = selfupdate.Select("0.5.0", flagged, true)
	assert.True(t, ok)
	assert.Equal(t, "0.7.0", got.Version)
}

func TestIsDev(t *testing.T) {
	assert.True(t, selfupdate.IsDev("dev"))
	assert.True(t, selfupdate.IsDev(""))
	assert.True(t, selfupdate.IsDev("0.5"))
	assert.False(t, selfupdate.IsDev("0.5.0"))
	assert.False(t, selfupdate.IsDev("0.6.0-rc1"))
}
