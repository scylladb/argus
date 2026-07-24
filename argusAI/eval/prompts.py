from __future__ import annotations

from argusAI.prompts import PRODUCTION_PROMPT_NAME, load_summary_prompts

PROMPTS: dict[str, str] = load_summary_prompts()

DEFAULT_PROMPT_NAME = PRODUCTION_PROMPT_NAME
