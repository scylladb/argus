# ARGUS-185 — Show what a test does where its runs are planned and read

## Problem

A test in Argus is a name, a Jenkins path and a plugin name. A person who
builds a release plan picks tests by name, guesses what each job does, and
opens Jenkins or the scylla-cluster-tests repository to confirm the tier, the
duration and the backends. A newcomer or a planner from another team cannot
pick without help. An LLM agent that builds a plan through the planning API
gets the same name and nothing else, so it either guesses or reads the SCT
code, which is slow and imprecise.

The knowledge exists. SCT test-case YAML files carry a `test_metadata` block
with a prose description, a tier, a type, a duration class and the supported
backends, and the SCT job creator copies it into the Jenkins job description.
Argus imports the job as a test and shows none of it.

## Who it affects

- A release planner in the planning grid and the test picker, who needs the
  description, the tier, the type, the duration class and the backends of a
  test before adding it to a plan.
- A reader of a run page, who wants to know what the job under the run is for.
- An LLM agent that reads a plan (about 50 tests) or a release (about 500
  tests) through the planning API and needs what each test does in the same
  response, so it selects tests without a second lookup or a scan of SCT.
- The SCT team, whose documentation effort ([scylla-cluster-tests#14818] and
  the rollout tickets under SCT-35) stops at the Jenkins job description.

[scylla-cluster-tests#14818]: https://github.com/scylladb/scylla-cluster-tests/pull/14818

## Evidence

ARGUS-155: "One of the downsides when people are planning -- they don't see
the all the information... you need to first learn and figure out what the
tests from SCT and then come back to Argus and do the planning."

ARGUS-185: "Goal: let people understand what each test/job is about (purpose,
tier, type, duration, supported backends) without having to dig into Jenkins
job config or SCT YAML."

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

On the same day 208 jobs under the release folders Argus monitors carried
that block. The Argus row of that test has no description.

The questions the review of [scylladb/argus#1096] settled, with the answer
that closed each one.

[scylladb/argus#1096]: https://github.com/scylladb/argus/pull/1096

**How is the data used, and do we search over it?**

> do we plan searching over this metadata and how these searches will look
> like?

> We likely need this if the plan for these descriptions is to be fetchable
> by the plan executor API - e.g. if we want to start a set of tests.
> Although, since those tests are already part of the plan this might not be
> needed - we can just iterate over tests in the plan and so additional
> lookup table isn't needed.

> this is a core question, how we're going to use this data - so we can make
> better decision. We need to change the intent - not to state how we collect
> and store this data, but how this data is going to be used.

The use is a read of a plan's or a release's tests, each with its metadata.
No search by label in this task.

**Is a read-time fetch from Jenkins needed?**

> why we need that if we update it every 5 minutes with jenkins scan?

> test doesn't exist with a jenkins scan and a jenkins scan will fill those
> descriptions when they exist. The timeframe is too short to worry about
> missing data. Will remove this bit.

**Must Argus keep SCT's exact field set?**

> why we need to keep the format - why client's can't define own formats. I
> suppose 'map' would be better here (more flexible)

> I think we'll settle on a single map for data provided now. Additional
> tables can be designed later as a followup in case we hit bottlenecks as
> primary use case can just iterate over the plan (like 50 tests) or release
> (500-ish)

**Which Jenkins trees does the scan read?**

> I wonder if we need to query all jobs. Maybe we should have a list of trees
> we observe? no need to observe unmaintained scylla versions?

> If the 'dormant' means ones that are disabled in argus admin, then I think
> we could do that (so we have control over it without code change)

## What good looks like

- A test entry in the planning grid, the test picker and the planning API
  carries the description and every label SCT wrote for it. An agent that
  lists a plan or a release reads them in the call it already makes.
- The run page shows, in a tab of its own, what the test under the run is
  for.
- A job whose description gains or changes its metadata shows the change in
  Argus within one scan cycle. A job without the block looks as it does
  today.
- A label SCT adds later appears in Argus without a schema change.
- An administrator excludes an unmaintained release from the scan by marking
  it dormant, with no code change.

## Out of scope

- The SCT side: the YAML format, the job creator, the description grammar.
  Findings about them go upstream as comments on scylla-cluster-tests#14818.
- Search or filtering of tests by label. Agreed in the review of #1096: the
  use iterates over a plan or a release. A lookup table is a follow-up when a
  search use case exists.
- A read-time fetch from Jenkins. Agreed in the review of #1096.
- Editing the metadata in the admin panel. Jenkins owns the values.
- The Go CLI output (`argus plan search`), an ARGUS-155 acceptance item.
- A metadata copy on a run.
- The generated test catalog of ARGUS-155 track 1.
