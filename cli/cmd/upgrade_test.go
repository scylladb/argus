package cmd

import (
	"bytes"
	"context"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/scylladb/argus/cli/internal/selfupdate"
)

type fakeUpgrader struct {
	allowPrerelease bool
	result          selfupdate.Result
	err             error
}

func (f *fakeUpgrader) Upgrade(_ context.Context, allowPrerelease bool) (selfupdate.Result, error) {
	f.allowPrerelease = allowPrerelease
	return f.result, f.err
}

func runUpgrade(t *testing.T, fake *fakeUpgrader, text bool, args ...string) (string, error) {
	t.Helper()
	prevFactory, prevText := newUpgrader, useText
	newUpgrader = func(string) upgrader { return fake }
	useText = text
	t.Cleanup(func() {
		newUpgrader, useText = prevFactory, prevText
		_ = upgradeCmd.Flags().Set("prerelease", "false")
	})

	var buf bytes.Buffer
	upgradeCmd.SetOut(&buf)
	upgradeCmd.SetContext(context.Background())
	require.NoError(t, upgradeCmd.ParseFlags(args))
	err := upgradeCmd.RunE(upgradeCmd, nil)
	return buf.String(), err
}

func TestUpgradeCmd_JSON(t *testing.T) {
	fake := &fakeUpgrader{result: selfupdate.Result{From: "0.5.0", To: "0.6.0", Upgraded: true, Path: "/usr/local/bin/argus"}}

	out, err := runUpgrade(t, fake, false)
	require.NoError(t, err)

	assert.JSONEq(t, `{"from": "0.5.0", "to": "0.6.0", "upgraded": true, "path": "/usr/local/bin/argus"}`, out)
	assert.False(t, fake.allowPrerelease)
}

func TestUpgradeCmd_PrereleaseFlag(t *testing.T) {
	fake := &fakeUpgrader{result: selfupdate.Result{From: "0.5.0", To: "0.6.0-rc1", Upgraded: true}}

	_, err := runUpgrade(t, fake, false, "--prerelease")
	require.NoError(t, err)
	assert.True(t, fake.allowPrerelease)
}

func TestUpgradeCmd_Text(t *testing.T) {
	out, err := runUpgrade(t, &fakeUpgrader{result: selfupdate.Result{From: "0.5.0", To: "0.6.0", Upgraded: true}}, true)
	require.NoError(t, err)
	assert.Equal(t, "argus upgraded 0.5.0 -> 0.6.0\n", out)

	out, err = runUpgrade(t, &fakeUpgrader{result: selfupdate.Result{From: "0.6.0", To: "0.6.0"}}, true)
	require.NoError(t, err)
	assert.Equal(t, "argus 0.6.0 is the newest release\n", out)
}

func TestUpgradeCmd_DevBuild(t *testing.T) {
	_, err := runUpgrade(t, &fakeUpgrader{err: selfupdate.ErrDevBuild}, false)
	require.ErrorIs(t, err, selfupdate.ErrDevBuild)
}

func TestUpgradeCmd_SkipsRootSetup(t *testing.T) {
	require.NotNil(t, upgradeCmd.PersistentPreRunE)
	assert.NoError(t, upgradeCmd.PersistentPreRunE(upgradeCmd, nil))
	assert.Equal(t, "true", upgradeCmd.Annotations[SkipAuthRetryAnnotation])
}
