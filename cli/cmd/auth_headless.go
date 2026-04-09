package cmd

import (
	"fmt"
	"os"

	"github.com/scylladb/argus/cli/internal/config"
	"github.com/scylladb/argus/cli/internal/keychain"
	"github.com/scylladb/argus/cli/internal/logging"
	"github.com/spf13/cobra"
	"golang.org/x/term"
)

var authHeadlessCmd = &cobra.Command{
	Use:   "headless",
	Short: "Store CF Access service-token credentials for headless (non-browser) authentication",
	Long: `auth headless stores three secrets in the system keychain so that all
subsequent Argus CLI commands can authenticate without cloudflared or a
browser.

The three required credentials are:

  1. CF Access Client ID     — the Cloudflare Access service-token client ID
  2. CF Access Client Secret — the matching client secret
  3. Argus API Token         — a valid Argus personal access token (PAT)

When these credentials are present in the keychain, the CLI sends the
CF-Access-Client-Id and CF-Access-Client-Secret headers (bypassing
Cloudflare Access browser login) together with the Argus API token
(Authorization header), so cloudflared is never invoked.

Each value is prompted interactively with masked input.  To update the
credentials, simply re-run the command — existing values are overwritten.`,
	Annotations: map[string]string{SkipAuthRetryAnnotation: "true"},
	RunE: func(cmd *cobra.Command, _ []string) error {
		cmd.SilenceUsage = true
		ctx := cmd.Context()
		log := logging.For(LoggerFrom(ctx), "auth")

		fd := int(os.Stdin.Fd())
		if !term.IsTerminal(fd) {
			return fmt.Errorf("auth headless requires an interactive terminal; stdin is not a TTY")
		}

		clientID, err := readSecret(fd, "CF Access Client ID: ")
		if err != nil {
			return fmt.Errorf("reading CF Access Client ID: %w", err)
		}
		if clientID == "" {
			return fmt.Errorf("CF Access Client ID must not be empty")
		}

		clientSecret, err := readSecret(fd, "CF Access Client Secret: ")
		if err != nil {
			return fmt.Errorf("reading CF Access Client Secret: %w", err)
		}
		if clientSecret == "" {
			return fmt.Errorf("CF Access Client Secret must not be empty")
		}

		argusToken, err := readSecret(fd, "Argus API Token: ")
		if err != nil {
			return fmt.Errorf("reading Argus API Token: %w", err)
		}
		if argusToken == "" {
			return fmt.Errorf("Argus API Token must not be empty")
		}

		if err := keychain.StoreCFAccess(clientID, clientSecret, argusToken); err != nil {
			log.Error().Err(err).Msg("failed to store headless credentials")
			return err
		}

		// Disable cloudflared login in the config file so future invocations
		// use the headless credentials instead of attempting the browser flow.
		if err := config.Set(cfgFile, "use_cloudflare", "false"); err != nil {
			log.Warn().Err(err).Msg("credentials stored but failed to update config file; set use_cloudflare manually")
		} else {
			log.Debug().Msg("set use_cloudflare=false in config file")
		}

		log.Info().Msg("headless credentials stored in keychain")
		_, _ = fmt.Fprintln(cmd.OutOrStdout(), "Headless credentials stored successfully.")
		return nil
	},
}

// readSecret prints prompt to stderr and reads a line from the terminal with
// echo disabled (masked input).
func readSecret(fd int, prompt string) (string, error) {
	_, _ = fmt.Fprint(os.Stderr, prompt)
	raw, err := term.ReadPassword(fd)
	_, _ = fmt.Fprintln(os.Stderr) // newline after masked input
	if err != nil {
		return "", err
	}
	return string(raw), nil
}

func init() {
	authCmd.AddCommand(authHeadlessCmd)
}
