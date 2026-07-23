from __future__ import annotations

from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent

PRODUCTION_PROMPT_NAME = "v1_surgical"
JUDGE_PROMPT_NAME = "judge"


def load_prompt(name: str) -> str:
    path = PROMPTS_DIR / f"{name}.md"
    if not path.is_file():
        available = sorted(p.stem for p in PROMPTS_DIR.glob("*.md"))
        raise FileNotFoundError(f"No prompt '{name}' at {path}. Available: {available}")
    return path.read_text(encoding="utf-8").strip()


def load_summary_prompts() -> dict[str, str]:
    return {p.stem: p.read_text(encoding="utf-8").strip() for p in sorted(PROMPTS_DIR.glob("v*.md"))}
