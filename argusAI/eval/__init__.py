"""Offline evaluation harness for event summarization.

Extracts real SCT ERROR/CRITICAL events (via the ``argus`` CLI), summarizes each
with several candidate models under a configurable prompt, scores the summaries for
information preservation with a frontier judge model, and renders a comparison graph
plus a per-event side-by-side HTML report.

This is the harness the design doc (docs/plans/event-summarization.md §7) requires to
pick ``OPENAI_SUMMARY_MODEL`` and to validate the prompt before rollout. Run it as::

    python -m argusAI.eval --config argusAI/eval/config.example.yaml

See ``argusAI/eval/README.md``.
"""
