"""Render results.json into a self-contained, presentable HTML report.

Two things the reviewers asked to *see* (PR #1016): a decision graph comparing models,
and the actual summaries so a human can judge whether information was lost. This module
produces both in one standalone HTML file (no external assets, no JS dependency, works
offline and in light/dark) so it can be opened, screenshotted into a deck, or published
as an Artifact.

Charts are hand-rolled inline SVG following the dataviz method: thin marks, baseline-
anchored rounded bars, selective direct labels, a legend for >1 series, recessive axes,
and the colorblind-safe Okabe-Ito categorical palette (validated for all CVD types).
The headline is a quality-vs-cost scatter — "the cheapest model that is good enough".
"""

from __future__ import annotations

import html
import json
import logging
from collections import defaultdict
from pathlib import Path

from .metrics import SeriesStats, aggregate_series, prompt_stat_line

LOGGER = logging.getLogger(__name__)

# Okabe-Ito qualitative palette — assigned in fixed order, never cycled.
PALETTE = ["#0072B2", "#E69F00", "#009E73", "#D55E00", "#CC79A7", "#56B4E9", "#F0E442", "#000000"]


# --- tiny SVG helpers -------------------------------------------------------


def _hbar(title: str, rows: list[tuple[str, float, str]], vmax: float, unit: str, fmt: str = "{:.1f}") -> str:
    """Horizontal bar chart. rows = [(label, value, color)]. Direct value labels."""
    row_h, gap, left, right, top = 26, 10, 160, 70, 34
    width = 720
    plot_w = width - left - right
    height = top + len(rows) * (row_h + gap)
    vmax = vmax or 1.0
    bars = []
    for i, (label, value, color) in enumerate(rows):
        y = top + i * (row_h + gap)
        w = max(2.0, plot_w * (value / vmax))
        bars.append(
            f'<text x="{left - 10}" y="{y + row_h * 0.7}" text-anchor="end" class="lbl">{html.escape(label)}</text>'
            f'<rect x="{left}" y="{y}" width="{w:.1f}" height="{row_h}" rx="4" fill="{color}"/>'
            f'<text x="{left + w + 6:.1f}" y="{y + row_h * 0.7}" class="val">{fmt.format(value)}{unit}</text>'
        )
    return (
        f'<figure class="chart"><figcaption>{html.escape(title)}</figcaption>'
        f'<svg viewBox="0 0 {width} {height}" role="img">'
        f"{''.join(bars)}</svg></figure>"
    )


def _scatter(title: str, points: list[tuple[str, float, float, str]], xlabel: str, ylabel: str) -> str:
    """Quality (y) vs cost (x) scatter. points = [(label, x, y, color)]."""
    width, height = 720, 420
    left, right, top, bottom = 64, 130, 34, 54
    plot_w, plot_h = width - left - right, height - top - bottom
    xs = [p[1] for p in points] or [0.0]
    ymax = 100.0
    xmax = max(xs) * 1.15 or 1.0
    marks = []
    # y gridlines at 0/25/50/75/100
    for gy in (0, 25, 50, 75, 100):
        yy = top + plot_h * (1 - gy / ymax)
        marks.append(
            f'<line x1="{left}" y1="{yy:.1f}" x2="{left + plot_w}" y2="{yy:.1f}" class="grid"/>'
            f'<text x="{left - 8}" y="{yy + 4:.1f}" text-anchor="end" class="tick">{gy}</text>'
        )
    for label, x, y, color in points:
        px = left + plot_w * (x / xmax)
        py = top + plot_h * (1 - y / ymax)
        marks.append(
            f'<circle cx="{px:.1f}" cy="{py:.1f}" r="7" fill="{color}" stroke="var(--surface)" stroke-width="2"/>'
            f'<text x="{px + 11:.1f}" y="{py + 4:.1f}" class="pt-lbl">{html.escape(label)}</text>'
        )
    return (
        f'<figure class="chart wide"><figcaption>{html.escape(title)}</figcaption>'
        f'<svg viewBox="0 0 {width} {height}" role="img">'
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" class="axis"/>'
        f'<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" y2="{top + plot_h}" class="axis"/>'
        f'<text x="{left + plot_w / 2}" y="{height - 12}" text-anchor="middle" class="axis-lbl">{html.escape(xlabel)}</text>'
        f'<text transform="translate(16,{top + plot_h / 2}) rotate(-90)" text-anchor="middle" class="axis-lbl">{html.escape(ylabel)}</text>'
        f"{''.join(marks)}</svg></figure>"
    )


_CSS = """
:root{--surface:#ffffff;--ink:#1a1a1a;--ink-2:#555;--muted:#888;--grid:#e6e6e6;--axis:#bbb;--card:#f7f7f8;--border:#e2e2e5;}
@media (prefers-color-scheme:dark){:root{--surface:#16181d;--ink:#e8e8ea;--ink-2:#aeb0b6;--muted:#7d808a;--grid:#2a2d34;--axis:#3a3d45;--card:#1e2129;--border:#2c2f37;}}
:root[data-theme=dark]{--surface:#16181d;--ink:#e8e8ea;--ink-2:#aeb0b6;--muted:#7d808a;--grid:#2a2d34;--axis:#3a3d45;--card:#1e2129;--border:#2c2f37;}
:root[data-theme=light]{--surface:#ffffff;--ink:#1a1a1a;--ink-2:#555;--muted:#888;--grid:#e6e6e6;--axis:#bbb;--card:#f7f7f8;--border:#e2e2e5;}
*{box-sizing:border-box}body{margin:0;background:var(--surface);color:var(--ink);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;padding:32px;max-width:1180px;margin:0 auto}
h1{font-size:24px;margin:0 0 4px}h2{font-size:18px;margin:36px 0 12px;border-bottom:1px solid var(--border);padding-bottom:6px}
.meta{color:var(--ink-2);font-size:13px;margin-bottom:8px}
.charts{display:flex;flex-wrap:wrap;gap:20px}
.chart{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:14px 16px;margin:0;flex:1 1 340px}
.chart.wide{flex-basis:100%}figcaption{font-weight:600;font-size:14px;margin-bottom:8px}
svg{width:100%;height:auto;overflow:visible}
.lbl{fill:var(--ink);font-size:12px}.val{fill:var(--ink-2);font-size:12px}.tick{fill:var(--muted);font-size:11px}
.pt-lbl{fill:var(--ink);font-size:12px}.axis{stroke:var(--axis);stroke-width:1}.grid{stroke:var(--grid);stroke-width:1}
.axis-lbl{fill:var(--ink-2);font-size:12px}
table{border-collapse:collapse;width:100%;font-size:13px;margin-top:8px}
th,td{text-align:right;padding:7px 10px;border-bottom:1px solid var(--border)}th:first-child,td:first-child{text-align:left}
th{color:var(--ink-2);font-weight:600}tbody tr:first-child td{font-weight:600}
.legend{display:flex;flex-wrap:wrap;gap:14px;margin:6px 0 2px;font-size:13px}
.legend span{display:inline-flex;align-items:center;gap:6px}.sw{width:12px;height:12px;border-radius:3px;display:inline-block}
.event{border:1px solid var(--border);border-radius:10px;margin:14px 0;overflow:hidden}
.event>summary{cursor:pointer;padding:12px 16px;background:var(--card);font-weight:600;list-style:none}
.event>summary::-webkit-details-marker{display:none}
.ev-body{padding:12px 16px}
.orig{white-space:pre-wrap;background:var(--card);border:1px solid var(--border);border-radius:8px;padding:10px;font:12px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace;max-height:280px;overflow:auto}
.sums{display:flex;flex-wrap:wrap;gap:12px;margin-top:12px}
.sum{flex:1 1 300px;border:1px solid var(--border);border-radius:8px;padding:10px}
.sum h4{margin:0 0 6px;font-size:13px;display:flex;justify-content:space-between;align-items:center}
.sum .txt{white-space:pre-wrap;font:12.5px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace}
.score{font-size:11px;color:var(--ink-2);font-weight:500}
.tag{display:inline-block;font-size:10px;padding:1px 6px;border-radius:10px;background:var(--grid);color:var(--ink-2);margin-left:4px}
.warn{color:#D55E00}.err{color:#D55E00;font-style:italic}
.pill{font-size:11px;color:var(--ink-2);font-weight:400}
.prompt{border:1px solid var(--border);border-radius:10px;margin:10px 0;overflow:hidden}
.prompt>summary{cursor:pointer;padding:11px 15px;background:var(--card);list-style:none;display:flex;justify-content:space-between;gap:14px;align-items:baseline;flex-wrap:wrap}
.prompt>summary::-webkit-details-marker{display:none}
.prompt .pname{font-weight:600}
.prompt .pstat{font-size:12px;color:var(--ink-2)}
.prompt .ptext{white-space:pre-wrap;padding:12px 15px;font:12.5px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;border-top:1px solid var(--border)}
.prompt.winner{border-color:#009E73;box-shadow:0 0 0 1px #009E73 inset}
.badge{display:inline-block;font-size:10px;font-weight:700;padding:1px 7px;border-radius:10px;background:#009E73;color:#fff;margin-left:8px;letter-spacing:.3px}
"""


def _legend(stats: list[SeriesStats], colors: dict[str, str]) -> str:
    items = "".join(
        f'<span><i class="sw" style="background:{colors[s.key]}"></i>{html.escape(s.key)}</span>' for s in stats
    )
    return f'<div class="legend">{items}</div>'


def _summary_table(stats: list[SeriesStats], judged: bool) -> str:
    head = (
        "<tr><th>Model" + ("·prompt" if any("·" in s.key for s in stats) else "") + "</th>"
        "<th>Overall</th><th>Cover</th><th>Faith</th><th>Concise</th>"
        "<th>Compress</th><th>Out tok</th><th>Cost/ev</th><th>Latency</th><th>Drop</th><th>Halluc</th><th>Err</th></tr>"
    )
    body = ""
    for s in stats:
        ov = f"{s.avg_overall:.1f}" if judged else "—"
        body += (
            f"<tr><td>{html.escape(s.key)}</td>"
            f"<td>{ov}</td><td>{s.avg_coverage:.0f}</td><td>{s.avg_faithfulness:.0f}</td>"
            f"<td>{s.avg_conciseness:.0f}</td><td>{s.avg_compression * 100:.0f}%</td>"
            f"<td>{s.avg_completion_tokens:.0f}</td><td>${s.avg_cost:.5f}</td>"
            f"<td>{s.avg_latency_ms:.0f}ms</td><td>{s.total_dropped}</td>"
            f"<td>{s.total_hallucinations}</td><td>{s.errors}</td></tr>"
        )
    return f"<table><thead>{head}</thead><tbody>{body}</tbody></table>"


def _prompts_section(results: dict) -> str:
    """Show every evaluated prompt's full text next to its aggregate score, best first
    and flagged CHOSEN — so a reader can see exactly what changed prompt-to-prompt and
    why the winner was picked, without leaving the page."""
    prompts = results.get("prompts", {})
    if not prompts:
        return ""
    scored: dict[str, list[dict]] = defaultdict(list)
    for c in results.get("cells", []):
        j = c.get("judge")
        # Skip errored cells and cells with no judge score (judge disabled/errored) —
        # otherwise mean() over c["judge"]["overall"] dereferences None and aborts the report.
        if not c.get("error") and j and not j.get("error"):
            scored[c["prompt_name"]].append(c)

    rows = []
    for name, text in prompts.items():
        stat, sortkey = prompt_stat_line(scored.get(name, []))
        rows.append((sortkey, name, text, stat))
    rows.sort(key=lambda r: -r[0])
    # The CHOSEN prompt is the production decision, not merely the top raw-quality score —
    # v5 was picked for equal quality at far better compression. Honor an explicit
    # 'chosen_prompt' in the results; fall back to the top scorer only if none is set.
    chosen = results.get("chosen_prompt")
    best = chosen if chosen in prompts else (rows[0][1] if rows and rows[0][0] >= 0 else None)

    out = []
    for _sortkey, name, text, stat in rows:
        win = name == best
        badge = '<span class="badge">CHOSEN</span>' if win else ""
        out.append(
            f'<details class="prompt{" winner" if win else ""}"{" open" if win else ""}><summary>'
            f'<span class="pname">{html.escape(name)}{badge}</span>'
            f'<span class="pstat">{html.escape(stat)}</span></summary>'
            f'<div class="ptext">{html.escape(text)}</div></details>'
        )
    return "".join(out)


def _tags(j: dict) -> str:
    out = ""
    drop = j.get("dropped_critical") or []
    hall = j.get("hallucinations") or []
    if drop:
        out += f'<span class="tag warn">dropped: {html.escape(", ".join(drop)[:80])}</span>'
    if hall:
        out += f'<span class="tag warn">hallucinated: {html.escape(", ".join(hall)[:80])}</span>'
    return out


def _summary_card(c: dict, show_prompt: bool) -> str:
    """One model/prompt summary card for the per-event side-by-side view."""
    j = c.get("judge") or {}
    if c.get("error"):
        score, txt, tags = '<span class="err">failed</span>', html.escape(c["error"]), ""
    elif not c.get("judge") or j.get("error"):
        # judge disabled (null) or errored — show the summary without a misleading "Q 0".
        score, txt, tags = '<span class="score">judge n/a</span>', html.escape(c.get("summary", "")), ""
    else:
        score = (
            f'<span class="score">Q {j.get("overall", 0):.0f} · '
            f"cov {j.get('coverage', 0)} · faith {j.get('faithfulness', 0)}</span>"
        )
        txt, tags = html.escape(c.get("summary", "")), _tags(j)
    name = html.escape(c["model_label"])
    if show_prompt:
        name += f' <span class="tag">{html.escape(c["prompt_name"])}</span>'
    return f'<div class="sum"><h4><span>{name}</span>{score}</h4><div class="txt">{txt}</div>{tags}</div>'


def _event_header(ev: dict, key: str) -> str:
    header = f"{html.escape(ev.get('event_type', 'event'))} · {html.escape(ev.get('severity', ''))}"
    if ev.get("node"):
        header += f" · {html.escape(ev['node'])}"
    return header + f' <span class="pill">({ev.get("message_chars", len(key))} chars)</span>'


def _events_section(results: dict) -> str:
    by_event: dict[str, list[dict]] = defaultdict(list)
    for c in results.get("cells", []):
        by_event[c["event_key"]].append(c)
    events = {e["message"].strip(): e for e in results.get("events", [])}

    blocks = []
    for key, cs in by_event.items():
        ev = events.get(key.strip(), {})
        show_prompt = len({x["prompt_name"] for x in cs}) > 1
        ordered = sorted(cs, key=lambda x: (x["model_label"], x["prompt_name"]))
        sums = "".join(_summary_card(c, show_prompt) for c in ordered)
        blocks.append(
            f'<details class="event"><summary>{_event_header(ev, key)}</summary>'
            f'<div class="ev-body"><div class="orig">{html.escape(ev.get("message", key))}</div>'
            f'<div class="sums">{sums}</div></div></details>'
        )
    return "".join(blocks)


def render(results: dict) -> str:
    stats, _ = aggregate_series(results)
    judged = results.get("judge_model") is not None
    colors = {s.key: PALETTE[i % len(PALETTE)] for i, s in enumerate(stats)}

    charts = []
    if judged:
        charts.append(
            _scatter(
                "Quality vs. cost — the cheapest model that's good enough",
                [(s.key, s.avg_cost, s.avg_overall, colors[s.key]) for s in stats],
                "Avg cost per event (USD)",
                "Avg quality (0–100)",
            )
        )
        charts.append(
            _hbar(
                "Overall quality (higher is better)",
                [(s.key, s.avg_overall, colors[s.key]) for s in stats],
                100,
                "",
                "{:.0f}",
            )
        )
    charts.append(
        _hbar(
            "Compression — summary size as % of original (lower = more compression)",
            [(s.key, s.avg_compression * 100, colors[s.key]) for s in stats],
            max((s.avg_compression * 100 for s in stats), default=100),
            "%",
            "{:.0f}",
        )
    )
    charts.append(
        _hbar(
            "Avg cost per event (USD)",
            [(s.key, s.avg_cost, colors[s.key]) for s in stats],
            max((s.avg_cost for s in stats), default=0.001),
            "",
            "${:.5f}",
        )
    )
    charts.append(
        _hbar(
            "Avg latency",
            [(s.key, s.avg_latency_ms, colors[s.key]) for s in stats],
            max((s.avg_latency_ms for s in stats), default=1),
            "ms",
            "{:.0f}",
        )
    )

    unknown = results.get("unknown_priced_models") or []
    default_priced = results.get("default_priced_models") or []
    warn = ""
    if unknown:
        warn += (
            f'<p class="warn">⚠ No pricing configured for: {html.escape(", ".join(unknown))} '
            f"— their cost shows as $0. Add them under <code>pricing:</code> in the config.</p>"
        )
    if default_priced:
        warn += (
            f'<p class="warn">⚠ Using built-in placeholder pricing for: {html.escape(", ".join(default_priced))} '
            f"— verify the cost axis, or set real rates under <code>pricing:</code> in the config.</p>"
        )

    prompts_used = results.get("prompts", {})
    prompt_note = " · ".join(sorted(prompts_used.keys()))

    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Event Summarization — model evaluation</title><style>{_CSS}</style></head><body>
<h1>Event Summarization — model evaluation</h1>
<div class="meta">Generated {html.escape(results.get("generated_at", ""))} ·
{results.get("num_events", 0)} unique events · {len(stats)} series ·
judge: {html.escape(str(results.get("judge_model")))} · prompts: {html.escape(prompt_note)}</div>
{warn}
<h2>Comparison</h2>
{_legend(stats, colors)}
<div class="charts">{"".join(charts)}</div>
<h2>Aggregate metrics</h2>
{_summary_table(stats, judged)}
<h2>Prompts evaluated (full text — click to expand)</h2>
{('<p class="meta">' + html.escape(results["decision_note"]) + "</p>") if results.get("decision_note") else ""}
{_prompts_section(results)}
<h2>Per-event summaries (click to expand)</h2>
{_events_section(results)}
</body></html>"""


def write_report(results: dict, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render(results), encoding="utf-8")
    LOGGER.info("Wrote HTML report to %s", out_path)
    return out_path


def report_from_file(results_path: Path, out_path: Path) -> Path:
    results = json.loads(Path(results_path).read_text(encoding="utf-8"))
    return write_report(results, out_path)
