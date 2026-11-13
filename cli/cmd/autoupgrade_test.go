package cmd

import (
	"bytes"
	"context"
	"io"
	"testing"

	"github.com/stretchr/testify/assert"

	"github.com/scylladb/argus/cli/internal/selfupdate"
)

type countingUpdater struct {
	calls  int
	result selfupdate.Result
}

func (c *countingUpdater) Daily(_ context.Context, _ io.Writer) (selfupdate.Result, error) {
	c.calls++
	return c.result, nil
}

func withAutoUpgradeFakes(t *testing.T, version string, fake *countingUpdater) {
	t.Helper()
	prevVersion, prevFactory := buildVersion.version, newDailyUpdater
	buildVersion.version = version
	newDailyUpdater = func(string) dailyUpdater { return fake }
	t.Cleanup(func() { buildVersion.version, newDailyUpdater = prevVersion, prevFactory })
	t.Setenv(envNoAutoUpgrade, "")
	t.Setenv(EnvUpgradedFrom, "")
}

func TestAutoUpgrade_RunsAndReturnsTheNewBinary(t *testing.T) {
	fake := &countingUpdater{result: selfupdate.Result{Upgraded: true, Path: "/opt/argus"}}
	withAutoUpgradeFakes(t, "0.5.0", fake)

	path, ok := AutoUpgrade(context.Background(), []string{"argus", "run", "get", "abc"}, &bytes.Buffer{})

	assert.True(t, ok)
	assert.Equal(t, "/opt/argus", path)
	assert.Equal(t, 1, fake.calls)
}

func TestAutoUpgrade_NoUpgradeNoExec(t *testing.T) {
	fake := &countingUpdater{}
	withAutoUpgradeFakes(t, "0.5.0", fake)

	_, ok := AutoUpgrade(context.Background(), []string{"argus", "run", "get", "abc"}, &bytes.Buffer{})

	assert.False(t, ok)
	assert.Equal(t, 1, fake.calls)
}

func TestAutoUpgrade_Skips(t *testing.T) {
	cases := []struct {
		name    string
		version string
		env     map[string]string
		args    []string
	}{
		{"dev build", "dev", nil, []string{"argus", "run", "get", "abc"}},
		{"opt-out", "0.5.0", map[string]string{envNoAutoUpgrade: "1"}, []string{"argus", "run", "get", "abc"}},
		{"opt-out true", "0.5.0", map[string]string{envNoAutoUpgrade: "true"}, []string{"argus", "run", "get", "abc"}},
		{"after exec", "0.6.0", map[string]string{EnvUpgradedFrom: "0.5.0"}, []string{"argus", "run", "get", "abc"}},
		{"upgrade command", "0.5.0", nil, []string{"argus", "upgrade", "--prerelease"}},
		{"upgrade after a persistent flag", "0.5.0", nil, []string{"argus", "--config", "/tmp/c.yaml", "upgrade"}},
		{"version command", "0.5.0", nil, []string{"argus", "version"}},
		{"version after a persistent flag", "0.5.0", nil, []string{"argus", "--text", "version"}},
		{"no command", "0.5.0", nil, []string{"argus"}},
		{"help command", "0.5.0", nil, []string{"argus", "help"}},
		{"help for a command", "0.5.0", nil, []string{"argus", "help", "upgrade"}},
		{"help flag", "0.5.0", nil, []string{"argus", "run", "get", "--help"}},
		{"short help flag", "0.5.0", nil, []string{"argus", "-h"}},
		{"completion command", "0.5.0", nil, []string{"argus", "completion", "zsh"}},
		{"completion after a persistent flag", "0.5.0", nil, []string{"argus", "--text", "completion", "zsh"}},
		{"completion request after a persistent flag", "0.5.0", nil, []string{"argus", "--config", "/tmp/c.yaml", "__complete", "run", ""}},
		{"shell completion request", "0.5.0", nil, []string{"argus", "__complete", "run", ""}},
		{"shell completion without descriptions", "0.5.0", nil, []string{"argus", "__completeNoDesc", "run"}},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			fake := &countingUpdater{result: selfupdate.Result{Upgraded: true, Path: "/opt/argus"}}
			withAutoUpgradeFakes(t, tc.version, fake)
			for k, v := range tc.env {
				t.Setenv(k, v)
			}

			_, ok := AutoUpgrade(context.Background(), tc.args, &bytes.Buffer{})

			assert.False(t, ok)
			assert.Equal(t, 0, fake.calls)
		})
	}
}
