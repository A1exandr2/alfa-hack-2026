from ml.llm_assistant.schemas import CreditAdvice
from ml.risk_scoring import get_decision


def rule_based_fallback(raw_data: dict, risk_score: float) -> CreditAdvice:
    decision = get_decision(risk_score)
    conditions = (
        ["Заявка требует ручной проверки."]
        if decision == "CONDITIONAL_APPROVAL"
        else []
    )
    if raw_data.get("has_overdue") == 1 or raw_data.get("debt_load", 0) > 1.0:
        return CreditAdvice(
            decision=decision,
            conditions=conditions,
            recommended_product="Рефинансирование", 
            explanation="У вас высокая долговая нагрузка или есть просрочки. Рекомендуем рефинансирование для снижения платежей.",
            top_risk_factors=["Высокая долговая нагрузка", "Наличие просрочек"], 
            next_step="Оставить заявку на рефинансирование",
        )
    if raw_data.get("company_age", 0) < 2:
        return CreditAdvice(
            decision=decision,
            conditions=conditions,
            recommended_product="Оборотный", 
            explanation="Для молодых компаний рекомендуем оборотный кредит на короткий срок.",
            top_risk_factors=["Молодой возраст компании"], 
            next_step="Заполнить заявку на оборотный кредит",
        )
    return CreditAdvice(
        decision=decision,
        conditions=conditions,
        recommended_product="Инвестиционный", 
        explanation="Ваши показатели стабильны. Вы можете рассмотреть инвестиционный кредит для развития.",
        top_risk_factors=["Стабильные показатели"], 
        next_step="Перейти в каталог продуктов",
    )