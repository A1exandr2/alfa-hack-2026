"""Единая точка входа ML-модуля для backend. Backend импортирует только это."""
from typing import Optional

from ml.llm_assistant.service import get_ai_advice
from ml.risk_scoring import calculate_risk, get_decision, get_risk_level


def score_and_explain(
    company: dict,
    financials: dict,
    credit: dict,
    loan_amount: float,
    user_query: Optional[str] = None,
) -> dict:
    """
    Полный ML-пайплайн: скоринг + LLM-объяснение.

    Args:
        company: {"company_age": float}
        financials: {"revenue": float, "profit_margin": float}
        credit: {"has_overdue": int, "debt_load": float}
        loan_amount: сумма кредита
        user_query: дополнительная информация от клиента
    
    Returns:
        {
            "risk_score": float, 
            "risk_level": "Low" | "Medium" | "High",
            "decision": "APPROVED" | "MANUAL_REVIEW", 
            "top_factors": [str],
            "ai_advice": None | {"source": "AI"|"Fallback_Rules", "data": {...}}
        }
    """
    score, factors = calculate_risk(company, financials, credit)
    result = {
        "risk_score": score, 
        "risk_level": get_risk_level(score),
        "decision": get_decision(score), 
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
    }

    result["ai_advice"] = get_ai_advice(raw, score, factors)

    return result