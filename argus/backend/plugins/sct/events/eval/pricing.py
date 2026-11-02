"""Token pricing → dollar cost.

Prices change and new models appear, so the table is a *default* the config can extend
or override (``pricing:`` block). Values are USD per 1M tokens. ``cached`` is the
discounted input rate applied to ``cached_tokens`` (prompt cache reads); when a model has no
separate cached rate it falls back to the input rate. Cache writes bill at 1.25x the input rate.

These defaults are placeholders — set the real numbers in your config before trusting the
cost axis of the report. Unknown models cost 0 and are flagged in the report so a missing
price never silently reads as "free".
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPrice:
    input_per_1m: float
    output_per_1m: float
    cached_per_1m: float | None = None

    def cost(
        self, prompt_tokens: int, completion_tokens: int, cached_tokens: int = 0, cache_write_tokens: int = 0
    ) -> float:
        cached_rate = self.cached_per_1m if self.cached_per_1m is not None else self.input_per_1m
        fresh_input = max(prompt_tokens - cached_tokens - cache_write_tokens, 0)
        return (
            fresh_input * self.input_per_1m
            + cached_tokens * cached_rate
            + cache_write_tokens * self.input_per_1m * CACHE_WRITE_MULTIPLIER
            + completion_tokens * self.output_per_1m
        ) / 1_000_000.0


CACHE_WRITE_MULTIPLIER = 1.25

# Claude first-party API pricing per 1M tokens (2026-06). Cache reads bill at 10% of the input
# rate. Override in the config's `pricing:` block if your account's rates differ.
DEFAULT_PRICING: dict[str, ModelPrice] = {
    "claude-haiku-4-5": ModelPrice(input_per_1m=1.00, output_per_1m=5.00, cached_per_1m=0.10),
    "claude-sonnet-5": ModelPrice(input_per_1m=2.00, output_per_1m=10.00, cached_per_1m=0.20),
    "claude-opus-5": ModelPrice(input_per_1m=5.00, output_per_1m=25.00, cached_per_1m=0.50),
}


class PricingBook:
    def __init__(self, overrides: dict[str, dict] | None = None):
        self._book: dict[str, ModelPrice] = dict(DEFAULT_PRICING)
        self._overridden: set[str] = set(overrides or {})
        for model, vals in (overrides or {}).items():
            self._book[model] = ModelPrice(
                input_per_1m=float(vals["input_per_1m"]),
                output_per_1m=float(vals["output_per_1m"]),
                cached_per_1m=(float(vals["cached_per_1m"]) if vals.get("cached_per_1m") is not None else None),
            )

    def has(self, model: str) -> bool:
        return model in self._book

    def is_default(self, model: str) -> bool:
        """True when the model is priced only from the built-in placeholder table (not the
        config's ``pricing:`` block), so its cost figures are unvetted and worth flagging."""
        return model in self._book and model not in self._overridden

    def cost(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cached_tokens: int = 0,
        cache_write_tokens: int = 0,
    ) -> float:
        price = self._book.get(model)
        if price is None:
            return 0.0
        return price.cost(prompt_tokens, completion_tokens, cached_tokens, cache_write_tokens)
