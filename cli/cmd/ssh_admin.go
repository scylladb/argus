package cmd

import (
	"fmt"

	"github.com/scylladb/argus/cli/internal/api"
	"github.com/scylladb/argus/cli/internal/logging"
	"github.com/scylladb/argus/cli/internal/models"
	"github.com/spf13/cobra"
)


// ---------------------------------------------------------------------------
// Parent command: ssh tunnel
// ---------------------------------------------------------------------------

var sshTunnelCmd = &cobra.Command{
	Use:   "tunnel",
	Short: "Admin CRUD for proxy tunnel configurations",
}

// ---------------------------------------------------------------------------
// ssh tunnel list
// ---------------------------------------------------------------------------

var sshTunnelListCmd = &cobra.Command{
	Use:   "list",
	Short: "List proxy tunnel configurations",
	RunE: func(cmd *cobra.Command, _ []string) error {
		cmd.SilenceUsage = true
		ctx := cmd.Context()
		client := APIClientFrom(ctx)
		out := OutputterFrom(ctx)
		log := logging.For(LoggerFrom(ctx), "ssh-tunnel-list")

		activeOnly, _ := cmd.Flags().GetString("active-only")

		route := api.AdminProxyTunnelConfigs
		if activeOnly != "" {
			route += "?active_only=" + activeOnly
		}
		log.Debug().Str("route", route).Msg("listing tunnel configs")

		req, err := client.NewRequest(ctx, "GET", route, nil)
		if err != nil {
			return err
		}
		result, err := api.DoJSON[[]models.ProxyTunnelConfig](client, req)
		if err != nil {
			log.Error().Err(err).Msg("failed to list tunnel configs")
			return err
		}
		log.Info().Int("count", len(result)).Msg("tunnel configs fetched")
		return out.Write(models.NewTabularSlice(result))
	},
}

// ---------------------------------------------------------------------------
// ssh tunnel get
// ---------------------------------------------------------------------------

var sshTunnelGetCmd = &cobra.Command{
	Use:   "get",
	Short: "Get a proxy tunnel configuration",
	Long:  `Fetch one active proxy tunnel config. Omit --tunnel-id for the default active config.`,
	RunE: func(cmd *cobra.Command, _ []string) error {
		cmd.SilenceUsage = true
		ctx := cmd.Context()
		client := APIClientFrom(ctx)
		out := OutputterFrom(ctx)
		log := logging.For(LoggerFrom(ctx), "ssh-tunnel-get")

		tunnelID, _ := cmd.Flags().GetString("tunnel-id")

		route := api.AdminProxyTunnelConfig
		if tunnelID != "" {
			route += "?tunnel_id=" + tunnelID
		}
		log.Debug().Str("route", route).Msg("fetching tunnel config")

		req, err := client.NewRequest(ctx, "GET", route, nil)
		if err != nil {
			return err
		}
		result, err := api.DoJSON[models.ProxyTunnelConfig](client, req)
		if err != nil {
			log.Error().Err(err).Msg("failed to get tunnel config")
			return err
		}
		log.Info().Str("id", result.ID).Msg("tunnel config fetched")
		return out.Write(models.NewKVTabular(result))
	},
}

// ---------------------------------------------------------------------------
// ssh tunnel create
// ---------------------------------------------------------------------------

var sshTunnelCreateCmd = &cobra.Command{
	Use:   "create",
	Short: "Register a new proxy tunnel host with Argus",
	Long: `Register a new proxy tunnel host with Argus.

The backend will:
  1. Create a dedicated service user (ROLE_SSH_TUNNEL_SERVER) and generate its API token.
  2. Verify the host key fingerprint via ssh-keyscan.
  3. Run the provisioning script on the proxy host.

The response includes api_token — copy it into /etc/argus/proxy-token.env on
the proxy host before running provision_proxy_tunnel.sh.

Get the host key fingerprint with:
  ssh-keyscan -p <port> <host> | ssh-keygen -lf -`,
	RunE: func(cmd *cobra.Command, _ []string) error {
		cmd.SilenceUsage = true
		ctx := cmd.Context()
		client := APIClientFrom(ctx)
		out := OutputterFrom(ctx)
		log := logging.For(LoggerFrom(ctx), "ssh-tunnel-create")

		host, _ := cmd.Flags().GetString("host")
		port, _ := cmd.Flags().GetInt("port")
		proxyUser, _ := cmd.Flags().GetString("proxy-user")
		targetHost, _ := cmd.Flags().GetString("target-host")
		targetPort, _ := cmd.Flags().GetInt("target-port")
		isActive, _ := cmd.Flags().GetBool("active")

		payload := models.ProxyTunnelCreatePayload{
			Host:       host,
			Port:       port,
			ProxyUser:  proxyUser,
			TargetHost: targetHost,
			TargetPort: targetPort,
			IsActive:   isActive,
		}
		log.Debug().Str("host", host).Int("port", port).Msg("creating tunnel config")

		req, err := client.NewRequest(ctx, "POST", api.AdminProxyTunnelConfig, payload)
		if err != nil {
			return err
		}
		result, err := api.DoJSON[models.ProxyTunnelConfig](client, req)
		if err != nil {
			log.Error().Err(err).Msg("failed to create tunnel config")
			return err
		}
		log.Info().Str("id", result.ID).Msg("tunnel config created")
		return out.Write(models.NewKVTabular(result))
	},
}

// ---------------------------------------------------------------------------
// ssh tunnel set-active
// ---------------------------------------------------------------------------

var sshTunnelSetActiveCmd = &cobra.Command{
	Use:   "set-active",
	Short: "Enable or disable a proxy tunnel configuration",
	RunE: func(cmd *cobra.Command, _ []string) error {
		cmd.SilenceUsage = true
		ctx := cmd.Context()
		client := APIClientFrom(ctx)
		out := OutputterFrom(ctx)
		log := logging.For(LoggerFrom(ctx), "ssh-tunnel-set-active")

		tunnelID, _ := cmd.Flags().GetString("tunnel-id")
		isActive, _ := cmd.Flags().GetBool("active")

		route := fmt.Sprintf(api.AdminProxyTunnelSetActive, tunnelID)
		log.Debug().Str("tunnel_id", tunnelID).Bool("active", isActive).Msg("setting tunnel active state")

		req, err := client.NewRequest(ctx, "POST", route, models.ProxyTunnelActivePayload{IsActive: isActive})
		if err != nil {
			return err
		}
		result, err := api.DoJSON[models.ProxyTunnelConfig](client, req)
		if err != nil {
			log.Error().Err(err).Str("tunnel_id", tunnelID).Msg("failed to set tunnel active state")
			return err
		}
		log.Info().Str("id", result.ID).Bool("is_active", result.IsActive).Msg("tunnel active state updated")
		return out.Write(models.NewKVTabular(result))
	},
}

// ---------------------------------------------------------------------------
// ssh tunnel delete
// ---------------------------------------------------------------------------

var sshTunnelDeleteCmd = &cobra.Command{
	Use:   "delete",
	Short: "Permanently delete a proxy tunnel configuration (admin)",
	Long:  `Delete a proxy tunnel config and its associated service user. This cannot be undone.`,
	RunE: func(cmd *cobra.Command, _ []string) error {
		cmd.SilenceUsage = true
		ctx := cmd.Context()
		client := APIClientFrom(ctx)
		out := OutputterFrom(ctx)
		log := logging.For(LoggerFrom(ctx), "ssh-tunnel-delete")

		tunnelID, _ := cmd.Flags().GetString("tunnel-id")

		route := fmt.Sprintf(api.AdminProxyTunnelDelete, tunnelID)
		log.Debug().Str("tunnel_id", tunnelID).Msg("deleting tunnel config")

		req, err := client.NewRequest(ctx, "DELETE", route, nil)
		if err != nil {
			return err
		}

		type deleteResponse struct {
			Deleted bool `json:"deleted"`
		}
		result, err := api.DoJSON[deleteResponse](client, req)
		if err != nil {
			log.Error().Err(err).Str("tunnel_id", tunnelID).Msg("failed to delete tunnel config")
			return err
		}
		log.Info().Str("tunnel_id", tunnelID).Msg("tunnel config deleted")
		return out.Write(models.NewKVTabular(result))
	},
}

// ---------------------------------------------------------------------------
// ssh keys inspect  (JSON metadata — admin view)
// ---------------------------------------------------------------------------

var sshKeysInspectCmd = &cobra.Command{
	Use:   "inspect",
	Short: "List registered SSH keys with metadata (admin)",
	Long:  `Fetch all registered SSH keys with fingerprint, owner, and expiry metadata.`,
	RunE: func(cmd *cobra.Command, _ []string) error {
		cmd.SilenceUsage = true
		ctx := cmd.Context()
		client := APIClientFrom(ctx)
		out := OutputterFrom(ctx)
		log := logging.For(LoggerFrom(ctx), "ssh-keys-inspect")

		log.Debug().Msg("fetching SSH key metadata")

		req, err := client.NewRequest(ctx, "GET", api.AdminSSHKeys, nil)
		if err != nil {
			return err
		}
		result, err := api.DoJSON[[]models.SSHTunnelKey](client, req)
		if err != nil {
			log.Error().Err(err).Msg("failed to fetch SSH keys")
			return err
		}
		log.Info().Int("count", len(result)).Msg("SSH keys fetched")
		return out.Write(models.NewTabularSlice(result))
	},
}

// ---------------------------------------------------------------------------
// ssh keys delete
// ---------------------------------------------------------------------------

var sshKeysDeleteCmd = &cobra.Command{
	Use:   "delete",
	Short: "Revoke a registered SSH key (admin)",
	Long: `Revoke an SSH key by its UUID. Takes effect immediately — the key will not
be returned by AuthorizedKeysCommand on the next SSH connection attempt.`,
	RunE: func(cmd *cobra.Command, _ []string) error {
		cmd.SilenceUsage = true
		ctx := cmd.Context()
		client := APIClientFrom(ctx)
		out := OutputterFrom(ctx)
		log := logging.For(LoggerFrom(ctx), "ssh-keys-delete")

		keyID, _ := cmd.Flags().GetString("key-id")

		route := fmt.Sprintf(api.AdminSSHKeyDelete, keyID)
		log.Debug().Str("key_id", keyID).Msg("revoking SSH key")

		req, err := client.NewRequest(ctx, "DELETE", route, nil)
		if err != nil {
			return err
		}

		type deleteResponse struct {
			Deleted bool `json:"deleted"`
		}
		result, err := api.DoJSON[deleteResponse](client, req)
		if err != nil {
			log.Error().Err(err).Str("key_id", keyID).Msg("failed to revoke SSH key")
			return err
		}
		log.Info().Str("key_id", keyID).Bool("deleted", result.Deleted).Msg("SSH key revoked")
		return out.Write(models.NewKVTabular(result))
	},
}

// ---------------------------------------------------------------------------
// Registration — extends the existing sshCmd / sshKeysCmd from ssh.go
// ---------------------------------------------------------------------------

func init() {
	// ssh tunnel list
	sshTunnelListCmd.Flags().String("active-only", "", `Filter by active state: "true" or "false" (omit for all)`)

	// ssh tunnel get
	sshTunnelGetCmd.Flags().String("tunnel-id", "", "Tunnel config UUID (omit for the default active config)")

	// ssh tunnel create
	sshTunnelCreateCmd.Flags().String("host", "", "Public hostname or IP of the proxy host (required)")
	sshTunnelCreateCmd.Flags().Int("port", 22, "SSH port on the proxy host")
	sshTunnelCreateCmd.Flags().String("proxy-user", "argus-proxy", "OS user that clients connect as on the proxy host")
	sshTunnelCreateCmd.Flags().String("target-host", "", "Argus private IP that the proxy forwards to (required)")
	sshTunnelCreateCmd.Flags().Int("target-port", 8080, "Argus internal port")
	sshTunnelCreateCmd.Flags().Bool("active", true, "Mark the config as active immediately")
	_ = sshTunnelCreateCmd.MarkFlagRequired("host")
	_ = sshTunnelCreateCmd.MarkFlagRequired("target-host")

	// ssh tunnel set-active
	sshTunnelSetActiveCmd.Flags().String("tunnel-id", "", "Tunnel config UUID (required)")
	sshTunnelSetActiveCmd.Flags().Bool("active", true, "true to enable, false to disable")
	_ = sshTunnelSetActiveCmd.MarkFlagRequired("tunnel-id")

	// ssh tunnel delete
	sshTunnelDeleteCmd.Flags().String("tunnel-id", "", "Tunnel config UUID to delete (required)")
	_ = sshTunnelDeleteCmd.MarkFlagRequired("tunnel-id")

	// ssh keys delete
	sshKeysDeleteCmd.Flags().String("key-id", "", "SSH key UUID to revoke (required)")
	_ = sshKeysDeleteCmd.MarkFlagRequired("key-id")

	sshTunnelCmd.AddCommand(sshTunnelListCmd, sshTunnelGetCmd, sshTunnelCreateCmd, sshTunnelSetActiveCmd, sshTunnelDeleteCmd)
	sshKeysCmd.AddCommand(sshKeysInspectCmd, sshKeysDeleteCmd)
	sshCmd.AddCommand(sshTunnelCmd)
	// sshCmd and sshKeysCmd are already added to rootCmd in ssh.go
}
