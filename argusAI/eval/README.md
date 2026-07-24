# Event Summarization — evaluation harness

Offline harness that answers the two questions PR #1016 asked before rollout:

1. **Which model?** — the cheapest one whose summaries stay faithful and lose no
   information a triager (or Zeus) needs.
2. **Is the prompt any good?** — iterate it on real events until the output is right.

It pulls real SCT `ERROR`/`CRITICAL` events from Argus (via the `argus` CLI),
summarizes each with several candidate models under a configurable prompt, scores every
summary against the **original** event with a frontier judge model, and renders a
self-contained HTML report: a quality-vs-cost decision graph plus every summary shown
side-by-side with its source so a human can verify the judge.

Nothing is hard-coded — **model and API key are configurable** (mandatory for
production), as is the prompt, the judge, and the pricing table.

## Setup

```bash
pip install -e '.[ai-eval]'          # installs openai + PyYAML
export OPENAI_API_KEY=sk-...          # key comes from the env, never the config file
```

The `argus` CLI must be authenticated (`argus auth`) — the harness shells out to it.

## Run

```bash
# 1. edit argusAI/eval/config.example.yaml: set run_ids/test_id, models, prompts, pricing
cp argusAI/eval/config.example.yaml argusAI/eval/config.yaml

# 2. (optional) collect events first, without spending any API tokens, and inspect them
python -m argusAI.eval --config argusAI/eval/config.yaml --fetch-only

# 3. full sweep: summarize × judge × render report
python -m argusAI.eval --config argusAI/eval/config.yaml --open

# re-render the HTML from an existing results.json (no API calls)
python -m argusAI.eval --config argusAI/eval/config.yaml --report-only --open
```

Outputs land in `output_dir` (default `argusAI/eval/out/`):

| File | What |
|------|------|
| `events.json`  | the deduplicated events that were evaluated (reusable via `events_file`) |
| `results.json` | every (event × model × prompt) cell: summary, tokens, cost, latency, judge score |
| `report.html`  | the presentable graph + per-event side-by-side summaries |

## Config

See `config.example.yaml` — commented in full. The key knobs:

- `models` — list of candidates; each `params` block is forwarded verbatim to the API
  call (`reasoning_effort`, `temperature`, `max_completion_tokens`, …).
- `prompts` — names from `prompts.py`; list several to A/B them on the same events.
- `judge_model` / `judge_enabled` — the frontier scorer (Opus-class / GPT-5-class).
- `pricing` — USD per 1M tokens; **the defaults are placeholders**, set real numbers or
  the cost axis is meaningless (unknown models are flagged in the report, never silent).

## Regression baseline

`out/` is gitignored, so a run's evidence lives only on your laptop. To keep a durable
reference that future prompt/model changes are checked against, freeze the current winner
into the tracked `baseline/` dir:

```bash
# seed a baseline (from a fresh sweep, or from an existing results.json without spending tokens)
python -m argusAI.eval --config ... --write-baseline argusAI/eval/baseline
python -m argusAI.eval --config ... --report-only --write-baseline argusAI/eval/baseline

# later: re-run on the *frozen* events and check for regressions (exit 1 on FAIL)
python -m argusAI.eval --config ... --baseline argusAI/eval/baseline
```

`baseline/` holds two committed files: `events.json` (the frozen input set — `--baseline`
forces the run onto it so inputs are identical) and `baseline.json` (per-`(model,prompt)`
mean scores). Comparison is **aggregate + tolerance**, not exact-match, because the
summarizer and judge are non-deterministic. A series **FAILs** only when faithfulness or
coverage drops more than `--tolerance` points (default 3) — the two axes that mean
information was dropped or invented. Conciseness, cost, and latency are shown as deltas but
never fail the check; new hallucinations or dropped-critical items are flagged inline.

Deliberately not wired into CI: each run spends real OpenAI tokens and the judge is
non-deterministic, so it's a manual pre-change gate, not an automated one.

## Iterating the prompt

`prompts.py` holds `PRODUCTION` (the current winner) and `BASELINE` (the naive one-liner,
kept as an A/B control). To try a new idea, **add a new named entry** rather than editing
`PRODUCTION` in place, list both in `prompts:`, and the report compares them head-to-head on
identical events — so a regression is visible, not lost. If the challenger wins, promote its
text into `PRODUCTION` here **and** into `argusAI/utils/summarizer.py`'s `DEFAULT_PROMPT`
(the two are kept byte-identical), which becomes the production `EVENT_SUMMARIZATION_PROMPT`
default. Older experiments aren't carried in this file — git history and the saved `out/`
reports are the record.

## Relation to production

`argusAI/utils/summarizer.py` (the `Summarizer` class) is shared: this harness and the
production worker call it identically, so a summary you approve here is byte-for-byte what
the worker will store for the same `(model, prompt)`.
