# ARGUS-159 — argus prometheus leaves data the user cannot delete and the cache never expires

## Problem

`argus prometheus start` downloads a run's monitor-set archive, extracts the
Prometheus TSDB under `~/.cache/argus-cli/prometheus/<run-id>/` and starts a
`prom/prometheus` container on it. Two problems were left open when the
feature merged:

1. **Files the user cannot delete.** The container writes `wal/`,
   `chunks_head/` and `queries.active` as `nobody:nogroup`. The user's own
   `rm -rf` fails on them, and so does the cleanup in `argus prometheus stop`,
   which drops the error. Everything the CLI extracts is chmod 0777, so the
   rest of the directory is world-writable.
2. **Data the cache never expires.** The cache entry for a run's archive holds
   only the archive's file name. When the entry expires, `PurgeExpired`
   deletes the entry, but the 60–100 MB archive and the extracted TSDB stay on
   disk. `cache clear` and `cache info` do not see them. Containers older than
   one hour are pruned, but their data is kept. The data goes away only through
   `prometheus stop`, and only when the files are deletable.

The investigation found two more defects in the same code, and Komachi added
them to this task on 2026-10-15:

3. **Names used as paths without a check.** A `--run-id` flag value, an ID
   inside a cache key, and the monitor-set file name the server returns are
   joined into file system paths as they are. A value with `..` segments points
   the CLI's `MkdirAll`, `os.Create`, `RemoveAll` and cache writes outside
   its own directories. A comment ID of `../../..` makes the cache entry
   `~/.cache`, and `Invalidate` removes an entry with `RemoveAll`.
4. **`--no-cache cache clear` deletes `./cache` in the current directory.**
   Under `--no-cache` the cache root becomes the relative path `cache`.
   `cache clear` then empties `./cache/` wherever the user stands and prints
   `cache cleared`. The real cache is untouched.

## Who it affects

- Engineers and agents (Zeus) who run `argus prometheus start` on a Linux host
  with rootful Docker to explore a run's metrics. They hit the undeletable
  files and the disk that fills over time.
- Every CLI user. Flag values and server responses decide file system paths.
- Anyone who runs `argus --no-cache cache clear` or `cache info` in a
  directory that holds a `cache/` directory, such as a project checkout.

## Evidence

Jira ARGUS-159, "Argus CLI - followup prometheus metrics commands", Task, In
Progress:

> 2 outstanding review comments to address:1. fix permissions (owner) from
> prometheus containers from ~/.cache/argus-cli/prometheus
> (https://github.com/scylladb/argus/pull/1009#issuecomment-4574145649 )2. check
> if cache clearing works withCache.PurgeExpired

PR scylladb/argus#1009, review by soyacz, 2026-05-27:

> also, these containers should run as current user. otherwise
> .cache/argus-cli/prometheus/<dirs> are owned by nobody:nobody

PR scylladb/argus#1009, comment 4574145649 by soyacz, 2026-05-29:

```
ls -al ~/.cache/argus-cli/prometheus/26a209fe-a8aa-4b31-bf9c-d0b77c16b5a0/
total 58756
drwxrwxrwx 7 ls     ls          4096 May 29 12:55 .
drwxr-xr-x 3 ls     ls          4096 May 29 12:54 ..
drwxrwxrwx 3 ls     ls          4096 May 29 12:55 01KQDV0EYZYDKWQ0CEC6HAKQE8
drwxrwxrwx 3 ls     ls          4096 May 29 12:55 01KQDYCR1F2TJPRYKN223WD469
drwxrwxrwx 3 ls     ls          4096 May 29 12:55 01KQE034MZMHENPWCSSHFXRF5F
drwxr-xr-x 2 nobody nogroup     4096 May 29 12:55 chunks_head
-rwxrwxrwx 1 ls     ls      60125138 May 29 12:55 monitor-set-26a209fe.tar.zst
-rw-r--r-- 1 ls     ls            58 May 29 12:55 prometheus.yml
-rw-r--r-- 1 nobody nogroup    20001 May 29 12:55 queries.active
-rwxrwxrwx 1 ls     ls            36 May 29 12:55 run_id
drwxr-xr-x 2 nobody nogroup     4096 May 29 12:55 wal
rm -rf ~/.cache/argus-cli/prometheus/
rm: cannot remove '/home/ls/.cache/argus-cli/prometheus/26a209fe-a8aa-4b31-bf9c-d0b77c16b5a0/wal/00000001': Permission denied
rm: cannot remove '/home/ls/.cache/argus-cli/prometheus/26a209fe-a8aa-4b31-bf9c-d0b77c16b5a0/wal/00000000': Permission denied
```

PR scylladb/argus#1009, review by CodeLieutenant, 2026-05-29:

> Have you checked that cache clearing works with
> `Cache.PurgeExpired`

The same state on a developer host with rootful Docker 29.9, on 2026-10-15.
The run was started on 2026-05-28. Its cache entry has been purged, but its
data and its container are still there:

```
$ ls -la ~/.cache/argus-cli/prometheus/1e72eebe-a48d-4a3e-a560-c6ad0d85b1af/
total 95740
drwxrwxrwx. 1 komachi komachi      412 05-28 13:23 .
drwxr-xr-x. 1 komachi komachi       72 05-28 13:22 ..
drwxrwxrwx. 1 komachi komachi       60 05-28 13:23 01KRZ2T36NR1DJV82JRJRXR2GQ
drwxrwxrwx. 1 komachi komachi       60 05-28 13:23 01KRZ9NTENCHG4584M7NW1T6DP
drwxrwxrwx. 1 komachi komachi       60 05-28 13:23 01KRZ9NW7SNET9D03BC7WDRFZ6
drwxrwxrwx. 1 komachi komachi       60 05-28 13:23 01KRZGHHR1FZ810Q4DA80H416F
drwxrwxrwx. 1 komachi komachi       60 05-28 13:23 01KRZNFJ64E4ZSHJ3R1SMNEHB5
drwxr-xr-x. 1 nobody  nobody         0 05-28 13:23 chunks_head
-rwxrwxrwx. 1 komachi komachi 98025126 05-28 13:23 monitor-set-1e72eebe.tar.zst
-rw-r--r--. 1 komachi komachi       58 05-28 13:23 prometheus.yml
-rw-r--r--. 1 nobody  nobody     20001 05-28 13:23 queries.active
-rw-r--r--. 1 komachi komachi       36 05-28 13:23 run_id
drwxr-xr-x. 1 nobody  nobody        48 05-28 13:23 wal
$ ls -la ~/.cache/argus-cli/cache/prometheus-logs/
total 0
drwxr-xr-x. 1 komachi komachi  0 06-22 10:46 .
drwxr-xr-x. 1 komachi komachi 86 10-09 12:10 ..
$ du -sh ~/.cache/argus-cli/prometheus/
243M	/home/komachi/.cache/argus-cli/prometheus/
$ docker ps -a --filter name=argus-prom- --format '{{.Names}} {{.Status}}'
argus-prom-1e72eebe Exited (255) 4 months ago
```

The container runs as the image's user, and the CLI opens the directory to
everyone. `cli/cmd/prometheus.go:221-243`:

```go
		// Make data dir writable by the prometheus container user (uid 65534)
		_ = chmodRecursive(dataDir, 0777)
...
		dockerArgs := []string{
			"run", "-d",
			"--name", containerName,
			"-v", dataDir + ":/prometheus",
			"-v", configPath + ":/etc/prometheus/prometheus.yml:ro",
			"-p", "0:9090",
			promImage,
```

`PurgeExpired` walks the cache root, `~/.cache/argus-cli/cache/`, and the
archive lives in `~/.cache/argus-cli/prometheus/<run-id>/`.
`cli/internal/cache/cache.go:93` and `cli/cmd/prometheus.go:360`:

```go
		baseDir:    filepath.Join(baseDir, "cache"),
```

```go
	dir := filepath.Join(cacheDir, "argus-cli", "prometheus", runID)
```

The `stop` cleanup drops its errors and keeps the archive.
`cli/cmd/prometheus.go:324-336`:

```go
// cleanDataDir removes all contents of dir except .tar.zst archive files and the run_id marker.
func cleanDataDir(dir string) {
	...
		_ = os.RemoveAll(filepath.Join(dir, name))
```

Cache keys join IDs with `path.Join`, and the cache joins the key to its root.
`cli/internal/cache/keys.go:107-109` and `cli/internal/cache/cache.go:202-207`:

```go
func CommentKey(commentID string) string {
	return path.Join("comments", commentID)
}
```

```go
func (c *Cache) Invalidate(key string) error {
	if c.Disabled() {
		return nil
	}
	dir := filepath.Join(c.baseDir, filepath.FromSlash(key))
	if err := os.RemoveAll(dir); err != nil && !errors.Is(err, os.ErrNotExist) {
```

Where those joins land, computed with the same calls against this host's roots:

```
key "../.."        -> /home/komachi/.cache            # CommentKey("../../..")
key "../.."        -> /home/komachi/.cache            # RunCommentsKey("../../../..")
key "../x"         -> /home/komachi/.cache/argus-cli/x # PrometheusLogKey("../../x")
run-id "../../.." -> /home/komachi                   # prometheus data dir
```

The monitor-set name comes from the server's log list and becomes a file path.
`cli/cmd/prometheus.go:142-143` and `:168`:

```go
			cachedLogName = monitorLog
			cachedArchive = filepath.Join(dataDir, monitorLog)
...
			archiveFile, err := os.Create(cachedArchive)
```

`--no-cache` gives the cache an empty root. `cli/cmd/root.go:153-157`:

```go
		cacheDir := config.CacheDir()
		if noCache {
			cacheDir = ""
		}
		c := cache.New(cacheDir, cacheOpts...)
```

Reproduction of the `cache clear` defect, built from `master` at `bc9a620a`,
run in a scratch directory with `XDG_CACHE_HOME` pointed at a scratch root:

```
$ find .  (before)
.
./cache
./cache/x
./cache/x/file
$ argus --no-cache cache clear
[two lines: the Cloudflare token check timed out]
cache cleared
$ find .  (after)
.
./cache
```

The real cache root still held its entry, `cache/runs/r1/meta.json`.

## What good looks like

- After `argus prometheus start` and `stop` on rootful Docker or Docker
  Desktop, every file under `~/.cache/argus-cli/` belongs to the user. None
  is world-writable. `rm -rf ~/.cache/argus-cli` succeeds without `sudo`.
- When a run's cache entry expires, or `argus cache clear` runs, its
  downloaded monitor-set archive is gone from disk. While the archive is
  cached, `argus cache info` counts its size.
- The extracted TSDB does not outlive its container: `stop`, `stop --all` and
  the one-hour prune leave no data behind, and neither does a failed `start`.
- A second `start` for the same run within the cache TTL does not download the
  archive again. This works today and must keep working.
- No flag value, cache key, or server-provided file name makes the CLI create,
  write, read or delete a path outside its own directories. Such input is
  refused with an error.
- `argus --no-cache cache clear` and `cache info` never touch the current
  directory.

## Out of scope

- Rootless Docker and Podman. Their user namespace maps the container user to
  a subordinate uid.
- Removing files that earlier CLI versions left as `nobody`. Removing them
  needs root once, by hand.
- The Cloudflare login that `prometheus list` asks for (soyacz, PR
  scylladb/argus#1009, finding 1).
- A Grafana container next to Prometheus.
- A `docker run` that fails after creating its container and leaves it in the
  `Created` state.
