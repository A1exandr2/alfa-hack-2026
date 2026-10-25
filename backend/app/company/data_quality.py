"""Field provenance and submission requirements; never infer absent values."""
from datetime import datetime, timezone

FINANCIAL_FIELDS = ("revenue_annual", "profit_annual", "expenses_annual", "employees", "current_debt")
CREDIT_FIELDS = ("active_credits", "closed_credits", "overdue_count", "overdue_amount")
MANUAL_SOURCES = {"USER_INPUT", "USER_VERIFIED", "manual", "DOCUMENT_USER_CONFIRMED"}


def provenance(data, fields):
    now = datetime.now(timezone.utc).isoformat()
    return {field: {"source": data.source, "report_year": getattr(data, "report_year", None), "fetched_at": now, "as_of": data.as_of.isoformat() if getattr(data, "as_of", None) else None, "consent_id": getattr(data, "consent_id", None)}
            for field in fields if getattr(data, field) is not None}


def manual_fields(record, fields):
    sources = getattr(record, "field_sources", None) or {}
    return [field for field in fields if getattr(record, field) is not None and
            (sources.get(field, {}).get("source", record.source) if isinstance(sources.get(field, {}), dict) else sources[field]) in MANUAL_SOURCES]


def missing_fields(company, financials, history):
    from datetime import date
    required = []
    if company.registration_date is None or company.registration_date > date.today():
        required.append("company.registration_date")
    required += ["financials." + f for f in FINANCIAL_FIELDS if getattr(financials, f) is None]
    if getattr(company, "data_source", "DEMO") != "DEMO" and getattr(financials, "report_year", None) is None:
        required.append("financials.report_year")
    if financials.revenue_annual is not None and financials.revenue_annual <= 0:
        required.append("financials.revenue_annual")
    required += ["credit_history." + f for f in CREDIT_FIELDS if getattr(history, f) is None]
    return required
