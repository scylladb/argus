# Plan: Enable Local Development Without Jira, GitHub, and Email Access

## Problem

Running Argus locally requires valid credentials for Jira, GitHub, and email (SMTP)
even when the developer does not need any of these integrations. Three distinct issues
block a clean local setup:

1. `ArgusService.__init__` reads `current_app.config['GITHUB_ACCESS_TOKEN']` eagerly
   using a hard key lookup. The value is assigned to `self.github_headers` which is
   **never used anywhere** in the class. This dead assignment causes a `KeyError` on
   every API request if the key is absent.

2. There is no way to activate `dry_run=True` on `IssueService` (and by extension
   `JiraService` / `GithubService`) through configuration. A developer must patch
   calling code by hand.

3. `Email.__init__` always calls `_retrieve_credentials()` which reads all five
   `EMAIL_*` config keys with hard `[]` lookups. This happens inside
   `EmailNotificationServiceSender.__init__`, which is unconditionally instantiated
   by `NotificationManagerService.__init__`, which is called by both `ArgusService`
   and `TestRunService` on every request. There is no way to disable email through
   configuration.

## Goal

Allow a developer to start the full Argus backend locally with only ScyllaDB
available, by setting per-integration config flags. Jira, GitHub, and email are each
enabled by default and can be disabled independently — no credentials are required for
a disabled integration. In-app (DB-backed) notifications continue to work regardless
of the email flag.

---

## Changes

### 1. Remove dead `github_headers` from `ArgusService`

**File:** `argus/backend/service/argus_service.py`

Remove lines 54-57:

```python
self.github_headers = {
    "Accept": "application/vnd.github.v3+json",
    "Authorization": f"token {current_app.config['GITHUB_ACCESS_TOKEN']}"
}
```

This is a dead assignment — `github_headers` is never referenced outside `__init__`.
Removing it eliminates the `KeyError` that fires when `GITHUB_ACCESS_TOKEN` is absent.

---

### 2. Add per-integration `ENABLED` config flags for GitHub and Jira

**File:** `argus/backend/service/issue_service.py`

Update `IssueService.__init__` to read separate flags for each integration when no
explicit `dry_run` argument is passed:

```python
def __init__(self, dry_run: bool | None = None):
    github_dry_run = dry_run if dry_run is not None else not current_app.config.get("GITHUB_ENABLED", True)
    jira_dry_run = dry_run if dry_run is not None else not current_app.config.get("JIRA_ENABLED", True)
    self.gh = GithubService(dry_run=github_dry_run)
    self.jira = JiraService(dry_run=jira_dry_run)
```

Existing callers that pass `dry_run=True` explicitly (e.g., the test fixture in
`conftest.py`) continue to disable both integrations, which is the correct behaviour
for tests.

---

### 3. Make email credential read lazy

**File:** `argus/backend/util/send_email.py`

Move `_retrieve_credentials()` out of `__init__` and into `_connect()` so that
credentials are only read when an SMTP connection is actually being established:

```python
def __init__(self, init_connection=True):
    self.sender: str = ""
    self._password: str = ""
    self._user: str = ""
    self._server_host: str = ""
    self._server_port: int = 0
    self._connection: smtplib.SMTP | None = None
    if init_connection:
        self._connect()

def _connect(self):
    self._retrieve_credentials()  # moved here from __init__
    try:
        self._connection = smtplib.SMTP(host=self._server_host, port=self._server_port)
        ...
```

This means `EMAIL_*` keys are only required at the moment an email is dispatched, not
at service construction time. Since `EmailNotificationServiceSender.send_notification`
already wraps everything in a broad `except Exception` that logs the error, a missing
key at send time is silently swallowed rather than crashing the request.

---

### 4. Add `EMAIL_ENABLED` flag to `NotificationManagerService`

**File:** `argus/backend/service/notification_manager.py`

Skip instantiating `EmailNotificationServiceSender` when `EMAIL_ENABLED` is false:

```python
def __init__(self, notification_senders=None):
    self.notification_services = [ArgusDBNotificationSaver()]
    if current_app.config.get("EMAIL_ENABLED", True):
        self.notification_services.append(EmailNotificationServiceSender())
    if notification_senders:
        self.notification_services.extend(notification_senders)
```

When `EMAIL_ENABLED: false`, `Email()` is never constructed and no credentials are
ever read — lazy credential read (Change 3) is irrelevant in this path but remains
correct for the enabled path. In-app DB notifications (`ArgusDBNotificationSaver`)
continue to work regardless.

---

### 5. Update example config

**File:** `argus_web.example.yaml`

Add all three new flags with documentation comments inline in the commits that
introduce each flag.

---

### 6. Update test config and dev-setup guide

**File:** `argus/backend/tests/conftest.py`

The test app config provides fake `EMAIL_*` values only to satisfy the eager credential
read. With `EMAIL_ENABLED: false` in the test config those keys are never read and the
fake values can be removed:

```python
# before
"EMAIL_SENDER": "unit tester", "EMAIL_SENDER_PASS": "pass",
"EMAIL_SENDER_USER": "qa", "EMAIL_SERVER": "fake", "EMAIL_SERVER_PORT": 25

# after — replaced with:
"EMAIL_ENABLED": False
```

**File:** `docs/dev-setup.md`

Update the minimal dev config to use `EMAIL_ENABLED: false` and remove the
`EMAIL_*` placeholder values. Update the troubleshooting section accordingly.

---

## Out of Scope

- `jenkins_service.py:126` already uses `config.get(...)` so it is safe; no change needed.
- GitHub OAuth login (`GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`) is a separate
  concern from issue tracking and is not changed here.
- The hardcoded `scylladb.atlassian.net` URL pattern in `jira_service.py:83` is not
  changed; it is only relevant when `JIRA_ENABLED` is true.

---

## Affected Files Summary

| File                                            | Change                                                                                         |
| ----------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| `argus/backend/service/argus_service.py`        | Remove dead `github_headers` assignment                                                        |
| `argus/backend/service/issue_service.py`        | Read `GITHUB_ENABLED` / `JIRA_ENABLED` from config as per-integration defaults                 |
| `argus/backend/util/send_email.py`              | Move `_retrieve_credentials()` from `__init__` to `_connect()`                                 |
| `argus/backend/service/notification_manager.py` | Skip `EmailNotificationServiceSender` when `EMAIL_ENABLED: false`                              |
| `argus_web.example.yaml`                        | Document `GITHUB_ENABLED`, `JIRA_ENABLED`, and `EMAIL_ENABLED` flags inline per feature commit |
| `argus/backend/tests/conftest.py`               | Replace fake `EMAIL_*` values with `EMAIL_ENABLED: false`; remove dead fixtures                |
| `docs/dev-setup.md`                             | Add `EMAIL_ENABLED: false` to minimal dev config; remove `EMAIL_*` placeholders                |
