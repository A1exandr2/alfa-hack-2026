"""Прозрачный rule-based скоринг риска для микробизнеса."""
from typing import List, Tuple


def calculate_risk(
    company: dict, financials: dict, credit: dict
) -> Tuple[float, List[str]]:
    """
    Возвращает (score 0-100, top_factors).
    
    Args:
        company: {"company_age": float}
        financials: {"revenue": float, "profit_margin": float}
        credit: {"has_overdue": int, "debt_load": float}
    """

    score = 50.0
    factors: List[str] = []

    age = company["company_age"]
    if age < 1:
        score += 20
        factors.append("Компания моложе 1 года")
    elif age < 2:
        score += 10
        factors.append("Молодой возраст компании")
    elif age > 5:
        score -= 15
        factors.append("Длительная история работы (+5 лет)")

    if credit["has_overdue"]:
        score += 25
        factors.append("Есть просрочки в БКИ")

    if credit["debt_load"] > 1.0:
        score += 15
        factors.append("Высокая долговая нагрузка")
    elif credit["debt_load"] > 0.5:
        score += 5
        factors.append("Умеренная долговая нагрузка")

    margin = financials["profit_margin"]
    if margin < 0:
        score += 15
        factors.append("Отрицательная рентабельность")
    elif margin > 0.15:
        score -= 10
        factors.append("Высокая рентабельность")

    score = max(0.0, min(100.0, score))
    return score, factors[:3]


def get_risk_level(score: float) -> str:
    if score <= 30:
        return "Low"
    if score <= 60:
        return "Medium"
    return "High"


def get_decision(score: float) -> str:
    return "APPROVED" if score <= 60 else "MANUAL_REVIEW"