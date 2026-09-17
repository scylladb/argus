# ARGUS-65 — Avoid packages duplicates

## Problem

The packages list of an SCT test run can hold two identical rows. The Packages
tab of the run shows the same package twice. A reader that keys the rows by
package name fails on the duplicate.

## Who it affects

Every SCT run that reports one package from more than one place at the same
time. The stress threads report the `java-driver` package once per loader and
per CPU, and they run in parallel.

## Evidence

Run `8e0ba893-47cc-420f-88b5-0d79c5afd9c2` on staging. The `packages` field of
the run response holds:

```json
{
    "name": "java-driver",
    "version": "3.11.5.7",
    "date": null,
    "revision_id": null,
    "build_id": null
},
{
    "name": "java-driver",
    "version": "3.11.5.7",
    "date": null,
    "revision_id": null,
    "build_id": null
}
```

The duplicate rows made the Packages tab crash. Pull request 830 works around
the crash in the frontend. Jira: [ARGUS-65](https://scylladb.atlassian.net/browse/ARGUS-65).

## What good looks like

Two submissions of an identical package, at the same time or one after the
other, leave one row in `packages`. Two different versions of one package name
stay as two rows. A package that a parallel submission adds is not lost.

## Out of scope

- A cleanup of duplicate rows that the database already holds.
- A change to the `PackageVersion` type, the client library, or the frontend.
