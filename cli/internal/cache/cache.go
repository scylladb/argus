// Package cache provides a simple file-based cache for API responses.
package cache

import (
	"fmt"
	"os"
	"path/filepath"

	"github.com/adrg/xdg"
)

// Cache is a file-based key-value cache.
type Cache struct {
	dir      string
	disabled bool
}

// New creates a Cache that stores entries under the XDG cache directory.
func New() *Cache {
	return &Cache{
		dir: filepath.Join(xdg.CacheHome, "argus-cli"),
	}
}

// Disable prevents the cache from returning any data. Set operations become
// no-ops. This is toggled by the --no-cache flag.
func (c *Cache) Disable() { c.disabled = true }

// Get reads cached data for the given key. Returns nil on miss or if disabled.
func (c *Cache) Get(key string) []byte {
	if c.disabled {
		return nil
	}
	data, err := os.ReadFile(filepath.Join(c.dir, key))
	if err != nil {
		return nil
	}
	return data
}

// Set writes data to cache using atomic write (temp file + rename).
// Returns nil without writing when the cache is disabled.
func (c *Cache) Set(key string, data []byte) error {
	if c.disabled {
		return nil
	}
	if err := os.MkdirAll(c.dir, 0o755); err != nil {
		return fmt.Errorf("creating cache dir: %w", err)
	}
	dst := filepath.Join(c.dir, key)
	tmp := dst + ".tmp"
	if err := os.WriteFile(tmp, data, 0o644); err != nil {
		return fmt.Errorf("writing cache temp file: %w", err)
	}
	if err := os.Rename(tmp, dst); err != nil {
		os.Remove(tmp)
		return fmt.Errorf("renaming cache file: %w", err)
	}
	return nil
}
