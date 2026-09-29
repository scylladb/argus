# ARGUS-245 — Browsers use outdated frontend bundles after a deployment

**Date**: 2026-09-29

## Root cause

Three things combine. Entry bundles keep the same URL across releases,
production serves them with no `Cache-Control`, so the browser picks its own
lifetime for them, and each build deletes the chunks that the previous entry
bundles import.

**1. Entry bundles and the stylesheet have fixed names.** `vite.config.ts`
hashes only the shared chunks:

```ts
entryFileNames: "[name].bundle.js",
chunkFileNames: "[name]-[hash].js",
assetFileNames: "[name][extname]",
```

The templates load the entries and the stylesheet by those fixed paths. For
example, `templates/base.html.j2:42` and `templates/dashboard.html.j2:4`:

```html
<link rel="stylesheet" href="/s/dist/style.css">
<script type="module" defer src="/s/dist/workArea.bundle.js"></script>
```

21 templates reference `/s/dist/<entry>.bundle.js` this way.

**2. The application serves `/s` with no `Cache-Control`.** The production
vhost on `argus-prod` (`/etc/nginx/conf.d/argus.conf`) does not follow
`docs/config/argus.nginx.conf`. It has no `location /s`. It sets
`root /home/argus/app/public` with `try_files $uri @proxy_to_app`, and no file
exists at `public/s/...`, so every `/s/...` request goes to gunicorn. The app
serves it through the Starlette mount at `argus_backend.py:90`:

```python
app.mount("/s", StaticFiles(directory="public"), name="static")
```

`StaticFiles` sends `etag` and `last-modified` and no `cache-control`. The
response a user gets through Cloudflare on 2026-09-29:

```
HTTP/2 200
content-type: text/javascript; charset=utf-8
last-modified: Mon, 28 Sep 2026 11:02:27 GMT
etag: "8a21d0ce467af895d38abcd4909c064e"
cf-cache-status: DYNAMIC
```

A response with a validator and no explicit lifetime is heuristically
cacheable (RFC 9111, section 4.2.2). Browsers use 10% of the time since
`Last-Modified`, so the file counts as fresh and is reused with no request to
the server. After a deployment the old entry bundle is still fresh in the
cache. Say a user fetched it five days after the previous build: that user
reuses it for about twelve hours. The longer a release stays deployed, the
longer the window after the next one. The ETag revalidation works; the origin
returns `304` for `If-None-Match`. The browser only sends that request once
the heuristic lifetime runs out.

The documented vhost, `docs/config/argus.nginx.conf`, serves `/s` from nginx
with `Cache-Control: public, max-age=600`. A deployment that follows it reuses
the old entry bundle for up to ten minutes, with the same result.

Cloudflare does not cache these files. `cf-cache-status: DYNAMIC` shows the
edge passes them to the origin, and the ETag matches the one the origin sends.

**3. The build deletes the previous chunks.** `vite.config.ts` sets
`emptyOutDir: true`. Commit 53ac9a6b (2026-04-29, "migrate build from Rollup
to Vite") added it. Rollup never cleaned `public/dist`, so the old chunks
stayed on disk and an old entry bundle still loaded. The upgrade procedure
runs the build in place on the live server (`git pull`, build, then
`systemctl restart argus`).

**The failure.** The cached old entry bundle imports chunks by their old
hashes, for example `ApiUtils-<old hash>.js`. The build deleted those files,
so the server returns 404 and the module graph fails to load. The page renders
its server HTML with no working frontend. The same window can pair a new entry
bundle with an old cached `style.css`, which leaves the page with missing or
wrong styles. A large update changes many chunk hashes at once, so almost
every page breaks. That matches "broken frontend after large updates".

The HTML pages come from the app with no validators, so the browser does not
reuse them. Only the static files under `/s` are stale.

## Approaches

**A. Set the cache headers in the nginx vhost. Selected.** Serve `/s/` from
nginx with three locations, so no static request reaches the app:

```nginx
location ~ "^/s/dist/([^/]+-[A-Za-z0-9_-]{8}\.js)$" {
    alias "/home/argus/app/public/dist/$1";
    add_header Cache-Control "public, max-age=31536000, immutable";
}

location /s/dist/ {
    alias "/home/argus/app/public/dist/";
    add_header Cache-Control "no-cache";
}

location /s/ {
    alias "/home/argus/app/public/";
    add_header Cache-Control "public, max-age=600";
    try_files $uri $uri/ =404;
}
```

A content-hashed chunk directly in `dist/` is cached for good. Every other
file in `dist/` gets `no-cache`: the entry bundles, `style.css` and the fonts.
The browser revalidates those with the nginx ETag on each load. It gets `304`
until the next build and the new file after it. The files outside `dist/`, such
as `argus.png`, keep the ten-minute lifetime. They do not change between
releases. `docs/config/argus.nginx.conf` gets these locations. The production
vhost needs the same three blocks ahead of its `location /`.

The prefix is `/s/`, not `/s`. A `location /s` prefix also matches
`/storage/...`, the route that serves user pictures. In the production vhost no
regex location takes `/storage` back, so `location /s` would serve it from
`public/` and return 404. In the documented vhost the regex location for
gunicorn wins over the prefix, so the old `location /s` did not break it there.

- Cost: config only, with no code change. Each page load makes one
  conditional request per fixed-name file in `dist/`: `style.css`, the four
  bundles in `base.html.j2`, the entry bundle of the page, and the fonts it
  uses. nginx answers them, not gunicorn. The nginx ETag comes from the mtime
  and the size, and a build rewrites every file, so each deploy changes the
  ETag of every fixed-name file. A page downloads them once more after a
  deploy, about 1.9 MB, most of it `fontAwesome.bundle.js`. Unchanged chunks
  keep their hash and stay cached.
- Risk: the production vhost is edited by hand and already differs from the
  documented one. The fix takes effect only when the three blocks are added
  there and nginx reloads. Browsers that cached a bundle under the heuristic
  lifetime reuse it once more, until that lifetime runs out.
- Reason: nginx already serves the files in front of the app, and caching
  static files is its job. It meets all three outcomes in `intent.md`. The
  first load after a deploy gets the new entry, which imports only chunks that
  exist, and unchanged chunks stay cached. This is the ETag invalidation the
  Jira issue asks for.

**B. Set `Cache-Control` in the application's static mount.** Replace the plain
`StaticFiles` at `argus_backend.py:90` with a subclass that sets the same
headers by path, and keep the vhost as it is.
- Cost: a small class, one line at the mount, and a test.
- Risk: every revalidation goes through gunicorn. The same rule then lives in
  two places, the app and the documented vhost, and the two must stay the
  same.
- Rejected: the first build of this fix took this approach. The pull request
  review rejected it, because the application is not the layer that caches
  static files. With approach A, `StaticFiles` stays the plain development
  server it was.

**C. Hash every output and resolve names through the Vite manifest.** Set
`build.manifest: true` and add `[hash]` to the entry and asset names. Add a
Jinja global in `argus/backend/rendering.py` that reads
`public/dist/.vite/manifest.json` and returns the URL for an entry. Change the
21 templates and `base.html.j2` to call it, then cache all of `/s/dist` as
immutable.
- Cost: a template change on every page, a manifest load and reload path, and
  tests.
- Risk: it adds a contract, since the backend reads the frontend build output.
  A missing or stale manifest breaks every page. Under the flow it would need a
  spec.
- Rejected: A reaches the same outcomes with no new contract. C saves only the
  `304` round trips.

## Regression test

None. The fix is nginx configuration, and no test suite runs nginx. Verify it
by hand in an `nginx:stable` container. Mount a local build at
`/home/argus/app/public` and put a stub server on the gunicorn socket
`/var/lib/argus/argus.sock` that tags its responses `X-Upstream: app`. Run the
documented vhost and the production vhost with the three blocks added. Both
must give:

| Request | Status | `Cache-Control` | Served by |
|---|---|---|---|
| `/s/dist/workArea.bundle.js`, `main.bundle.js`, `style.css`, `NotoSans-Regular.ttf` | 200 | `no-cache` | nginx |
| `/s/dist/main.bundle.js` with its ETag in `If-None-Match` | 304 | `no-cache` | nginx |
| `/s/dist/ApiUtils-CLFHIzQN.js`, `bootstrap.esm-Kvjg6Wgs.js` | 200 | `public, max-age=31536000, immutable` | nginx |
| `/s/dist/missing-AAAAAAAA.js`, `/s/dist/sub/A-abcdefgh.js` | 404 | none | nginx |
| `/s/argus.png`, `/s/no-user-picture.png` | 200 | `public, max-age=600` | nginx |
| `/storage/picture/<id>`, `/storage`, `/api/v1/version`, `/`, `/s`, `/sfoo` | 200 | none | app |

Across a local build, all 39 hashed chunks get `immutable` and the other 30
files in `dist/` get `no-cache`. In the production layout with `location /s` in
place of `location /s/`, `/storage/picture/<id>`, `/storage` and `/sfoo` return
404 from nginx. That is the check for the prefix.

After the production vhost changes, check through the public host with a
logged-in browser: `main.bundle.js` shows `cache-control: no-cache` and an
`ETag` in the nginx format (`"<mtime>-<size>"`, not an md5), and a user picture
still loads.

## Risks

| Risk | Response |
|---|---|
| The production vhost keeps falling through to the app, so nothing changes | The pull request names the three blocks and the reload. The check through the public host above confirms them. |
| A future `location` ahead of these blocks, or a prefix shorter than `/s/`, captures `/storage` or another app route | The container check covers `/storage`, `/s` and `/sfoo`. Rerun it after any change to the static locations. |
| The pattern misclassifies a file, for example a future hashed entry or an unhashed font | Only files directly in `dist/` whose names match `-<8 chars>.js` get `immutable`, and no `.bundle.js` name can match. Everything else in `dist/` gets `no-cache`, which is always safe. |
| A change to the Vite chunk hash length turns hashed chunks into `no-cache` | The failure is safe: more `304`s, never a stale file. |
| During `yarn build`, `emptyOutDir` empties `public/dist` while it is served, so requests in that window get 404 | This existed before the fix. The fix leaves it as it is. It is out of scope and can be a follow-up that builds into a temporary directory and swaps it in. |
| A tab that was open before the deploy still holds the old code | Out of scope in `intent.md`. No entry uses a dynamic `import()`, so an open tab has all its modules loaded and keeps working until the user reloads. |
