// Package cache provides a file-based, directory-organised response cache
// for the Argus CLI.
//
// Each cache entry lives in its own directory under the application's XDG
// cache root, making it easy to browse by hand without the CLI:
//
//	~/.cache/argus-cli/cache/
//	├── runs/
//	│   └── scylla-cluster-tests/
//	│       └── <run-id>/
//	│           ├── data.json   ← cached API payload
//	│           └── meta.json   ← TTL metadata (fetched_at, expires_at, …)
//	├── run-types/
//	│   └── <run-id>/
//	│       ├── data.json
//	│       └── meta.json
//	├── activity/
//	│   └── <run-id>/ …
//	├── results/
//	│   └── <test-id>/
//	│       └── <run-id>/ …
//	├── comments/
//	│   ├── <comment-id>/ …
//	│   └── run/
//	│       └── <run-id>/ …
//	├── pytest-results/
//	│   └── <run-id>/ …
//	└── version/ …
//
// All writes are atomic (write to *.tmp then rename) so a crash during a
// write never leaves a corrupt entry behind.
package cache

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"time"
)

// Sentinel errors returned by [Get].
var (
	// ErrCacheMiss is returned when no entry exists for the requested key.
	ErrCacheMiss = errors.New("cache: miss")

	// ErrExpired is returned when an entry exists but has passed its TTL.
	// The caller can decide whether to re-fetch or surface stale data.
	ErrExpired = errors.New("cache: entry expired")
)

// Meta is the metadata written alongside each cached data file.
// Human-readable timestamps make it easy to inspect entries without tooling.
type Meta struct {
	FetchedAt time.Time `json:"fetched_at"`
	ExpiresAt time.Time `json:"expires_at"`
	CacheKey  string    `json:"cache_key"`
	// SourceURL is the API endpoint the data was fetched from, for reference.
	SourceURL string `json:"source_url,omitempty"`
}

// IsExpired reports whether the entry's TTL has passed.
func (m Meta) IsExpired() bool {
	return time.Now().After(m.ExpiresAt)
}

// TTLRemaining returns the time left before expiry.
// Returns zero when the entry is already expired.
func (m Meta) TTLRemaining() time.Duration {
	if d := time.Until(m.ExpiresAt); d > 0 {
		return d
	}
	return 0
}

// Cache is a file-based, directory-organised cache for API responses.
//
// The zero value is not usable; always construct via [New].
type Cache struct {
	// baseDir is the root under which all entries are stored.
	// Typically $XDG_CACHE_HOME/argus-cli/cache.
	baseDir    string
	defaultTTL time.Duration
	disabled   bool
}

// New returns a [Cache] rooted at baseDir/cache.
// baseDir should be the application XDG cache directory
// (e.g. the value returned by config.CacheDir()).
func New(baseDir string, opts ...Option) *Cache {
	c := &Cache{
		baseDir:    filepath.Join(baseDir, "cache"),
		defaultTTL: DefaultTTL,
	}
	for _, o := range opts {
		o(c)
	}
	return c
}

// Disabled reports whether the cache is in pass-through mode.
// Safe to call on a nil receiver.
func (c *Cache) Disabled() bool {
	return c == nil || c.disabled
}

// Dir returns the root directory that stores all cache entries.
func (c *Cache) Dir() string {
	return c.baseDir
}

// Get retrieves a cached value stored under key and unmarshals it into T.
//
// Returns:
//   - (value, meta, nil)        on a valid cache hit
//   - (zero, meta, ErrExpired)  when the entry exists but its TTL has passed
//   - (zero, Meta{}, ErrCacheMiss) when no entry exists at key
func Get[T any](c *Cache, key string) (T, Meta, error) {
	var zero T
	if c.Disabled() {
		return zero, Meta{}, ErrCacheMiss
	}

	dir := filepath.Join(c.baseDir, filepath.FromSlash(key))

	metaBytes, err := os.ReadFile(filepath.Join(dir, "meta.json"))
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return zero, Meta{}, ErrCacheMiss
		}
		return zero, Meta{}, fmt.Errorf("cache: reading meta for %q: %w", key, err)
	}

	var meta Meta
	if err := json.Unmarshal(metaBytes, &meta); err != nil {
		// Corrupt meta file — treat as a miss so the entry gets overwritten
		// on the next successful fetch rather than blocking the user.
		return zero, Meta{}, ErrCacheMiss
	}

	if meta.IsExpired() {
		return zero, meta, ErrExpired
	}

	dataBytes, err := os.ReadFile(filepath.Join(dir, "data.json"))
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return zero, Meta{}, ErrCacheMiss
		}
		return zero, Meta{}, fmt.Errorf("cache: reading data for %q: %w", key, err)
	}

	var value T
	if err := json.Unmarshal(dataBytes, &value); err != nil {
		// Corrupt data file — same policy as corrupt meta.
		return zero, meta, ErrCacheMiss
	}

	return value, meta, nil
}

// Set serialises value as indented JSON and writes it under key.
// A ttl of zero falls back to the cache's DefaultTTL.
//
// Writes are atomic: each file is written to a *.tmp sibling first, then
// renamed into place so concurrent readers never see a partial write.
func Set[T any](c *Cache, key string, value T, sourceURL string, ttl time.Duration) error {
	if c.Disabled() {
		return nil
	}

	if ttl <= 0 {
		ttl = c.defaultTTL
	}

	dir := filepath.Join(c.baseDir, filepath.FromSlash(key))
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return fmt.Errorf("cache: creating directory for %q: %w", key, err)
	}

	now := time.Now()
	meta := Meta{
		FetchedAt: now,
		ExpiresAt: now.Add(ttl),
		CacheKey:  key,
		SourceURL: sourceURL,
	}

	if err := writeJSON(filepath.Join(dir, "meta.json"), meta); err != nil {
		return fmt.Errorf("cache: writing meta for %q: %w", key, err)
	}
	if err := writeJSON(filepath.Join(dir, "data.json"), value); err != nil {
		return fmt.Errorf("cache: writing data for %q: %w", key, err)
	}

	return nil
}

// Invalidate removes the cache entry at key.
// It is not an error if the entry does not exist.
func (c *Cache) Invalidate(key string) error {
	if c.Disabled() {
		return nil
	}
	dir := filepath.Join(c.baseDir, filepath.FromSlash(key))
	if err := os.RemoveAll(dir); err != nil && !errors.Is(err, os.ErrNotExist) {
		return fmt.Errorf("cache: invalidating %q: %w", key, err)
	}
	return nil
}

// PurgeExpired walks the cache and removes every entry whose TTL has passed.
// It is safe to call concurrently with [Get] and [Set] — each removal is an
// atomic directory delete. Errors on individual entries are skipped so that
// one corrupt file does not abort the whole sweep.
// Returns the number of entries removed.
func (c *Cache) PurgeExpired() int {
	if c.Disabled() {
		return 0
	}
	removed := 0
	_ = walkEntries(c.baseDir, func(_, entryDir string, rawMeta []byte) {
		var meta Meta
		if err := json.Unmarshal(rawMeta, &meta); err != nil || !meta.IsExpired() {
			return
		}
		if err := os.RemoveAll(entryDir); err == nil {
			removed++
		}
	})
	return removed
}

// Clear removes every entry from the cache.
// It is not an error if the cache directory does not exist.
func (c *Cache) Clear() error {
	if c == nil {
		return nil
	}
	entries, err := os.ReadDir(c.baseDir)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return nil
		}
		return fmt.Errorf("cache: listing entries: %w", err)
	}
	for _, e := range entries {
		path := filepath.Join(c.baseDir, e.Name())
		if err := os.RemoveAll(path); err != nil {
			return fmt.Errorf("cache: removing %q: %w", e.Name(), err)
		}
	}
	return nil
}

// Stats walks the cache directory tree and returns aggregate information
// suitable for the `argus cache info` command.
func (c *Cache) Stats() (Stats, error) {
	s := Stats{Dir: c.baseDir, Categories: make(map[string]CategoryStats)}
	if c == nil {
		return s, nil
	}
	err := walkEntries(c.baseDir, func(category, entryDir string, rawMeta []byte) {
		cat := s.Categories[category]
		cat.Entries++
		s.Entries++

		var meta Meta
		if err := json.Unmarshal(rawMeta, &meta); err == nil && meta.IsExpired() {
			cat.Expired++
			s.Expired++
		}

		for _, name := range []string{"data.json", "meta.json"} {
			if fi, err := os.Stat(filepath.Join(entryDir, name)); err == nil {
				cat.Bytes += fi.Size()
				s.TotalBytes += fi.Size()
			}
		}

		s.Categories[category] = cat
	})
	return s, err
}

// Stats holds aggregate information about the cache returned by [Cache.Stats].
type Stats struct {
	Dir        string
	TotalBytes int64
	Entries    int
	Expired    int
	// Categories breaks down stats by top-level resource type (e.g. "runs",
	// "activity", "comments").
	Categories map[string]CategoryStats
}

// CategoryStats holds per-resource-type statistics.
type CategoryStats struct {
	Entries int
	Expired int
	Bytes   int64
}

// walkEntries invokes fn for every leaf entry directory (any directory
// containing a meta.json file) under root. The name of the first directory
// component below root is passed as category.
func walkEntries(root string, fn func(category, entryDir string, rawMeta []byte)) error {
	topDirs, err := os.ReadDir(root)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return nil
		}
		return fmt.Errorf("cache: reading cache root: %w", err)
	}
	for _, top := range topDirs {
		if !top.IsDir() {
			continue
		}
		findLeaves(filepath.Join(root, top.Name()), top.Name(), fn)
	}
	return nil
}

// findLeaves recursively descends dir, calling fn on any directory that
// contains a meta.json file.
func findLeaves(dir, category string, fn func(string, string, []byte)) {
	metaPath := filepath.Join(dir, "meta.json")
	if b, err := os.ReadFile(metaPath); err == nil {
		fn(category, dir, b)
		return
	}
	entries, err := os.ReadDir(dir)
	if err != nil {
		return
	}
	for _, e := range entries {
		if e.IsDir() {
			findLeaves(filepath.Join(dir, e.Name()), category, fn)
		}
	}
}

// writeJSON atomically writes v as indented JSON to path.
func writeJSON(path string, v any) error {
	data, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		return err
	}
	tmp := path + ".tmp"
	if err := os.WriteFile(tmp, data, 0o644); err != nil {
		return err
	}
	return os.Rename(tmp, path)
}
