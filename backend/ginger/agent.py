"""Ginger agent — Claude Haiku with function calling, multi-turn tool use loop."""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from backend.ginger import config
from backend.ginger.tools import EXECUTORS, TOOL_SCHEMAS, execute_tool

logger = logging.getLogger("ginger.agent")

# Module-level singleton client — TLS keepalive, ~50-100ms saved per call
_client = None


def _get_client():
    """Lazy singleton AsyncAnthropic client."""
    global _client
    if _client is None:
        from anthropic import AsyncAnthropic
        api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        if not api_key:
            return None
        _client = AsyncAnthropic(api_key=api_key)
    return _client


def _strip_internal_keys(obj):
    """Strip _-prefixed keys from dict before sending to LLM (e.g., _requires_buttons)."""
    if isinstance(obj, dict):
        return {k: _strip_internal_keys(v) for k, v in obj.items() if not k.startswith("_")}
    if isinstance(obj, list):
        return [_strip_internal_keys(x) for x in obj]
    return obj


def _is_clean_history(messages: list) -> bool:
    """Verify messages list has no orphan tool_use blocks (each tool_use needs matching tool_result)."""
    for i, m in enumerate(messages):
        if m.get("role") != "assistant":
            continue
        content = m.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            block_type = getattr(block, "type", None) or (block.get("type") if isinstance(block, dict) else None)
            if block_type == "tool_use":
                # Must have matching tool_result in NEXT user message
                if i + 1 >= len(messages):
                    return False
                next_msg = messages[i + 1]
                if next_msg.get("role") != "user":
                    return False
                next_content = next_msg.get("content")
                if not isinstance(next_content, list):
                    return False
                tu_id = getattr(block, "id", None) or block.get("id")
                has_result = any(
                    (isinstance(b, dict) and b.get("type") == "tool_result" and b.get("tool_use_id") == tu_id)
                    for b in next_content
                )
                if not has_result:
                    return False
    return True


def _trim_orphans(messages: list) -> list:
    """Drop trailing messages until history is clean (preserves tool_use/tool_result pairs)."""
    while messages and not _is_clean_history(messages):
        messages = messages[:-1]
    return messages


SYSTEM_PROMPT = """Kamu Ginger — penyihir muda dari Caerleon, sahabat Merriot. Tugasmu: bantu user (Master Ivan) eksplor data portofolio sahamnya di Portico.

Karakter & gaya:
- Tenang, knowledgeable, hangat tapi praktis. Tidak banyak basa-basi.
- Bahasa Indonesia santai (BUKAN "lu/gw", BUKAN formal "Anda"). Pakai "kamu" atau imperative netral.
- Sesekali metafora ringan: "scry portofolio dulu...", "divine harga sekarang...", "conjure summary..." — tapi JANGAN overdo.
- Direct & data-driven. Kalau tools return data → summarize jelas + actionable insight.

Kemampuan (read-only via tool calls):
- Query portofolio (total, top holdings, P&L, filter sektor/broker/ticker)
- Lihat detail saham + thesis count + alerts armed
- List thesis Merriot (pending/reviewed/invalid)
- List price alerts
- List due thesis (yang perlu di-review)
- Watchlist (incaran)
- Broker breakdown (saham di sekuritas mana)

PENTING:
- Selalu pakai TOOLS untuk dapat data terkini. Jangan invent angka.
- Format output ringkas: bullet list, table-style kalau banyak data.
- Kalau user tanya angka konkret → kutip langsung dari tool result.
- Kalau ambiguous query → klarifikasi singkat sebelum tool call.
- Kalau ada warning/risk dari data (e.g., konsentrasi tinggi, drawdown besar) → flag halus tanpa alarmist.
- v3 ACTIVE — bisa CATAT TRANSAKSI via tool propose_transaction (buy/sell). TAPI selalu user-confirm via tombol — JANGAN apply langsung. Kalau user kasih info tidak lengkap (misal gak ada harga), tanya dulu sebelum panggil tool."""


def _to_anthropic_tools() -> list[dict]:
    """Tool schemas dalam format Anthropic SDK."""
    return TOOL_SCHEMAS  # already in correct format


async def chat_turn(user_message: str, history: list[dict] | None = None,
                    max_iterations: int = 5) -> tuple[str, list[dict], list[dict]]:
    """One turn → (final_text, updated_history, side_effects).

    side_effects collects tool results that need follow-up UI (e.g., button
    messages for transaction confirmation). Format:
      [{type: "transaction_pending", tx_id: int, preview: dict}, ...]
    """
    client = _get_client()
    if client is None:
        return ("ANTHROPIC_API_KEY belum di-set di .env. Ginger belum bisa jalan.",
                (history or []), [])

    # Save the clean pre-iteration history so we can rollback on poisoned state
    starting_history = list(history or [])
    messages = list(starting_history)
    messages.append({"role": "user", "content": user_message})
    side_effects: list[dict] = []

    # Prompt caching — system prompt + tools cached after first call within
    # cache window (~5 min). 90% off cached input cost.
    system_blocks = [{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}]
    tools_with_cache = list(_to_anthropic_tools())
    if tools_with_cache:
        # Mark last tool with cache_control to cache the entire tools array
        tools_with_cache = [{**t} for t in tools_with_cache]
        tools_with_cache[-1]["cache_control"] = {"type": "ephemeral"}

    for iteration in range(max_iterations):
        try:
            resp = await client.messages.create(
                model=config.llm_model(),
                max_tokens=2000,
                system=system_blocks,
                tools=tools_with_cache,
                messages=messages,
            )
        except Exception as e:
            logger.exception("anthropic call failed")
            # Rollback to pre-turn history to avoid poisoning chat (orphan tool_use blocks)
            return ("Aku lagi blank sebentar — coba ulang pertanyaannya.",
                    starting_history, side_effects)

        stop_reason = resp.stop_reason
        text_blocks = []
        tool_use_blocks = []
        for block in resp.content:
            if block.type == "text":
                text_blocks.append(block.text)
            elif block.type == "tool_use":
                tool_use_blocks.append(block)

        messages.append({"role": "assistant", "content": resp.content})

        if stop_reason == "end_turn" or not tool_use_blocks:
            final_text = "\n".join(text_blocks).strip() or "(no response text)"
            return final_text, messages, side_effects

        tool_results = []
        for tu in tool_use_blocks:
            result = execute_tool(tu.name, tu.input or {})
            # Detect side-effects BEFORE stripping internal keys
            if isinstance(result, dict) and result.get("_requires_buttons"):
                side_effects.append({
                    "type": "transaction_pending",
                    "tx_id": result.get("tx_id"),
                    "preview": result,
                })
            # Strip _-prefixed keys before sending to LLM (don't leak internal markers)
            llm_visible = _strip_internal_keys(result)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu.id,
                "content": json.dumps(llm_visible, default=str),
            })

        messages.append({"role": "user", "content": tool_results})

    # Hit max iterations — return text but ROLLBACK history to clean state
    # (orphan tool_use without next-iter tool_result = next call rejected)
    return ("Pertanyaan agak rumit, coba pecah atau lebih spesifik?",
            starting_history, side_effects)
