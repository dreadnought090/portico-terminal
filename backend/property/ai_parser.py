from __future__ import annotations
import json
import anthropic
from backend.property.config import ANTHROPIC_API_KEY, PARSER_MODEL, PROPERTIES, EXPENSE_CATEGORIES

_client: anthropic.AsyncAnthropic | None = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY, base_url="https://api.anthropic.com")
    return _client

SYSTEM_PROMPT = f"""You are a property management assistant. Parse Indonesian/English mixed text into structured data.

Return ONLY valid JSON with these fields:
- intent: "add_income" | "add_expense" | "bulk_expense" | "set_reminder" | "set_bill_reminder" | "query" | "auto_fill_lease" | "auto_fill_acquisition" | "repeat_last" | "unknown"
- property: property key from this list: {list(PROPERTIES.keys())}
- month: 3-letter month code (JAN, FEB, MAR, APR, MAY, JUN, JUL, AUG, SEPT, OCT, NOV, DEC)
- category: expense category from this list: {list(EXPENSE_CATEGORIES.values())}
- amount: integer (convert "2.5jt" to 2500000, "900rb" to 900000, "1.2jt" to 1200000)
- notes: any extra info
- duration_months: integer, ONLY when input mentions "tahun" or yearly rent (e.g. "1 tahun" → 12, "2 tahun" → 24). Null otherwise.
- query_type: for queries only — "summary" | "comparison" | "roi" | "trend"
- description: for reminders only
- due_day: for reminders only (1-31)
- tenant_name: string, tenant name if mentioned (e.g. "sewa yale 0111 april 2.5jt pak budi" → "Pak Budi"). Null if not mentioned.
- lease_start: string YYYY-MM-DD, lease start date if mentioned (e.g. "masuk 1 mei 2026" → "2026-05-01"). Null if not mentioned.
- lease_end: string YYYY-MM-DD, lease end date if mentioned (e.g. "keluar 30 april 2027" → "2027-04-30"). Null if not mentioned.
- entry_day: integer 1-31, the day-of-month tenant moved in / rent received (e.g. "masuk tgl 4" → 4, "tanggal 15" → 15). Null if not mentioned.
- broker_pct: number 0-50, broker fee percentage if explicitly mentioned (e.g. "broker 10%" → 10, "tanpa broker" or "no broker" → 0, "broker 5 persen" → 5). Null if not mentioned (default applied later).
- start_year: 4-digit integer year if explicitly mentioned (e.g. "mei 2026" → 2026, "april 2027" → 2027). For leases crossing years like "mei 2026 - mei 2027", set start_year to the FIRST year (2026) and rely on duration_months for the span. Null if year not mentioned (current year applied later).

Property name matching:
- "yale 2516" or "2516" → yale_2516
- "yale 0111" or "0111" → yale_0111
- "yale 0727" or "0727" → yale_0727
- "yale 0728" or "0728" → yale_0728
- "amega" or "amega crown" or "a8-10" or "a810" → amega_a810

Month matching: "april" → APR, "mei" → MAY, "juni" → JUN, etc.

Amount matching:
- "2.5jt" or "2,5jt" or "2.500.000" → 2500000
- "900rb" or "900.000" → 900000
- "1.2jt" → 1200000
- "25jt" → 25000000

If "semua unit" or "all properties" → intent is "bulk_expense" or "bulk_income"
If "sama kayak bulan lalu" or "same as last month" → intent is "repeat_last"
If asking about data ("berapa", "gimana", "bandingkan") → intent is "query"

For lease auto-fill: extract annual_rent, broker_pct, months, bank_loan_monthly, start_month, tenant_name
For acquisition auto-fill: extract harga, bphtb, ajb, perbaikan, dp, cicilan, tenor, lender
"""


async def parse_intent(text: str) -> dict:
    try:
        response = await _get_client().messages.create(
            model=PARSER_MODEL,
            max_tokens=300,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": text}],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            # Strip ```json ... ``` fence
            raw = raw.split("```")[1].strip()
            if raw.startswith("json"):
                raw = raw[4:].strip()
        return json.loads(raw)
    except (json.JSONDecodeError, IndexError, anthropic.APIError) as e:
        return {"intent": "unknown", "notes": f"Parse error: {str(e)}"}
