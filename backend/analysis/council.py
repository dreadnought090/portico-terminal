"""Council — parallel 4-agent thesis stress-test + synthesizer."""
import os
import json
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

import anthropic

from backend.analysis.prompts import (
    COUNCIL_ROLES,
    SYNTHESIZER_PROMPT,
    PROMPT_VERSION,
    format_synthesizer_input,
)

logger = logging.getLogger("mybloomberg.council")

ANTHROPIC_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
SYNTHESIZER_MODEL = os.environ.get("COUNCIL_SYNTHESIZER_MODEL", "claude-opus-4-7")
COUNCIL_MAX_TOKENS = int(os.environ.get("COUNCIL_MAX_TOKENS", "2000"))

# Rough cost estimate per 1M tokens (USD). Update when pricing changes.
MODEL_COSTS = {
    "claude-opus-4-7": {"input": 15.0, "output": 75.0},
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5-20251001": {"input": 0.8, "output": 4.0},
}


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Rough USD cost for a call."""
    cost = MODEL_COSTS.get(model, {"input": 3.0, "output": 15.0})
    return (input_tokens / 1_000_000 * cost["input"]) + (output_tokens / 1_000_000 * cost["output"])


async def _call_role(client: anthropic.AsyncAnthropic, role_key: str, role_config: dict, thesis: str) -> dict:
    """Execute one analyst role asynchronously."""
    start = datetime.now(timezone.utc)
    try:
        message = await client.messages.create(
            model=role_config["model"],
            max_tokens=COUNCIL_MAX_TOKENS,
            system=role_config["system"],
            messages=[{"role": "user", "content": f"Thesis to analyze:\n\n{thesis}"}],
        )
        output_text = message.content[0].text if message.content else ""
        usage = message.usage
        cost = _estimate_cost(role_config["model"], usage.input_tokens, usage.output_tokens)
        duration_ms = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)

        return {
            "role": role_key,
            "label": role_config["label"],
            "model": role_config["model"],
            "output": output_text,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "cost_usd": cost,
            "duration_ms": duration_ms,
            "error": None,
        }
    except Exception as e:
        logger.exception("Council role %s failed", role_key)
        return {
            "role": role_key,
            "label": role_config["label"],
            "model": role_config["model"],
            "output": "",
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_usd": 0.0,
            "duration_ms": int((datetime.now(timezone.utc) - start).total_seconds() * 1000),
            "error": str(e),
        }


async def _synthesize(client: anthropic.AsyncAnthropic, thesis: str, panel_outputs: dict) -> dict:
    """Combine 4 analyst outputs into CIO-style recommendation."""
    start = datetime.now(timezone.utc)
    synth_input = format_synthesizer_input(thesis, panel_outputs)
    try:
        message = await client.messages.create(
            model=SYNTHESIZER_MODEL,
            max_tokens=3000,
            messages=[{"role": "user", "content": synth_input}],
        )
        output_text = message.content[0].text if message.content else ""
        usage = message.usage
        cost = _estimate_cost(SYNTHESIZER_MODEL, usage.input_tokens, usage.output_tokens)
        duration_ms = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)

        return {
            "output": output_text,
            "model": SYNTHESIZER_MODEL,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "cost_usd": cost,
            "duration_ms": duration_ms,
            "error": None,
        }
    except Exception as e:
        logger.exception("Synthesizer failed")
        return {
            "output": "",
            "model": SYNTHESIZER_MODEL,
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_usd": 0.0,
            "duration_ms": int((datetime.now(timezone.utc) - start).total_seconds() * 1000),
            "error": str(e),
        }


async def run_council(ticker: str, thesis: str, roles_enabled: Optional[list] = None) -> dict:
    """
    Run full 4-agent council + synthesizer.

    Args:
        ticker: stock ticker (e.g., "BBCA")
        thesis: user's thesis text (markdown)
        roles_enabled: optional subset of roles (default: all 4)

    Returns:
        dict with panel outputs, synthesis, and metadata
    """
    if not ANTHROPIC_API_KEY:
        return {
            "error": "API key belum diset. Isi OPENROUTER_API_KEY di .env dengan Anthropic API key.",
            "ticker": ticker,
            "panel": {},
            "synthesis": None,
        }

    if not thesis or not thesis.strip():
        return {
            "error": "Thesis kosong. Tulis thesis dulu sebelum run council.",
            "ticker": ticker,
            "panel": {},
            "synthesis": None,
        }

    roles_to_run = roles_enabled or list(COUNCIL_ROLES.keys())
    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

    start = datetime.now(timezone.utc)

    # Step 1 — parallel panel calls
    panel_tasks = [
        _call_role(client, role_key, COUNCIL_ROLES[role_key], thesis)
        for role_key in roles_to_run
        if role_key in COUNCIL_ROLES
    ]
    panel_results = await asyncio.gather(*panel_tasks)

    panel_outputs = {r["role"]: r["output"] for r in panel_results}
    panel_errors = [r for r in panel_results if r["error"]]

    # Step 2 — synthesizer (only if at least 2 panel outputs succeeded)
    successful_panel = [r for r in panel_results if not r["error"]]
    if len(successful_panel) < 2:
        return {
            "ticker": ticker,
            "thesis": thesis,
            "panel": {r["role"]: r for r in panel_results},
            "synthesis": None,
            "error": f"Terlalu banyak panel calls gagal ({len(panel_errors)}/{len(panel_results)}). Synthesizer di-skip.",
            "total_duration_ms": int((datetime.now(timezone.utc) - start).total_seconds() * 1000),
            "total_cost_usd": sum(r["cost_usd"] for r in panel_results),
            "prompt_version": PROMPT_VERSION,
        }

    synthesis_result = await _synthesize(client, thesis, panel_outputs)

    total_duration = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)
    total_cost = sum(r["cost_usd"] for r in panel_results) + synthesis_result["cost_usd"]
    total_input_tokens = sum(r["input_tokens"] for r in panel_results) + synthesis_result["input_tokens"]
    total_output_tokens = sum(r["output_tokens"] for r in panel_results) + synthesis_result["output_tokens"]

    return {
        "ticker": ticker,
        "thesis": thesis,
        "panel": {r["role"]: r for r in panel_results},
        "synthesis": synthesis_result,
        "error": None,
        "total_duration_ms": total_duration,
        "total_cost_usd": total_cost,
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "prompt_version": PROMPT_VERSION,
    }


def estimate_council_cost(thesis_length_chars: int = 2000) -> dict:
    """Rough cost estimate shown to user BEFORE running council."""
    # Rule of thumb: 1 token ≈ 4 chars
    input_tokens_per_role = thesis_length_chars // 4 + 500  # +system prompt
    output_tokens_per_role = 1000  # conservative avg

    panel_cost = 0.0
    for role_key, role_config in COUNCIL_ROLES.items():
        panel_cost += _estimate_cost(role_config["model"], input_tokens_per_role, output_tokens_per_role)

    # Synthesizer: 4x input (combines panels)
    synth_input = input_tokens_per_role * 4
    synth_output = 2000
    synth_cost = _estimate_cost(SYNTHESIZER_MODEL, synth_input, synth_output)

    total = panel_cost + synth_cost
    return {
        "panel_cost_usd": round(panel_cost, 4),
        "synthesizer_cost_usd": round(synth_cost, 4),
        "total_cost_usd": round(total, 4),
        "estimate_note": "Rough estimate. Actual cost may vary ±30%.",
    }
