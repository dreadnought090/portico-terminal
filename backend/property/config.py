from __future__ import annotations
import os

TELEGRAM_BOT_TOKEN = os.getenv("PROPERTY_BOT_TOKEN", "")
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
PARSER_MODEL = "claude-sonnet-4-6"
QA_MODEL = "claude-sonnet-4-6"

OWNER_CHAT_ID = int(os.getenv("PROPERTY_OWNER_CHAT_ID", "0"))

def get_authorized_users() -> dict[int, str]:
    users = {}
    if OWNER_CHAT_ID:
        users[OWNER_CHAT_ID] = "owner"
    return users

# ── Property Registry ─────────────────────────────────
PROPERTIES = {
    "yale_2516": {"name": "YALE 2516", "sheet": "YALE 2516"},
    "yale_0111": {"name": "YALE 0111", "sheet": "YALE 0111"},
    "yale_0727": {"name": "YALE 0727", "sheet": "YALE 0727"},
    "yale_0728": {"name": "YALE 0728", "sheet": "YALE 0728"},
    "amega_a810": {"name": "Amega Crown A8-10", "sheet": "Amega Crown A8-10"},
}

# ── Expense Categories ────────────────────────────────
EXPENSE_CATEGORIES = {
    "service_charge": "SERVICE CHARGE (IPL)",
    "ipl": "SERVICE CHARGE (IPL)",
    "agent_fee": "AGENT FEES / COMMISSIONS",
    "komisi": "AGENT FEES / COMMISSIONS",
    "listrik": "AIR + LISTRIK",
    "air": "AIR + LISTRIK",
    "insurance": "INSURANCE",
    "asuransi": "INSURANCE",
    "maintenance": "INTERIOR MAINTENANCE",
    "perawatan": "INTERIOR MAINTENANCE",
    "repair": "INTERIOR REPAIRS / RENOVATION",
    "renovasi": "INTERIOR REPAIRS / RENOVATION",
    "housekeeping": "HOUSEKEEPING",
    "cleaning": "HOUSEKEEPING",
    "pbb": "LAND TAX (PBB)",
    "pajak": "LAND TAX (PBB)",
    "cicilan": "BORROWING EXPENSES",
    "loan": "LOAN(S) INTEREST",
    "parking": "PARKING",
    "parkir": "PARKING",
    "wifi": "INTERNET / WIFI",
    "internet": "INTERNET / WIFI",
    "gas": "GAS",
    "travel": "TRAVEL EXPENSES",
}

MONTH_MAP = {
    "jan": "JAN", "januari": "JAN", "january": "JAN",
    "feb": "FEB", "februari": "FEB", "february": "FEB",
    "mar": "MAR", "maret": "MAR", "march": "MAR",
    "apr": "APR", "april": "APR",
    "mei": "MAY", "may": "MAY",
    "jun": "JUN", "juni": "JUN", "june": "JUN",
    "jul": "JUL", "juli": "JUL", "july": "JUL",
    "ags": "AUG", "agustus": "AUG", "august": "AUG", "aug": "AUG",
    "sep": "SEPT", "september": "SEPT",
    "okt": "OCT", "oktober": "OCT", "october": "OCT",
    "nov": "NOV", "november": "NOV",
    "des": "DEC", "desember": "DEC", "december": "DEC",
}

MONTH_COLUMNS = {
    "JAN": "C", "FEB": "D", "MAR": "E", "APR": "F",
    "MAY": "G", "JUN": "H", "JUL": "I", "AUG": "J",
    "SEPT": "K", "OCT": "L", "NOV": "M", "DEC": "N",
}

CATEGORY_ROWS = {
    "RENTAL INCOME": 5,
    "OTHER RENTAL INCOME": 6,
    "MARKETING / ADVERTISING": 11,
    "SERVICE CHARGE (IPL)": 12,
    "AGENT FEES / COMMISSIONS": 13,
    "AIR + LISTRIK": 14,
    "INSURANCE": 15,
    "INTERIOR MAINTENANCE": 16,
    "INTERIOR REPAIRS / RENOVATION": 17,
    "HOUSEKEEPING": 18,
    "EXTERIOR MAINTENANCE": 19,
    "EXTERIOR REPAIRS": 20,
    "GROUNDSKEEPING": 21,
    "GAS": 22,
    "SEWAGE": 23,
    "REFUSE": 24,
    "INTERNET / WIFI": 25,
    "PARKING": 26,
    "CORRESPONDENCE": 27,
    "CARETAKER FEES / SALARY": 28,
    "TRAVEL EXPENSES": 29,
    "EQUIPMENT / APPLIANCE PURCHASES": 30,
    "EQUIPMENT / APPLIANCE RENTAL FEES": 31,
    "LAND TAX (PBB)": 32,
    "BORROWING EXPENSES": 33,
    "LOAN(S) INTEREST": 34,
    "RENOVATION (MAJOR)": 35,
    "OTHER 1": 36,
    "OTHER 2": 37,
    "OTHER 3": 38,
}
