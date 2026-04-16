package cmd

import (
	"context"
	"errors"
	"net"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestSSHCommand_IsHiddenAndWired(t *testing.T) {
	t.Parallel()

	cmd, _, err := rootCmd.Find([]string{"ssh"})
	require.NoError(t, err)
	require.NotNil(t, cmd)
	assert.Equal(t, "ssh", cmd.Name())
	assert.True(t, cmd.Hidden)

	keysCmd, _, err := rootCmd.Find([]string{"ssh", "keys"})
	require.NoError(t, err)
	assert.Equal(t, "keys", keysCmd.Name())

	_, _, err = rootCmd.Find([]string{"ssh", "keys", "list"})
	require.NoError(t, err)
	_, _, err = rootCmd.Find([]string{"ssh", "keys", "register"})
	require.NoError(t, err)
	_, _, err = rootCmd.Find([]string{"ssh", "connect"})
	require.NoError(t, err)
}

func TestWaitForTunnelReadiness_PortReady(t *testing.T) {
	t.Parallel()

	ln, err := net.Listen("tcp", "127.0.0.1:0")
	require.NoError(t, err)
	defer func() { _ = ln.Close() }()

	port := ln.Addr().(*net.TCPAddr).Port
	waitErrC := make(chan error, 1)

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	err = waitForTunnelReadiness(ctx, port, waitErrC)
	require.NoError(t, err)
}

func TestWaitForTunnelReadiness_ProcessExitsFirst(t *testing.T) {
	t.Parallel()

	waitErrC := make(chan error, 1)
	waitErrC <- errors.New("ssh crashed")

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	err := waitForTunnelReadiness(ctx, 65530, waitErrC)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "ssh process exited before tunnel became ready")
}
