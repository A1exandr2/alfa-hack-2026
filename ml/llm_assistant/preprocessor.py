import re

DANGEROUS_PATTERNS = [
    r"забудь\s+(все\s+)?(предыдущие\s+)?инструкции",
    r"ты\s+теперь\s+",
    r"игнорируй\s+",
    r"system\s*prompt",
    r"<\|.*?\|>",
]


def sanitize_user_query(query: str) -> str:
    """Защита от prompt-injection."""
    cleaned = query
    for pattern in DANGEROUS_PATTERNS:
        cleaned = re.sub(pattern, "[УДАЛЕНО]", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()[:500]


def enrich_data_for_llm(
    raw_data: dict, risk_score: float, risk_factors: list
) -> dict:
    """
    Превращает сырые цифры в текстовый контекст для LLM.
    Включает заранее рассчитанный risk_score — модели остаётся только интерпретировать.
    """
    context = f"""
    Данные компании:
    - Возраст: {raw_data['company_age']} лет.
    - Рентабельность: {raw_data['profit_margin'] * 100:.1f}%.
    - Долговая нагрузка (Долг/Выручка): {raw_data['debt_load']:.2f}.
    - Просрочки в БКИ: {'Да' if raw_data['has_overdue'] else 'Нет'}.
    - Запрашиваемая сумма: {raw_data['loan_amount']} руб.

    Автоматический скоринг:
    - Риск-скор: {risk_score:.1f}/100.
    - Ключевые факторы риска: {', '.join(risk_factors) if risk_factors else 'не выявлены'}.
    """
    return {
        "context": context, 
        "safe_query": sanitize_user_query(raw_data["user_query"]),
    }
