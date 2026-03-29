package cache

import "time"

// DefaultTTL is used when [Set] is called with a zero TTL.
const DefaultTTL = 5 * time.Minute

// Option configures a [Cache] at construction time.
type Option func(*Cache)

// WithDisabled puts the cache in pass-through mode: [Get] always returns
// [ErrCacheMiss] and [Set] is a no-op.  Intended for the --no-cache flag.
func WithDisabled(disabled bool) Option {
	return func(c *Cache) {
		c.disabled = disabled
	}
}

// WithDefaultTTL overrides the TTL applied by [Set] when no explicit TTL is
// provided.  Values ≤ 0 are ignored.
func WithDefaultTTL(ttl time.Duration) Option {
	return func(c *Cache) {
		if ttl > 0 {
			c.defaultTTL = ttl
		}
	}
}
