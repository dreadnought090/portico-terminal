from __future__ import annotations


def calculate_lease(
    annual_rent: int,
    broker_pct: float,
    months: int = 12,
    bank_loan_monthly: int = 0,
) -> dict:
    monthly_rent = round(annual_rent / months)
    broker_fee_annual = round(annual_rent * broker_pct / 100)
    broker_fee_monthly = round(broker_fee_annual / months)
    net_monthly = monthly_rent - broker_fee_monthly
    cashflow_monthly = net_monthly - bank_loan_monthly

    return {
        "monthly_rent": monthly_rent,
        "broker_fee_monthly": broker_fee_monthly,
        "net_monthly": net_monthly,
        "bank_loan_monthly": bank_loan_monthly,
        "cashflow_monthly": cashflow_monthly,
        "annual_rent": annual_rent,
        "broker_fee_annual": broker_fee_annual,
    }


def calculate_acquisition(
    harga: int,
    bphtb: int = 0,
    ajb: int = 0,
    appraisal: int = 0,
    perbaikan: int = 0,
    dp: int = 0,
) -> dict:
    total_perolehan = harga + bphtb + ajb + appraisal + perbaikan
    pinjaman = total_perolehan - dp
    equity = dp + bphtb + ajb + appraisal + perbaikan

    return {
        "harga": harga,
        "bphtb": bphtb,
        "ajb": ajb,
        "appraisal": appraisal,
        "perbaikan": perbaikan,
        "total_perolehan": total_perolehan,
        "dp": dp,
        "pinjaman": pinjaman,
        "equity": equity,
    }


def calculate_amortization(
    principal: int,
    annual_rate: float,
    tenor_years: int,
) -> list[dict]:
    if principal <= 0:
        return []

    monthly_rate = annual_rate / 100 / 12
    total_months = tenor_years * 12

    if monthly_rate == 0:
        monthly_payment = principal / total_months
    else:
        monthly_payment = principal * (monthly_rate * (1 + monthly_rate) ** total_months) / \
                          ((1 + monthly_rate) ** total_months - 1)

    schedule = []
    remaining = principal

    for month in range(1, total_months + 1):
        interest = round(remaining * monthly_rate)
        principal_payment = round(monthly_payment - interest)
        remaining = max(0, round(remaining - principal_payment))

        schedule.append({
            "month": month,
            "payment": round(monthly_payment),
            "interest": interest,
            "principal_payment": principal_payment,
            "remaining": remaining,
        })

    return schedule
