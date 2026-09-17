# ARGUS-185 — Persist and surface SCT test metadata

## Problem

A test in Argus carries a name, a Jenkins path and a plugin name. It carries
no description, no tier, no type, no duration class and no list of supported
backends. A person who plans a release reads the test name, guesses what the
job does, and opens Jenkins or the scylla-cluster-tests repository to confirm.
An LLM agent that plans a release has the same gap and no way to close it
from the Argus API.

scylla-cluster-tests writes a `test_metadata` block into each test-case YAML
and copies it into the Jenkins job description when it creates or reconfigures
the job. Argus imports the job as a test and drops the description. PR
scylladb/argus#1012 parses the block and stores nothing.

## Who it affects

A release planner in the planning grid and the test picker. A reader of a run
page. An LLM agent that selects tests through the planning API. The SCT team,
whose metadata reaches Jenkins and stops there.

## Evidence

ARGUS-185: "This metadata originates from the test-case YAML test_metadata
field introduced in scylla-cluster-tests#14818, and currently is parsed but
not persisted or shown anywhere in Argus."

ARGUS-155: "One of the downsides when people are planning -- they don't see
the all the information... you need to first learn and figure out what the
tests from SCT and then come back to Argus and do the planning."

Description of `scylla-master/longevity/longevity-10gb-3h-test`, read from
Jenkins on 2026-09-17:

```
jenkins-pipelines/oss/longevity/longevity-10gb-3h.jenkinsfile

Basic longevity test running cassandra-stress write workload at QUORUM consistency for ~4 hours on a 6-node single-DC cluster with SisyphusMonkey nemesis. Validates cluster stability under moderate write load with continuous chaos operations.

### TestMetadata
tier: tier1
test_type: longevity
duration_class: short
supported_backends: ['aws', 'gce', 'azure']
```

The same day, 208 jobs under the release folders the scanner monitors carried
the `### TestMetadata` block. None of six probed jobs carried the
`<testMetadata>` element in `config.xml` that PR #1012 reads first: Jenkins
drops the element when it saves the job.

`argus_test_v2` row of that test: `description` is NULL.

## What good looks like

Within one scan cycle of a job being created or reconfigured, its Argus test
carries the description, the tier, the type, the duration class and the
backends. The planning grid, the test picker and a tab on the run page show
them. The planning API returns them on every test entry. A job whose
description loses the block keeps the values it had.

## Out of scope

The SCT side: the YAML format, the job creator, the description grammar.
Editing the metadata in the admin panel. The Go CLI output. A metadata copy
on a run. The generated test catalog of ARGUS-155 track 1.
