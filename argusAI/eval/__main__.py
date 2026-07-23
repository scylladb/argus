"""CLI: run the evaluation sweep and render the report.

    python -m argusAI.eval --config argusAI/eval/config.example.yaml

Sub-modes:
    --fetch-only     collect events into out/events.json and stop (no API calls)
    --report-only    re-render the HTML from an existing out/results.json (no API calls)
    --write-baseline DIR   freeze the current run's aggregate scores as a regression baseline
    --baseline DIR         re-run on the frozen set and check for regressions (exit 1 on FAIL)

Everything else (models, prompts, events, judge) comes from the YAML config; only the
API key comes from the environment (OPENAI_API_KEY by default).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import webbrowser
from pathlib import Path

from .baseline import BASELINE_FILE, EVENTS_FILE, compare, load_baseline, render_table, save_baseline
from .config import EvalConfig
from .events_source import EventFetcher, save_events
from .harness import EvalHarness
from .report import report_from_file, write_report

_DEFAULT_TOLERANCE = 3.0


def _write_baseline(results: dict, out_dir: Path, tolerance: float) -> None:
    """Persist baseline.json plus the frozen events beside it, so a later --baseline run
    scores the identical inputs."""
    path = save_baseline(results, out_dir, tolerance)
    (out_dir / EVENTS_FILE).write_text(json.dumps(results.get("events", []), indent=2), encoding="utf-8")
    print(f"Baseline: {path} (+ {out_dir / EVENTS_FILE}, {results.get('num_events')} events)")


def _run_baseline_check(cfg: EvalConfig, base_dir: Path, tolerance: float | None, report_path: Path) -> int:
    """Re-run the sweep on the frozen event set and diff aggregate scores against the stored
    baseline. Exit non-zero if a gated axis regressed beyond tolerance."""
    base_path, events_path = base_dir / BASELINE_FILE, base_dir / EVENTS_FILE
    if not base_path.exists() or not events_path.exists():
        print(f"Baseline incomplete: need both {base_path} and {events_path}.", file=sys.stderr)
        return 1
    baseline = load_baseline(base_path)
    tol = tolerance if tolerance is not None else baseline.get("tolerance", _DEFAULT_TOLERANCE)
    cfg.events_file = events_path  # regression check must score the identical frozen inputs
    results = EvalHarness(cfg).run()
    write_report(results, report_path)
    rows, ok = compare(results, baseline, tol)
    print("\n" + render_table(rows, baseline, tol))
    print(f"\nReport: {report_path}\n{'PASS — no regressions' if ok else 'FAIL — regressions above'}")
    return 0 if ok else 1


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m argusAI.eval", description=__doc__)
    parser.add_argument("--config", required=True, help="path to eval YAML config")
    parser.add_argument("--fetch-only", action="store_true", help="only collect events, no API calls")
    parser.add_argument("--report-only", action="store_true", help="only re-render report from results.json")
    parser.add_argument("--write-baseline", metavar="DIR", help="freeze this run's scores as a regression baseline")
    parser.add_argument("--baseline", metavar="DIR", help="re-run on the frozen set and check for regressions")
    parser.add_argument(
        "--tolerance",
        type=float,
        default=None,
        help=f"allowed faithfulness/coverage drop in points (default: baseline's, else {_DEFAULT_TOLERANCE})",
    )
    parser.add_argument("--open", action="store_true", help="open the HTML report in a browser when done")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    _setup_logging(args.verbose)

    cfg = EvalConfig.from_yaml(args.config)
    out_dir = cfg.output_dir
    results_path = out_dir / "results.json"
    report_path = out_dir / "report.html"

    if args.report_only:
        if not results_path.exists():
            print(f"No results at {results_path}; run the sweep first.", file=sys.stderr)
            return 1
        report_from_file(results_path, report_path)
        print(f"Report: {report_path}")
        if args.write_baseline:  # seed a baseline from an existing run, spending no tokens
            results = json.loads(results_path.read_text(encoding="utf-8"))
            _write_baseline(results, Path(args.write_baseline), args.tolerance or _DEFAULT_TOLERANCE)
        if args.open:
            webbrowser.open(report_path.resolve().as_uri())
        return 0

    if args.baseline:
        return _run_baseline_check(cfg, Path(args.baseline), args.tolerance, report_path)

    if args.fetch_only:
        fetcher = EventFetcher(argus_cli=cfg.argus_cli, no_cache=cfg.no_cache)
        events = fetcher.collect(
            run_ids=cfg.run_ids,
            test_id=cfg.test_id,
            test_run_limit=cfg.test_run_limit,
            max_events=cfg.max_events,
        )
        save_events(events, out_dir / "events.json")
        print(f"Collected {len(events)} events -> {out_dir / 'events.json'}")
        return 0 if events else 2

    harness = EvalHarness(cfg)  # validates the API key up front
    results = harness.run()
    write_report(results, report_path)
    print(f"\nResults: {results_path}\nReport:  {report_path}")
    if args.write_baseline:
        _write_baseline(results, Path(args.write_baseline), args.tolerance or _DEFAULT_TOLERANCE)
    if args.open:
        webbrowser.open(report_path.resolve().as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
