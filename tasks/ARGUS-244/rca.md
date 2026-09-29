# ARGUS-244 — "Run SCT Test" Jenkins stage fails on multi-address `email_recipients`

**Date**: 2026-09-29

## Bug summary

The Jenkins "Run SCT Test" stage fails with a bash conditional-expression
syntax error whenever the job's `email_recipients` parameter contains more
than one comma-separated email address. The reported error token
`lukasz.sojka@scylladb.com""` — a doubled closing quote sitting after an
address — shows that a shell `[[ ... ]]` conditional is receiving the raw,
comma-and-space-separated `email_recipients` value wrapped in an extra layer
of quoting, e.g. something shaped like:

```sh
[[ -n ""lukasz.sojka@scylladb.com, other.user@scylladb.com"" ]]
```

Because the outer `""` closes immediately, bash tokenizes the rest of the
value as a run of unquoted words separated by the comma and the space, and
the `[[ ... ]]` conditional expression parser rejects the extra tokens with a
syntax error.

## Root cause

The failing conditional does not live in this repository. It lives in the
**scylla-cluster-tests** repository's `jenkins-pipelines/` tree — either in a
`*.jenkinsfile` pipeline definition or in a shared Groovy library under
`vars/` — where the `email_recipients` build parameter is rendered into a
bash `[[ ... ]]` test with one quoting layer too many. A single-address value
happens to still parse (no embedded whitespace to split on), which is why the
bug only surfaces once a user supplies more than one address.

## Evidence that the fix does not belong in scylladb/argus

- **Argus never renders a shell script.** `JenkinsService.build_job`
  (`argus/backend/service/jenkins_service.py:366-373`) forwards the caller's
  `params` dict, including `email_recipients`, straight to
  `python-jenkins`'s `build_job` call over the Jenkins HTTP API:

  ```python
  async def build_job(self, build_id: str, params: dict, user_override: str = None, requested_by: User | None = None):
      queue_number = await asyncio.to_thread(self._jenkins.build_job, build_id, {
          **params,
          self.RESERVED_PARAMETER_NAME: requested_by.email.split('@')[0] if not user_override else user_override
      })
      return queue_number
  ```

  There is no templating, string interpolation, or shell invocation on the
  Argus side — the value is passed through the Jenkins remote API as a plain
  build parameter, byte for byte.

- **Multi-address values are the intended, supported input.** The frontend
  wizard defines `email_recipients` as a free-form string parameter with the
  help text "Comma separated list of email recipients"
  (`frontend/TestRun/Jenkins/SCTParameterWizard.svelte:640-650`), and its
  `validate` functions (lines 634-637, 646-648) never reject or reformat
  multiple addresses. Argus intends for users to submit exactly the kind of
  value that reproduces the bug.

- **The `.jenkinsfile` is treated as an external artifact, not something
  Argus generates.** `JenkinsService._verify_sct_settings`
  (`argus/backend/service/jenkins_service.py:233-265`) verifies a job's
  pipeline settings by fetching `pipelineFile` from a GitHub repository over
  the GitHub Contents API (`gitRepo`/`gitBranch`/`pipelineFile` settings) —
  it reads the pipeline file from GitHub, it does not write or render one.
  `frontend/Common/JenkinsSettingsHelp.js` describes `pipelineFile` as "Path
  inside repository to the pipeline (.jenkinsfile) of the job", confirming
  the same external-artifact model on the frontend.

- **Pipeline definitions live in the SCT repo's `jenkins-pipelines/` tree.**
  The job-description fixtures in
  `argus/backend/tests/build_system_monitor/test_parse_test_metadata.py`
  (lines 6 and 183) show real job descriptions of the form
  `jenkins-pipelines/oss/longevity/longevity-10gb-3h.jenkinsfile` and
  `jenkins-pipelines/oss/tier1/gemini-1tb-10h.jenkinsfile` — paths that exist
  in scylla-cluster-tests, not in scylladb/argus.

- **An exhaustive search of this repository found no pipeline code at all.**
  Zero `*.groovy` files, zero `Jenkinsfile*` / `*.jenkinsfile` files, and zero
  occurrences of the string "Run SCT Test" anywhere in scylladb/argus.

## Recommended upstream fix (scylla-cluster-tests, not this repo)

In the `jenkins-pipelines/` definition or shared Groovy library that renders
the "Run SCT Test" stage, interpolate `email_recipients` exactly once with a
single quoting layer, e.g.:

```sh
[[ -n "${email_recipients}" ]]
```

or, better, avoid the shell entirely and test the parameter directly in
Groovy before it ever reaches a shell step:

```groovy
if (params.email_recipients?.trim()) {
    // ...
}
```

Either change removes the doubled-quote token and lets bash treat the whole
comma-and-space-separated value as a single word, regardless of how many
addresses it contains.

## Closing note

This ticket should be re-filed / transferred to the **scylla-cluster-tests**
repository, whose `jenkins-pipelines/` tree owns the failing conditional.
scylladb/argus has no ownership of that pipeline code and forwards the
`email_recipients` parameter unmodified, so **no code change is needed in
scylladb/argus** for this issue.
