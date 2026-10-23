"""Единая точка входа ML-модуля для backend. Backend импортирует только это."""
from typing import Optional

from ml.llm_assistant.service import get_ai_advice
from ml.risk_scoring import calculate_risk, get_risk_level


def score_and_explain(
    company: dict,
    financials: dict,
    credit: dict,
    loan_amount: float,
    user_query: Optional[str] = None,
    loan_term_months: Optional[int] = None,
    product: Optional[dict] = None,
) -> dict:
    """
    Полный ML-пайплайн: rule-based risk score + LLM-исход и объяснение.

    Args:
        company: {"company_age": float}
        financials: {"revenue": float, "profit_margin": float}
        credit: {"has_overdue": int, "debt_load": float}
        loan_amount: сумма кредита
        user_query: дополнительная информация от клиента
        loan_term_months: срок заявки в месяцах, если выбран продукт
        product: выбранный продукт и его ограничения, если он есть
    
    Returns:
        {
            "risk_score": float, 
            "risk_level": "Low" | "Medium" | "High",
            "decision": "APPROVED" | "CONDITIONAL_APPROVAL" | "REJECTED",
            "top_factors": [str],
            "ai_advice": {"source": "AI"|"Fallback_Rules", "data": {...}}
        }
    """
    score, factors = calculate_risk(company, financials, credit)
    result = {
        "risk_score": score, 
        "risk_level": get_risk_level(score),
        "top_factors": factors,
        "ai_advice": None
    }

    effective_query = user_query
    if not effective_query or not effective_query.strip():
        effective_query = (
            "Пожалуйста, проанализируй финансовые показатели компании, оцени риски и "
            "порекомендуй наиболее подходящий кредитный продукт."
        )

    raw = {
        "company_age": company["company_age"],
        "revenue": financials["revenue"],
        "profit_margin": financials["profit_margin"],
        "has_overdue": credit["has_overdue"],
        "debt_load": credit["debt_load"],
        "loan_amount": loan_amount,
        "user_query": effective_query,
        "loan_term_months": loan_term_months,
        "product": product,
    }

    result["ai_advice"] = get_ai_advice(raw, score, factors)
    result["decision"] = result["ai_advice"]["data"]["decision"]

    return result