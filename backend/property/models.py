from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class Property:
    key: str
    name: str
    sheet_name: str

    @classmethod
    def from_config(cls, key: str, config: dict) -> Property:
        return cls(key=key, name=config["name"], sheet_name=config["sheet"])


@dataclass
class Transaction:
    property_key: str
    month: str
    category: str
    amount: int
    is_income: bool = True
    notes: str = ""


@dataclass
class Tenant:
    property_key: str
    name: str
    phone: str
    contract_start: date
    contract_end: date
    monthly_rent: int
    deposit: int
    status: str = "active"
    id_ktp: str = ""
    deposit_status: str = "held"
    notes: str = ""


@dataclass
class Reminder:
    property_key: str
    type: str
    description: str
    due_day: int
    amount: int = 0
    active: bool = True
    last_triggered: Optional[str] = None
    notes: str = ""


@dataclass
class Lease:
    property_key: str
    start_month: str
    start_year: int
    months: int
    annual_rent: int
    broker_pct: float
    bank_loan_monthly: int = 0
    tenant_name: str = ""


@dataclass
class AcquisitionCost:
    unit_name: str
    harga: int
    bphtb: int = 0
    ajb: int = 0
    appraisal: int = 0
    perbaikan: int = 0
    dp: int = 0
    pinjaman: int = 0
    lender: str = ""
    equity: int = 0
    cicilan_bulanan: int = 0
    tenor: int = 0
    fee_bank: int = 0
    tanggal_ajb: Optional[date] = None
