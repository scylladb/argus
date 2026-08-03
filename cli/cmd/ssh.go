package cmd

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"strings"
	"syscall"
	"time"

	"github.com/scylladb/argus/cli/internal/logging"
	"github.com/scylladb/argus/cli/internal/models"
	"github.com/scylladb/argus/cli/internal/services"
	"github.com/spf13/cobra"
)

const sshConnectProbeTimeout = 10 * time.Second

var (
	sshKeyPath     string
	sshTTLSeconds  int
	sshTunnelID    string
	sshFingerprint string

	sshCmd = &cobra.Command{
		Use:   "ssh",
		Short: "SSH tunnel operations",
	}

	sshKeysCmd = &cobra.Command{
		Use:   "keys",
		Short: "Manage SSH keys used for Argus tunnel",
	}

	sshKeysListCmd = &cobra.Command{
		Use:   "list",
		Short: "Fetch authorized SSH keys",
		Annotations: map[string]string{
			SkipAuthRetryAnnotation: "true",
		},
		RunE: func(cmd *cobra.Command, _ []string) error {
			cmd.SilenceUsage = true
			ctx := cmd.Context()
			client := APIClientFrom(ctx)

			svc := services.NewSSHService(client)
			keys, err := svc.ListAuthorizedKeys(ctx, sshTunnelID, sshFingerprint)
			if err != nil {
				return err
			}

			_, _ = fmt.Fprint(cmd.OutOrStdout(), deduplicateKeys(keys))
			return nil
		},
	}

	sshKeysRegisterCmd = &cobra.Command{
		Use:   "register",
		Short: "Register local SSH public key",
		RunE: func(cmd *cobra.Command, _ []string) error {
			cmd.SilenceUsage = true
			ctx := cmd.Context()
			client := APIClientFrom(ctx)
			out := OutputterFrom(ctx)

			svc := services.NewSSHService(client)
			state, _, err := svc.EnsureKey(ctx, sshKeyPath, sshTTLSeconds, false)
			if err != nil {
				return err
			}

			cfg, err := svc.RegisterTunnel(ctx, state.PublicKey, sshTTLSeconds, sshTunnelID)
			if err != nil {
				return err
			}

			return out.Write(cfg)
		},
	}

	sshConnectCmd = &cobra.Command{
		Use:   "connect",
		Short: "Start local SSH tunnel and print local port",
		RunE: func(cmd *cobra.Command, _ []string) error {
			cmd.SilenceUsage = true
			ctx := cmd.Context()
			log := logging.For(LoggerFrom(ctx), "ssh-connect")
			client := APIClientFrom(ctx)

			svc := services.NewSSHService(client)
			state, _, err := svc.EnsureKey(ctx, sshKeyPath, sshTTLSeconds, false)
			if err != nil {
				return err
			}

			tunnelCfg, err := svc.RegisterTunnel(ctx, state.PublicKey, sshTTLSeconds, sshTunnelID)
			if err != nil {
				return err
			}

			candidates := tunnelCfg.Candidates()
			var started *startedTunnel
			for i, candidate := range candidates {
				started, err = startTunnelCandidate(ctx, cmd, svc, candidate, state.PrivateKeyPath)
				if err == nil {
					if i > 0 {
						log.Info().
							Str("proxy_host", candidate.ProxyHost).
							Int("candidate", i+1).
							Int("of", len(candidates)).
							Msg("ssh tunnel failed over to another proxy")
					}
					break
				}
				if i < len(candidates)-1 {
					log.Warn().Err(err).
						Str("proxy_host", candidate.ProxyHost).
						Msg("proxy unreachable, trying the next one")
				}
			}
			if err != nil {
				return err
			}
			if started == nil {
				return fmt.Errorf("no proxy candidates returned for tunnel %s", tunnelCfg.TunnelID)
			}

			localPort, sshCmd, waitErrC := started.localPort, started.cmd, started.waitErrC
			defer func() {
				_ = os.Remove(started.knownHostsPath)
			}()
			// Kill the SSH process group when this function returns for any reason
			// (normal exit, error, Ctrl+C). Setpgid means the PGID == SSH's PID,
			// so -PID kills the whole group.
			defer func() {
				_ = syscall.Kill(-sshCmd.Process.Pid, syscall.SIGKILL)
			}()

			_, _ = fmt.Fprintln(cmd.OutOrStdout(), localPort)
			log.Info().Int("local_port", localPort).Msg("ssh tunnel established")

			if err := <-waitErrC; err != nil {
				if ctx.Err() != nil {
					return ctx.Err()
				}
				if exitErr, ok := err.(*exec.ExitError); ok {
					if status, ok := exitErr.Sys().(syscall.WaitStatus); ok {
						return fmt.Errorf("ssh exited with status %d", status.ExitStatus())
					}
				}
				return err
			}

			return nil
		},
	}
)

func init() {
	defaultKeyPath, err := services.DefaultSSHPrivateKeyPath()
	if err != nil {
		defaultKeyPath = "~/.ssh/" + services.DefaultSSHPrivateKeyName
	}

	for _, c := range []*cobra.Command{sshKeysListCmd, sshKeysRegisterCmd, sshConnectCmd} {
		c.Flags().StringVar(&sshTunnelID, "tunnel-id", "", "Tunnel UUID override (optional)")
	}

	sshKeysListCmd.Flags().StringVar(&sshFingerprint, "fingerprint", "",
		"SHA256 fingerprint of the offered key (sshd %f token); returns only that key")

	for _, c := range []*cobra.Command{sshKeysRegisterCmd, sshConnectCmd} {
		c.Flags().StringVar(&sshKeyPath, "key-path", defaultKeyPath, "Private key path")
		c.Flags().IntVar(&sshTTLSeconds, "ttl-seconds", services.DefaultSSHKeyTTLSeconds, "SSH key TTL in seconds")
	}

	sshKeysCmd.AddCommand(sshKeysListCmd, sshKeysRegisterCmd)
	sshCmd.AddCommand(sshKeysCmd, sshConnectCmd)
	rootCmd.AddCommand(sshCmd)
}

type startedTunnel struct {
	cmd            *exec.Cmd
	waitErrC       chan error
	localPort      int
	knownHostsPath string
}

// startTunnelCandidate brings up one proxy and returns once its local port
// accepts connections. Everything it created is cleaned up on failure, so the
// caller can move straight on to the next candidate.
func startTunnelCandidate(
	ctx context.Context,
	cmd *cobra.Command,
	svc *services.SSHService,
	cfg models.SSHTunnelConfig,
	privateKeyPath string,
) (*startedTunnel, error) {
	localPort, err := services.FindFreeLocalPort()
	if err != nil {
		return nil, err
	}

	knownHostsPath, err := svc.PrepareKnownHostsFile(ctx, cfg)
	if err != nil {
		return nil, err
	}

	sshArgs := services.BuildSSHConnectArgs(cfg, privateKeyPath, localPort, knownHostsPath)
	_, _ = fmt.Fprintln(cmd.ErrOrStderr(), "ssh "+strings.Join(sshArgs, " "))
	sshCmd := exec.CommandContext(ctx, "ssh", sshArgs...) //nolint:gosec // ssh args are generated by trusted CLI code
	sshCmd.Stdout = cmd.ErrOrStderr()
	sshCmd.Stderr = cmd.ErrOrStderr()
	// Run SSH in its own process group so Ctrl+C (SIGINT to the terminal
	// process group) does not race with our explicit Kill on context cancel.
	sshCmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}

	if err := sshCmd.Start(); err != nil {
		_ = os.Remove(knownHostsPath)
		return nil, err
	}

	waitErrC := make(chan error, 1)
	go func() {
		waitErrC <- sshCmd.Wait()
	}()

	if err := waitForTunnelReadiness(ctx, localPort, waitErrC); err != nil {
		// Kill the whole process group, not just ssh: the caller's group-kill
		// defer only covers the candidate that succeeded.
		// Do NOT drain waitErrC here: waitForTunnelReadiness may have
		// already consumed it, leaving the channel empty and causing a
		// deadlock. waitErrC is buffered(1) so the goroutine can always
		// write without blocking and will be GC'd with the channel.
		_ = syscall.Kill(-sshCmd.Process.Pid, syscall.SIGKILL)
		_ = os.Remove(knownHostsPath)
		return nil, err
	}

	return &startedTunnel{
		cmd:            sshCmd,
		waitErrC:       waitErrC,
		localPort:      localPort,
		knownHostsPath: knownHostsPath,
	}, nil
}

func deduplicateKeys(raw string) string {
	seen := make(map[string]struct{})
	var out []string
	for _, line := range strings.Split(raw, "\n") {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		if _, dup := seen[line]; !dup {
			seen[line] = struct{}{}
			out = append(out, line)
		}
	}
	if len(out) == 0 {
		return ""
	}
	return strings.Join(out, "\n") + "\n"
}

func waitForTunnelReadiness(ctx context.Context, port int, waitErrC <-chan error) error {
	readyCtx, cancel := context.WithTimeout(ctx, sshConnectProbeTimeout)
	defer cancel()

	readyErrC := make(chan error, 1)
	go func() {
		readyErrC <- services.WaitForLocalPort(readyCtx, port, sshConnectProbeTimeout)
	}()

	select {
	case err := <-waitErrC:
		if err == nil {
			return fmt.Errorf("ssh process exited before tunnel became ready")
		}
		return fmt.Errorf("ssh process exited before tunnel became ready: %w", err)
	case err := <-readyErrC:
		return err
	case <-ctx.Done():
		return ctx.Err()
	}
}
