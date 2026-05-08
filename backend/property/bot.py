from __future__ import annotations
import asyncio
import html as html_mod
import logging
import httpx
from datetime import datetime
from backend.property.config import (
    TELEGRAM_API, TELEGRAM_BOT_TOKEN, PROPERTIES, MONTH_COLUMNS,
    CATEGORY_ROWS, get_authorized_users,
)
from backend.property.sheets import (
    SheetsClient, current_year, list_available_years,
)
from backend.property.ai_parser import parse_intent
from backend.property import reminders as property_reminders
import json
from pathlib import Path

logger = logging.getLogger("property.bot")

QA_LOG_PATH = Path(__file__).parent / "data" / "qa_log.jsonl"


def _log_qa(chat_id: int, field: str, question: str, answer: str) -> None:
    """Append a Q&A pair to the audit log (JSONL)."""
    try:
        QA_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(QA_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": datetime.now().isoformat(timespec="seconds"),
                "chat_id": chat_id,
                "field": field,
                "question": question,
                "answer": answer,
            }, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error(f"QA log write failed: {e}")

sheets: SheetsClient = None
http: httpx.AsyncClient = None
last_update_id: int = 0

user_states: dict[int, dict] = {}

ALL_MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEPT", "OCT", "NOV", "DEC"]

BROKER_FEE_PCT = 10  # auto-deduct broker fee on rental income


def months_from(start_month: str, count: int) -> list[str]:
    idx = ALL_MONTHS.index(start_month)
    return [ALL_MONTHS[(idx + i) % 12] for i in range(count)]


def current_month() -> str:
    m = datetime.now().month
    return ALL_MONTHS[m - 1]


def _add_months(d, months: int):
    """Add `months` to date `d` without depending on dateutil."""
    from datetime import date as _date
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    # Clamp day for short months (Feb 30 → Feb 28/29).
    import calendar
    day = min(d.day, calendar.monthrange(year, month)[1])
    return _date(year, month, day)


def split_lease_by_year(start_month: str, start_year: int, duration: int) -> list[tuple[int, str]]:
    """Walk `duration` months starting at (start_year, start_month). Returns
    list of (year, month) pairs in order. Raises ValueError on invalid input."""
    if start_month not in ALL_MONTHS:
        raise ValueError(f"invalid start_month: {start_month!r}")
    if not (1 <= duration <= 60):
        raise ValueError(f"duration must be 1-60 months, got {duration}")
    if not (2000 <= start_year <= 2100):
        raise ValueError(f"start_year out of range: {start_year}")
    start_idx = ALL_MONTHS.index(start_month)
    return [
        (start_year + (start_idx + i) // 12, ALL_MONTHS[(start_idx + i) % 12])
        for i in range(duration)
    ]


def _safe_year(value, fallback: int) -> int:
    """Coerce parser output to a sane year. Returns `fallback` if invalid."""
    try:
        y = int(value) if value is not None else None
    except (TypeError, ValueError):
        return fallback
    if y is None or not (2000 <= y <= 2100):
        return fallback
    return y


def is_authorized(chat_id: int) -> bool:
    return chat_id in get_authorized_users()



async def send_message(chat_id: int, text: str, reply_markup: dict = None) -> bool:
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        await http.post(f"{TELEGRAM_API}/sendMessage", json=payload)
        return True
    except Exception as e:
        logger.error(f"send_message to {chat_id} failed: {e}")
        return False


async def send_document(chat_id: int, file_path, caption: str = ""):
    with open(file_path, "rb") as f:
        await http.post(
            f"{TELEGRAM_API}/sendDocument",
            data={"chat_id": chat_id, "caption": caption},
            files={"document": (file_path.name, f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )


def fire_typing(chat_id: int):
    async def _do():
        try:
            await http.post(
                f"{TELEGRAM_API}/sendChatAction",
                json={"chat_id": chat_id, "action": "typing"})
        except Exception:
            pass
    asyncio.create_task(_do())


def property_buttons() -> dict:
    buttons = []
    for key, info in PROPERTIES.items():
        buttons.append({"text": info["name"], "callback_data": f"prop:{key}"})
    return {"inline_keyboard": [buttons[i:i+2] for i in range(0, len(buttons), 2)]}


def month_buttons() -> dict:
    buttons = [{"text": m, "callback_data": f"month:{m}"} for m in ALL_MONTHS]
    return {"inline_keyboard": [buttons[i:i+4] for i in range(0, 12, 4)]}


def type_buttons() -> dict:
    return {"inline_keyboard": [
        [{"text": "\U0001f4b0 Sewa", "callback_data": "type:income"},
         {"text": "\U0001f4c9 Pengeluaran", "callback_data": "type:expense"}],
    ]}


async def handle_start(chat_id: int):
    user_states.pop(chat_id, None)
    text = (
        "\U0001F3E0 <b>Property Manager Bot</b>\n\n"
        "Ketik pesan biasa atau pakai tombol:\n\n"
        "Contoh input:\n"
        "• <code>sewa yale 0111 april 2.5jt</code>\n"
        "• <code>service charge amega april 900rb</code>\n"
        "• <code>unit 0728 renovasi 4.5jt</code>\n"
        "• <code>sewa yale 0728 april 26jt setahun</code>\n"
        "• <code>summary april</code>\n"
    )
    buttons = {"inline_keyboard": [
        [{"text": "\U0001f4ca Input Data", "callback_data": "menu:input"},
         {"text": "\U0001f4cb Lihat Data", "callback_data": "menu:view"}],
        [{"text": "⏰ Reminders", "callback_data": "menu:reminders"},
         {"text": "\U0001f4b0 Finance", "callback_data": "menu:finance"}],
        [{"text": "\U0001f4c2 Download XLSX", "callback_data": "menu:file"}],
    ]}
    await send_message(chat_id, text, buttons)


async def handle_text(chat_id: int, text: str):
    fire_typing(chat_id)
    try:
        intent = await parse_intent(text)
    except Exception as e:
        logger.error(f"Parser error: {e}")
        await send_message(chat_id, "❌ Gak bisa proses pesan. Coba lagi.")
        return

    action = intent.get("intent", "unknown")

    handlers = {
        "add_income": handle_add_income,
        "add_expense": handle_add_expense,
        "bulk_expense": handle_bulk_expense,
        "query": handle_query,
        "set_reminder": handle_set_reminder,
        "set_bill_reminder": handle_set_reminder,
        "repeat_last": handle_repeat_last,
        "auto_fill_lease": handle_auto_fill_lease,
        "auto_fill_acquisition": handle_auto_fill_acquisition,
    }

    handler = handlers.get(action)
    if handler:
        await handler(chat_id, intent)
    elif action == "clarify":
        await send_message(chat_id, "\U0001f914 " + html_mod.escape(
            intent.get("notes", "Bisa ulang dengan lebih spesifik?")))
    else:
        await send_message(chat_id,
            "❓ Gak ngerti. Coba:\n"
            "• <code>sewa yale 0111 april 2.5jt</code>\n"
            "• <code>summary</code>")



async def handle_add_income(chat_id: int, intent: dict):
    prop_key = intent.get("property", "")
    month = intent.get("month", "")
    amount = intent.get("amount", 0)
    duration_months = intent.get("duration_months")

    if not prop_key or prop_key not in PROPERTIES:
        await send_message(chat_id,
            f"❌ Property '{html_mod.escape(str(prop_key))}' gak dikenal.")
        return

    if not month:
        if duration_months and duration_months > 1:
            month = current_month()
            intent["month"] = month
        else:
            await send_message(chat_id,
                "❌ Bulan gak jelas. Coba: 'sewa yale 0111 <b>april</b> 2.5jt'")
            return

    if month not in MONTH_COLUMNS:
        await send_message(chat_id, f"❌ Bulan '{html_mod.escape(month)}' gak valid.")
        return

    if amount <= 0 or amount > 1_000_000_000:
        await send_message(chat_id, "❌ Amount gak valid (harus 1 - 1 Milyar).")
        return

    if duration_months is not None and not (1 <= duration_months <= 60):
        await send_message(chat_id,
            f"❌ Durasi {duration_months} bulan gak valid (harus 1-60).")
        return

    # Refuse if a prior income follow-up is still pending — overwriting it would
    # silently drop the earlier income.
    existing = user_states.get(chat_id)
    if existing and existing.get("flow") == "income_followup":
        await send_message(chat_id,
            "⚠️ Masih ada input sewa yang menunggu jawaban. Selesaikan dulu, "
            "atau ketik /start untuk reset.")
        return

    pending = []
    if intent.get("entry_day") in (None, ""):
        pending.append("entry_day")
    if intent.get("broker_pct") is None:
        pending.append("broker_pct")

    if pending:
        user_states[chat_id] = {
            "flow": "income_followup",
            "intent": intent,
            "pending": pending,
            "processing": False,
            "ts": datetime.now().timestamp(),
        }
        await _ask_next_income_followup(chat_id)
        return

    await _finalize_income(chat_id, intent)


def _income_followup_question(field: str) -> tuple[str, dict]:
    if field == "entry_day":
        text = "📅 Tanggal masuk sewa berapa? (1-31)\n<i>Atau ketik angka langsung, atau Skip.</i>"
        kb = {"inline_keyboard": [[{"text": "Skip", "callback_data": "incfu:entry_day:skip"}]]}
    else:  # broker_pct
        text = "💼 Broker fee berapa %?\n<i>Default 10%. Pilih atau ketik angka.</i>"
        kb = {"inline_keyboard": [[
            {"text": "0%", "callback_data": "incfu:broker_pct:0"},
            {"text": "5%", "callback_data": "incfu:broker_pct:5"},
            {"text": "10%", "callback_data": "incfu:broker_pct:10"},
            {"text": "15%", "callback_data": "incfu:broker_pct:15"},
            {"text": "Skip", "callback_data": "incfu:broker_pct:skip"},
        ]]}
    return text, kb


async def _ask_next_income_followup(chat_id: int):
    state = user_states.get(chat_id)
    if not state or not state.get("pending"):
        return
    field = state["pending"][0]
    text, kb = _income_followup_question(field)
    await send_message(chat_id, text, kb)


async def _apply_income_followup_answer(chat_id: int, field: str, raw: str) -> bool:
    """Validate & store answer. Returns True if accepted, False if invalid."""
    state = user_states.get(chat_id)
    if not state:
        return False

    # Keep session alive on every interaction, including validation failures.
    state["ts"] = datetime.now().timestamp()
    question_text, _ = _income_followup_question(field)

    if raw.lower() == "skip":
        state["intent"][field] = None if field == "broker_pct" else ""
        _log_qa(chat_id, field, question_text, "skip")
    elif field == "entry_day":
        try:
            day = int(raw.strip())
        except ValueError:
            await send_message(chat_id, "❌ Tanggal harus angka 1-31. Coba lagi atau Skip.")
            return False
        if not 1 <= day <= 31:
            await send_message(chat_id, "❌ Tanggal harus 1-31.")
            return False
        state["intent"]["entry_day"] = day
        _log_qa(chat_id, field, question_text, str(day))
    else:  # broker_pct
        try:
            pct = float(raw.strip().rstrip("%"))
        except ValueError:
            await send_message(chat_id, "❌ Persentase harus angka 0-50. Coba lagi atau Skip.")
            return False
        if not 0 <= pct <= 50:
            await send_message(chat_id, "❌ Persentase harus 0-50.")
            return False
        state["intent"]["broker_pct"] = pct
        _log_qa(chat_id, field, question_text, f"{pct}%")

    state["pending"].pop(0)
    return True


async def _advance_income_followup(chat_id: int) -> None:
    """After a successful answer: ask next pending question, or finalize."""
    state = user_states.get(chat_id)
    if not state:
        return
    if state.get("pending"):
        await _ask_next_income_followup(chat_id)
        return

    # Keep state in place with processing=True so concurrent text/callback
    # input gets dropped (handle_income_followup_text & incfu callback both
    # check processing) instead of being re-parsed as a new intent. Pop after
    # finalize completes.
    state["processing"] = True
    intent = state["intent"]
    try:
        await _finalize_income(chat_id, intent)
    finally:
        user_states.pop(chat_id, None)


async def handle_income_followup_text(chat_id: int, text: str) -> bool:
    """Returns True if message was consumed by followup flow."""
    state = user_states.get(chat_id)
    if not state or state.get("flow") != "income_followup" or not state.get("pending"):
        return False
    if state.get("processing"):
        return True  # ignore concurrent input while finalize is running

    field = state["pending"][0]
    if not await _apply_income_followup_answer(chat_id, field, text):
        return True

    await _advance_income_followup(chat_id)
    return True


async def _finalize_income(chat_id: int, intent: dict):
    prop_key = intent["property"]
    month = intent["month"]
    amount = intent["amount"]
    notes = intent.get("notes", "") or ""
    duration_months = intent.get("duration_months")
    tenant_name = intent.get("tenant_name")
    lease_start = intent.get("lease_start")
    lease_end = intent.get("lease_end")
    entry_day = intent.get("entry_day")
    broker_pct = intent.get("broker_pct")
    if broker_pct is None:
        broker_pct = BROKER_FEE_PCT
    start_year = _safe_year(intent.get("start_year"), current_year())

    annotations = []
    if entry_day:
        annotations.append(f"masuk tgl {entry_day}")
    if intent.get("broker_pct") is not None:
        annotations.append(f"broker {broker_pct}%")
    cell_note = " | ".join([notes] + annotations).strip(" |") if (notes or annotations) else ""

    sheet_name = PROPERTIES[prop_key]["sheet"]
    prop_name = PROPERTIES[prop_key]["name"]

    try:
        if duration_months and duration_months > 1:
            monthly = round(amount / duration_months)
            # Single rounding: avoid display vs written-cell drift.
            broker_monthly = round(amount * broker_pct / 100 / duration_months) if broker_pct > 0 else 0
            broker_total = broker_monthly * duration_months

            try:
                year_month_pairs = split_lease_by_year(month, start_year, duration_months)
            except ValueError as ve:
                await send_message(chat_id, f"❌ Input gak valid: {ve}")
                return
            by_year: dict[int, list[str]] = {}
            for y, m in year_month_pairs:
                by_year.setdefault(y, []).append(m)

            for y, months_list in by_year.items():
                await asyncio.to_thread(
                    sheets.write_income_batch, sheet_name, months_list, monthly,
                    cell_note, y)
                if broker_monthly > 0:
                    await asyncio.to_thread(
                        sheets.write_expense_batch, sheet_name, months_list,
                        broker_monthly, "AGENT FEES / COMMISSIONS", y)

            year_summary = " | ".join(
                f"{y}: {', '.join(ms)}" for y, ms in sorted(by_year.items())
            )
            msg = (
                f"✅ Sewa {prop_name} per tahun: Rp {amount:,} ÷ {duration_months} bln = Rp {monthly:,}/bln\n"
                f"Broker fee ({broker_pct}%): Rp {broker_total:,} = Rp {broker_monthly:,}/bln\n"
                f"📂 Tercatat di file: {year_summary}"
            )
        else:
            await asyncio.to_thread(
                sheets.write_income, sheet_name, month, amount, cell_note, start_year)
            broker_fee = round(amount * broker_pct / 100)
            if broker_fee > 0:
                await asyncio.to_thread(
                    sheets.write_expense, sheet_name, month,
                    "AGENT FEES / COMMISSIONS", broker_fee, "", start_year)
            msg = (
                f"✅ Sewa {prop_name} {month} {start_year}: Rp {amount:,} tercatat\n"
                f"Broker fee ({broker_pct}%): Rp {broker_fee:,}"
            )

        if entry_day:
            msg += f"\n📅 Masuk tgl {entry_day}"

        if tenant_name and (lease_start or lease_end or duration_months):
            from backend.property.models import Tenant
            from datetime import date as _date
            try:
                start_date = _date.fromisoformat(lease_start) if lease_start else None
                end_date = _date.fromisoformat(lease_end) if lease_end else None
            except ValueError:
                start_date = end_date = None

            # If only start given but duration known, derive end. Skip tenant
            # insertion if we'd produce a nonsensical "ended today" record.
            if start_date and not end_date and duration_months:
                end_date = _add_months(start_date, duration_months)
            if start_date and end_date:
                tenant = Tenant(
                    property_key=prop_key,
                    name=tenant_name,
                    monthly_rent=round(amount / duration_months) if duration_months else amount,
                    contract_start=start_date,
                    contract_end=end_date,
                    phone="", id_ktp="", deposit=0,
                )
                await asyncio.to_thread(sheets.add_tenant, tenant, start_year)
                msg += f"\n\n📋 Tenant: {html_mod.escape(tenant_name)}"
                msg += f" | Masuk: {start_date} → Keluar: {end_date}"

        await send_message(chat_id, msg)
    except Exception as e:
        logger.error(f"Write income failed: {e}")
        await send_message(chat_id, "❌ Gagal tulis data. Cek log server.")


async def handle_add_expense(chat_id: int, intent: dict):
    prop_key = intent.get("property", "")
    month = intent.get("month", "")
    category = intent.get("category", "")
    amount = intent.get("amount", 0)

    if not prop_key or prop_key not in PROPERTIES:
        await send_message(chat_id,
            f"❌ Property '{html_mod.escape(str(prop_key))}' gak dikenal.")
        return
    if not month or month not in MONTH_COLUMNS:
        await send_message(chat_id,
            "❌ Bulan gak jelas. Contoh: 'service charge amega <b>april</b> 900rb'")
        return
    if not category or category not in CATEGORY_ROWS:
        await send_message(chat_id,
            f"❌ Kategori '{html_mod.escape(str(category))}' gak dikenal.")
        return
    if amount <= 0 or amount > 1_000_000_000:
        await send_message(chat_id, "❌ Amount gak valid.")
        return

    try:
        sheet_name = PROPERTIES[prop_key]["sheet"]
        await asyncio.to_thread(
            sheets.write_expense, sheet_name, month, category, amount)
        await send_message(chat_id,
            f"✅ {category} {PROPERTIES[prop_key]['name']} {month}: Rp {amount:,} tercatat")
    except Exception as e:
        logger.error(f"Write expense failed: {e}")
        await send_message(chat_id, "❌ Gagal tulis data. Cek log server.")


async def handle_bulk_expense(chat_id: int, intent: dict):
    month = intent.get("month", "")
    category = intent.get("category", "")
    amount = intent.get("amount", 0)

    if not month or not category or amount <= 0:
        await send_message(chat_id, "❌ Format: 'bayar IPL semua unit april 1.2jt'")
        return

    success = []
    failed = []
    for prop_key, info in PROPERTIES.items():
        try:
            await asyncio.to_thread(
                sheets.write_expense, info["sheet"], month, category, amount)
            success.append(info["name"])
        except Exception as e:
            failed.append(f"{info['name']}: {e}")

    msg = f"✅ {category} {month} Rp {amount:,} tercatat untuk:\n"
    msg += "\n".join(f"  • {s}" for s in success)
    if failed:
        msg += "\n\n❌ Gagal:\n" + "\n".join(f"  • {f}" for f in failed)
    await send_message(chat_id, msg)


async def handle_query(chat_id: int, intent: dict):
    prop_key = intent.get("property", "")
    month = intent.get("month", "")

    if prop_key and prop_key in PROPERTIES:
        sheet_name = PROPERTIES[prop_key]["sheet"]
        target_month = month if month and month in MONTH_COLUMNS else current_month()
        try:
            data = await asyncio.to_thread(
                sheets.read_property_summary, sheet_name, target_month)
            name = html_mod.escape(PROPERTIES[prop_key]['name'])
            msg = f"\U0001f4ca <b>{name}</b> — {target_month}\n\n"
            msg += f"\U0001f4b0 Income: Rp {data['rental_income']:,}\n"
            msg += f"\U0001f4c9 Expenses: Rp {data['total_expenses']:,}\n"
            net = data['net']
            icon = "\U0001f7e2" if net >= 0 else "\U0001f534"
            msg += f"{icon} Net: Rp {net:,}\n"
            if data['expenses']:
                msg += "\nBreakdown pengeluaran:\n"
                for cat, val in sorted(data['expenses'].items(), key=lambda x: -x[1]):
                    msg += f"  • {html_mod.escape(cat)}: Rp {val:,}\n"
            await send_message(chat_id, msg)
        except Exception as e:
            logger.error(f"Query failed: {e}")
            await send_message(chat_id, "❌ Gagal baca data.")
    else:
        try:
            overview = await asyncio.to_thread(sheets.read_overview)
            msg = "\U0001f4ca <b>Portfolio Overview (YTD)</b>\n\n"
            msg += f"\U0001f4b0 Total Income: Rp {overview['ytd_rental_income']:,}\n"
            msg += f"\U0001f4c9 Total Expenses: Rp {overview['ytd_total_expenses']:,}\n"
            net = overview['ytd_net']
            icon = "\U0001f7e2" if net >= 0 else "\U0001f534"
            msg += f"{icon} Net: Rp {net:,}\n"
            await send_message(chat_id, msg)
        except Exception as e:
            logger.error(f"Overview failed: {e}")
            await send_message(chat_id, "❌ Gagal baca overview.")


async def handle_set_reminder(chat_id: int, intent: dict):
    from backend.property.models import Reminder
    prop_key = intent.get("property", "")
    rtype = intent.get("type", "sewa")
    desc = intent.get("description", "")
    due_day = intent.get("due_day", 1)
    amount = intent.get("amount", 0)

    if not prop_key:
        await send_message(chat_id, "❌ Property gak jelas.")
        return
    if prop_key not in PROPERTIES:
        await send_message(chat_id,
            f"❌ Property '{html_mod.escape(prop_key)}' gak dikenal.")
        return
    try:
        due_day = int(due_day)
    except (ValueError, TypeError):
        due_day = 0
    if not (1 <= due_day <= 31):
        await send_message(chat_id, "❌ Hari harus 1-31.")
        return

    reminder = Reminder(
        property_key=prop_key,
        type=rtype,
        description=desc or f"{rtype} {PROPERTIES.get(prop_key, {}).get('name', prop_key)}",
        due_day=due_day,
        amount=amount,
        active=True,
    )
    try:
        await asyncio.to_thread(sheets.add_reminder, reminder)
        await send_message(chat_id,
            f"⏰ Reminder di-set: tgl {due_day} setiap bulan")
    except Exception as e:
        logger.error(f"Reminder failed: {e}")
        await send_message(chat_id, "❌ Gagal set reminder.")


async def handle_repeat_last(chat_id: int, intent: dict):
    await send_message(chat_id,
        "\U0001f504 Fitur 'sama kayak bulan lalu' coming soon.")


async def handle_auto_fill_lease(chat_id: int, intent: dict):
    await send_message(chat_id,
        "\U0001f3d7️ Auto-fill lease coming soon.")


async def handle_auto_fill_acquisition(chat_id: int, intent: dict):
    await send_message(chat_id,
        "\U0001f3d7️ Auto-fill acquisition coming soon.")


async def handle_send_file(chat_id: int, year: int | None = None):
    """Send the Excel file for the given year (default: current year)."""
    from backend.property.sheets import excel_path_for
    target_year = year or current_year()
    path = excel_path_for(target_year)
    if not path.exists():
        available = list_available_years()
        if available:
            await send_message(chat_id,
                f"❌ File {target_year} belum ada. Tersedia: {', '.join(map(str, available))}")
        else:
            await send_message(chat_id, "❌ File XLSX gak ditemukan.")
        return
    try:
        fire_typing(chat_id)
        await send_document(chat_id, path,
            caption=f"\U0001f4c2 Property Manager {target_year} (updated)")
    except Exception as e:
        logger.error(f"Send file failed: {e}")
        await send_message(chat_id, "❌ Gagal kirim file.")


async def handle_callback(chat_id: int, callback_data: str, callback_id: str):
    # Answer callback immediately to stop spinner
    async def _answer():
        try:
            await http.post(
                f"{TELEGRAM_API}/answerCallbackQuery",
                json={"callback_query_id": callback_id})
        except Exception:
            pass
    asyncio.create_task(_answer())

    if ":" not in callback_data:
        return

    action, value = callback_data.split(":", 1)

    if action == "menu":
        if value == "input":
            await send_message(chat_id, "\U0001f4ca Pilih property:", property_buttons())
        elif value == "view":
            await handle_query(chat_id, {"property": "", "query_type": "summary", "month": ""})
        elif value == "reminders":
            try:
                reminders = await asyncio.to_thread(sheets.get_active_reminders)
                if not reminders:
                    await send_message(chat_id, "⏰ Belum ada reminder.")
                else:
                    msg = "⏰ <b>Active Reminders</b>\n\n"
                    for r in reminders:
                        prop = html_mod.escape(str(r.get('Property', '')))
                        desc = html_mod.escape(str(r.get('Description', '')))
                        day = r.get('Due Day', '?')
                        msg += f"• {prop} — {desc} (tgl {day})\n"
                    await send_message(chat_id, msg)
            except Exception as e:
                logger.error(f"Reminders list failed: {e}")
                await send_message(chat_id, "❌ Gagal baca reminders.")
        elif value == "finance":
            await send_message(chat_id,
                "\U0001f4b0 Finance commands:\n"
                "• <code>lease yale 0111, mulai apr, 25jt/thn, broker 10%</code>\n"
                "• <code>beli amega, harga 200jt, DP 50jt</code>")
        elif value == "file":
            await handle_send_file(chat_id)

    elif action == "incfu":
        # incfu:<field>:<value>
        if ":" not in value:
            return
        field, raw = value.split(":", 1)
        state = user_states.get(chat_id)
        if not state or state.get("flow") != "income_followup":
            return
        if state.get("processing"):
            return  # finalize in flight; drop spam-clicks
        if not state.get("pending") or state["pending"][0] != field:
            return
        if not await _apply_income_followup_answer(chat_id, field, raw):
            return
        await _advance_income_followup(chat_id)

    elif action == "prop":
        if value not in PROPERTIES:
            return
        existing = user_states.get(chat_id)
        if existing and existing.get("flow") == "income_followup":
            await send_message(chat_id,
                "⚠️ Selesaikan input sewa yang menunggu jawaban dulu, atau ketik /start.")
            return
        user_states[chat_id] = {"property": value, "ts": datetime.now().timestamp()}
        await send_message(chat_id,
            f"Property: {PROPERTIES[value]['name']}\nPilih tipe:", type_buttons())

    elif action == "type":
        state = user_states.get(chat_id, {})
        if "property" not in state:
            return
        state["type"] = value
        _touch_state(chat_id)
        await send_message(chat_id, "Pilih bulan:", month_buttons())

    elif action == "month":
        state = user_states.get(chat_id, {})
        if "property" not in state or "type" not in state:
            return
        state["month"] = value
        _touch_state(chat_id)
        prop_name = PROPERTIES.get(state.get("property", ""), {}).get("name", "?")
        tipe = "Sewa" if state.get("type") == "income" else "Pengeluaran"
        await send_message(chat_id,
            f"{tipe} {prop_name} {value}\n"
            f"Ketik jumlah (contoh: <code>2500000</code> atau <code>2.5jt</code>):")


def _parse_amount(text: str) -> int | None:
    """Parse amount from text like '2.5jt', '900rb', '2500000'."""
    t = text.lower().strip()
    try:
        if "jt" in t:
            num = t.replace("jt", "").replace(",", ".")
            return int(float(num) * 1_000_000)
        elif "rb" in t:
            num = t.replace("rb", "").replace(",", ".")
            return int(float(num) * 1_000)
        else:
            # Strip thousands separators: "1.500.000" -> "1500000"
            cleaned = t.replace(".", "").replace(",", "")
            return int(cleaned)
    except (ValueError, TypeError):
        return None


async def handle_form_amount(chat_id: int, text: str):
    state = user_states.get(chat_id)
    if not state or "month" not in state or "type" not in state:
        return False
    if state.get("flow") == "income_followup":
        # Don't consume guided-form input while a follow-up is pending.
        return False
    _touch_state(chat_id)

    amount = _parse_amount(text)
    if amount is None or amount <= 0 or amount > 1_000_000_000:
        await send_message(chat_id,
            "❌ Gak ngerti jumlah. Contoh: <code>2500000</code> atau <code>2.5jt</code>")
        return True

    prop_key = state["property"]
    month = state["month"]
    tipe = state["type"]
    sheet_name = PROPERTIES[prop_key]["sheet"]

    try:
        if tipe == "income":
            await asyncio.to_thread(sheets.write_income, sheet_name, month, amount)
            broker_fee = round(amount * BROKER_FEE_PCT / 100)
            await asyncio.to_thread(
                sheets.write_expense, sheet_name, month,
                "AGENT FEES / COMMISSIONS", broker_fee)
            await send_message(chat_id,
                f"✅ Sewa {PROPERTIES[prop_key]['name']} {month}: Rp {amount:,}\n"
                f"Broker fee ({BROKER_FEE_PCT}%): Rp {broker_fee:,}")
        else:
            await asyncio.to_thread(
                sheets.write_expense, sheet_name, month, "OTHER 1", amount)
            await send_message(chat_id,
                f"✅ Pengeluaran {PROPERTIES[prop_key]['name']} {month}: Rp {amount:,}")
    except Exception as e:
        logger.error(f"Form write failed: {e}")
        await send_message(chat_id, "❌ Gagal tulis data.")

    user_states.pop(chat_id, None)
    return True


def _cleanup_stale_states():
    """Remove user states older than 10 minutes. Notifies users if a follow-up
    flow expired so they don't wonder why their reply was re-parsed."""
    now = datetime.now().timestamp()
    stale = []
    for cid, s in user_states.items():
        if now - s.get("ts", 0) > 600:
            stale.append((cid, s.get("flow")))
    for cid, flow in stale:
        user_states.pop(cid, None)
        if flow == "income_followup":
            asyncio.create_task(send_message(
                cid,
                "⏱️ Sesi input sewa expired (10 menit). Mulai lagi kalau mau.",
            ))


def _touch_state(chat_id: int):
    """Update timestamp on active state to prevent premature cleanup."""
    if chat_id in user_states:
        user_states[chat_id]["ts"] = datetime.now().timestamp()


async def poll_updates():
    global last_update_id
    while True:
        try:
            params = {"offset": last_update_id + 1, "timeout": 30}
            resp = await http.get(f"{TELEGRAM_API}/getUpdates", params=params)
            if resp.status_code != 200:
                logger.warning(f"getUpdates HTTP {resp.status_code}")
                await asyncio.sleep(5)
                continue
            try:
                data = resp.json()
            except (ValueError, json.JSONDecodeError) as e:
                logger.warning(f"getUpdates non-JSON body: {e}")
                await asyncio.sleep(5)
                continue

            if not data.get("ok"):
                logger.warning(f"getUpdates not ok: {data.get('description')}")
                await asyncio.sleep(5)
                continue

            _cleanup_stale_states()

            for update in data.get("result", []):
                last_update_id = update["update_id"]
                try:
                    if "message" in update:
                        msg = update["message"]
                        chat_id = msg["chat"]["id"]
                        text = msg.get("text", "")

                        if not is_authorized(chat_id):
                            await send_message(chat_id,
                                "\U0001f6ab Unauthorized. Hubungi owner untuk akses.")
                            continue

                        if text == "/start":
                            await handle_start(chat_id)
                        elif text.startswith("/"):
                            await handle_command(chat_id, text)
                        elif await handle_income_followup_text(chat_id, text):
                            pass
                        elif await handle_form_amount(chat_id, text):
                            pass
                        else:
                            await handle_text(chat_id, text)

                    elif "callback_query" in update:
                        cb = update["callback_query"]
                        chat_id = cb["message"]["chat"]["id"]
                        if is_authorized(chat_id):
                            await handle_callback(chat_id, cb["data"], cb["id"])
                except Exception as e:
                    logger.error(f"Update handling error: {e}")

        except httpx.ReadTimeout:
            continue
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Poll error: {e}")
            await asyncio.sleep(5)


async def handle_command(chat_id: int, text: str):
    cmd = text.split()[0].lower()
    if cmd == "/summary":
        await handle_query(chat_id, {"property": "", "query_type": "summary", "month": ""})
    elif cmd == "/input":
        await send_message(chat_id, "\U0001f4ca Pilih property:", property_buttons())
    elif cmd == "/file":
        # Optional year arg: "/file 2027"
        parts = text.split()
        year = None
        if len(parts) > 1 and parts[1].isdigit():
            year = int(parts[1])
        await handle_send_file(chat_id, year)
    elif cmd == "/years":
        years = list_available_years()
        if years:
            await send_message(chat_id, f"📂 Tahun tersedia: {', '.join(map(str, years))}")
        else:
            await send_message(chat_id, "📂 Belum ada file year-data.")
    elif cmd == "/help":
        await handle_start(chat_id)
    else:
        await send_message(chat_id,
            "❓ Unknown command. Ketik /start untuk menu.")


_poll_task: asyncio.Task | None = None


def start_bot() -> None:
    """Launch property bot polling loop. No-op if PROPERTY_BOT_TOKEN missing.

    Reminder cron jobs are owned by Portico's global scheduler; see
    `backend.property.reminders.register_cron`.
    """
    global sheets, http, _poll_task

    if not TELEGRAM_BOT_TOKEN:
        logger.info("PROPERTY_BOT_TOKEN not set — property bot disabled")
        return
    if _poll_task is not None:
        return

    logger.info("Starting Property Manager Bot...")
    http = httpx.AsyncClient(timeout=40)
    sheets = SheetsClient()
    property_reminders.configure(sheets, http)
    _poll_task = asyncio.create_task(poll_updates(), name="property-bot-poll")
    logger.info("Property bot ready, polling for messages")


async def stop_bot() -> None:
    global _poll_task
    if _poll_task is not None:
        _poll_task.cancel()
        try:
            await _poll_task
        except (asyncio.CancelledError, Exception):
            pass
        _poll_task = None
    if http is not None:
        await http.aclose()
