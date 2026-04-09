package config

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sort"

	"github.com/spf13/cobra"
	"github.com/spf13/pflag"
	"github.com/spf13/viper"
)

// Sentinel errors returned by the config package.
var (
	// ErrReadingConfigFile is returned when the config file exists but cannot
	// be read or parsed.
	ErrReadingConfigFile = errors.New("config: reading config file")

	// ErrDecodingConfig is returned when the config file content cannot be
	// decoded into the [Config] struct.
	ErrDecodingConfig = errors.New("config: decoding config")

	// ErrCreatingConfigDir is returned when the config directory cannot be
	// created on first run.
	ErrCreatingConfigDir = errors.New("config: creating config directory")

	// ErrWritingConfigFile is returned when the initial config file cannot be
	// written on first run.
	ErrWritingConfigFile = errors.New("config: writing config file")

	// ErrUnknownKey is returned by [Set] and [Get] when the supplied key is
	// not a recognised config key.
	ErrUnknownKey = errors.New("config: unknown key")
)

// Config holds all runtime configuration for the Argus CLI.
// Fields map 1-to-1 to YAML keys in the config file, Viper keys, flag names,
// and ARGUS_<KEY> environment variables.
type Config struct {
	// URL is the base URL of the Argus service.
	// Config key: "url" | Flag: --url | Env: ARGUS_URL
	URL   string `mapstructure:"url"`
	UseCf bool   `mapstructure:"use_cloudflare"`
}

// configKeys is the set of persistent flag names that correspond to Config
// fields. Adding a new Config field requires adding its flag name here so the
// auto-binder picks it up — no other wiring needed.
var configKeys = map[string]struct{}{
	"url":            {},
	"use_cloudflare": {},
}

// Load builds a Viper instance, auto-binds every persistent flag on cmd whose
// name appears in configKeys, reads from the config file at cfgFile (or the
// XDG default location), applies ARGUS_* environment-variable overrides, and
// decodes into [Config].
//
// Automatic flag binding means any persistent flag registered on cmd (or its
// root) whose name matches a Viper/config key is honoured without any manual
// BindPFlag call in the caller. Flag values win over the config file, which
// wins over env vars, which wins over built-in defaults — following Viper's
// standard precedence.
//
// If the config file does not exist, Load creates the directory and file,
// writing all currently resolved values so subsequent runs read from it.
//
// cfgFile may be empty, in which case Viper uses
// $XDG_CONFIG_HOME/argus-cli/config.yaml.
//
// cmd may be nil (useful in tests that do not exercise the full cobra tree);
// in that case no flag binding is performed.
func Load(cfgFile string, cmd *cobra.Command) (*Config, error) {
	v := viper.New()

	// ---- defaults ----------------------------------------------------
	v.SetDefault("url", "https://argus.scylladb.com")
	v.SetDefault("use_cloudflare", true)

	// ---- environment variables ---------------------------------------
	v.SetEnvPrefix("ARGUS")
	v.AutomaticEnv()

	// ---- auto-bind all persistent flags recognised as config keys ----
	// Walking the flag set once here means every new persistent flag added
	// to root.go is automatically honoured by Viper — just add its name to
	// configKeys above.
	if cmd != nil {
		cmd.Root().PersistentFlags().VisitAll(func(f *pflag.Flag) {
			if _, ok := configKeys[f.Name]; ok {
				_ = v.BindPFlag(f.Name, f)
			}
		})
	}

	// ---- config file -------------------------------------------------
	var resolvedPath string

	if cfgFile != "" {
		v.SetConfigFile(cfgFile)
		resolvedPath = cfgFile
	} else {
		v.AddConfigPath(ConfigDir())
		v.SetConfigName("config")
		v.SetConfigType("yaml")
		resolvedPath = filepath.Join(ConfigDir(), "config.yaml")
	}

	if err := v.ReadInConfig(); err != nil {
		var notFound viper.ConfigFileNotFoundError
		if !errors.As(err, &notFound) && !isNotExist(err) {
			return nil, fmt.Errorf("%w: %w", ErrReadingConfigFile, err)
		}

		// First run: persist the resolved values so future runs use the file.
		if writeErr := writeNewConfig(v, resolvedPath); writeErr != nil {
			return nil, writeErr
		}
	}

	// ---- decode into struct ------------------------------------------
	var cfg Config
	if err := v.Unmarshal(&cfg); err != nil {
		return nil, fmt.Errorf("%w: %w", ErrDecodingConfig, err)
	}

	return &cfg, nil
}

// writeNewConfig creates all parent directories for path and writes the
// current Viper state (defaults + flag/env overrides) to it as YAML.
func writeNewConfig(v *viper.Viper, path string) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return fmt.Errorf("%w: %w", ErrCreatingConfigDir, err)
	}

	if err := v.WriteConfigAs(path); err != nil {
		return fmt.Errorf("%w %q: %w", ErrWritingConfigFile, path, err)
	}

	return nil
}

// isNotExist returns true for OS-level "file not found" errors that may be
// wrapped inside a Viper error but are not ConfigFileNotFoundError.
func isNotExist(err error) bool {
	return errors.Is(err, os.ErrNotExist)
}

// Keys returns the sorted list of recognised config key names.
func Keys() []string {
	out := make([]string, 0, len(configKeys))
	for k := range configKeys {
		out = append(out, k)
	}
	// Deterministic order.
	sort.Strings(out)
	return out
}

// IsValidKey reports whether key is a recognised config key.
func IsValidKey(key string) bool {
	_, ok := configKeys[key]
	return ok
}

// Set updates a single config key on disk (in the default or user-supplied
// config file) without disturbing other keys.  value is stored as a string;
// Viper/mapstructure will coerce it to the correct Go type when the config is
// next loaded.
//
// cfgFile may be empty to use the default XDG path.
func Set(cfgFile, key, value string) error {
	if !IsValidKey(key) {
		return fmt.Errorf("%w: %q (valid keys: %v)", ErrUnknownKey, key, Keys())
	}

	v, path := newFileViper(cfgFile)
	// Best-effort read of existing file so we don't clobber other keys.
	_ = v.ReadInConfig()

	v.Set(key, value)
	return writeNewConfig(v, path)
}

// Get reads a single config key from disk and returns its string
// representation.  cfgFile may be empty to use the default XDG path.
func Get(cfgFile, key string) (string, error) {
	if !IsValidKey(key) {
		return "", fmt.Errorf("%w: %q (valid keys: %v)", ErrUnknownKey, key, Keys())
	}

	v, _ := newFileViper(cfgFile)
	// Apply defaults so we always return something meaningful.
	v.SetDefault("url", "https://argus.scylladb.com")
	v.SetDefault("use_cloudflare", true)
	_ = v.ReadInConfig()

	return v.GetString(key), nil
}

// GetAll returns all config key-value pairs as a map.  cfgFile may be empty.
func GetAll(cfgFile string) map[string]string {
	v, _ := newFileViper(cfgFile)
	v.SetDefault("url", "https://argus.scylladb.com")
	v.SetDefault("use_cloudflare", true)
	_ = v.ReadInConfig()

	out := make(map[string]string, len(configKeys))
	for k := range configKeys {
		out[k] = v.GetString(k)
	}
	return out
}

// newFileViper creates a Viper instance pointed at the config file, suitable
// for reading or writing individual keys without flag/env interference.
func newFileViper(cfgFile string) (*viper.Viper, string) {
	v := viper.New()
	v.SetConfigType("yaml")

	var path string
	if cfgFile != "" {
		v.SetConfigFile(cfgFile)
		path = cfgFile
	} else {
		v.AddConfigPath(ConfigDir())
		v.SetConfigName("config")
		path = filepath.Join(ConfigDir(), "config.yaml")
	}
	return v, path
}
