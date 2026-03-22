package config

import (
	"path/filepath"

	"github.com/adrg/xdg"
)

const appName = "argus-cli"

func ConfigFile(name string) (string, error) {
	return xdg.ConfigFile(filepath.Join(appName, name))
}

func CacheFile(name string) (string, error) {
	return xdg.CacheFile(filepath.Join(appName, name))
}

func ConfigDir() string {
	return filepath.Join(xdg.ConfigHome, appName)
}

func CacheDir() string {
	return filepath.Join(xdg.CacheHome, appName)
}
