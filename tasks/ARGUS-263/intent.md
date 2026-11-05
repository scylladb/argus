# ARGUS-263 — Show the hydra tunnel command for the monitor of an SCT run

## Problem

Because of CVE-2026-98432 (SCT-1412), SCT monitor nodes no longer get a public
IP (SCT-1420). The Grafana and Prometheus of a running test are reachable only
through an SSH tunnel that `hydra tunnel` opens.

The run page does not help with that:

- The *Open Grafana* button in the run header points at
  `http://<public_ip>:3000/`. A monitor without a public IP gives a link to
  `http://:3000/`, which a browser cannot open.
- The Resources tab lists the monitor node, but nothing on it says how to
  reach it. People look up the test id and the node name by hand, then type
  the `hydra tunnel` command themselves.

## Who it affects

Engineers who watch or debug a running SCT test from its Argus run page and
need its Grafana, its Prometheus, or a shell on the monitor node.

## Evidence

Jira ARGUS-263:

> Because of CVE-2026-98432 (SCT-1412), SCT monitor nodes no longer get a
> public IP (SCT-1420). The Grafana and Prometheus of a running test are
> reachable only through an SSH tunnel. The Grafana link on the run page now
> points to a private address that a browser cannot open.
>
> People need the tunnel command for the monitor of the run in front of them,
> without searching for the test id and the node name.

`frontend/TestRun/TestRunInfo.svelte`:

```
href="http://{locateGrafanaNode().instance_info.public_ip}:3000/"
```

## What good looks like

- A running monitor on the Resources tab has a **Connect** button. It opens a
  popover with a copy button for each command, filled with the test id and the
  monitor name:

  ```
  hydra tunnel -t <test_id> -p 3000 <monitor-name>
  hydra tunnel -t <test_id> -p 9090 <monitor-name>
  hydra ssh -t <test_id> <monitor-name>
  ```

- The run header offers the same popover next to the Grafana link. The link
  does not point at a missing address when the monitor has no public IP.
- A terminated monitor or a finished run shows
  `hydra investigate show-monitor <test_id>` instead of the tunnel commands.
- A copy button copies the exact command.
- A frontend unit test covers the command strings for a running and a
  terminated monitor.

## Out of scope

- Any SCT change. SCT already sends the monitor resource with its name, type,
  addresses and state.
- Any backend change in Argus.
- Proxying Grafana or Prometheus through Argus.
