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
    Включает заранее рассчитанный risk_score и данные конкретной заявки.
    """
    product = raw_data.get("product")
    if product is None:
        product_context = "Продукт не выбран."
    else:
        product_context = (
            f"Продукт: {product['name']}; ставка: {product['interest_rate']}%; "
            f"сумма: {product['min_amount']}–{product['max_amount']} руб.; "
            f"срок: {product['min_term_months']}–{product['max_term_months']} мес."
        )
    loan_term = raw_data.get("loan_term_months")
    loan_term_context = (
        f"{loan_term} мес." if loan_term is not None else "не указан"
    )
    context = f"""
    Данные компании:
    - Возраст: {raw_data['company_age']} лет.
    - Выручка за год: {raw_data['revenue']} руб.
    - Рентабельность: {raw_data['profit_margin'] * 100:.1f}%.
    - Долговая нагрузка (Долг/Выручка): {raw_data['debt_load']:.2f}.
    - Просрочки в БКИ: {'Да' if raw_data['has_overdue'] else 'Нет'}.
    - Запрашиваемая сумма: {raw_data['loan_amount']} руб.
    - Запрашиваемый срок: {loan_term_context}
    - {product_context}

    Автоматический скоринг:
    - Риск-скор: {risk_score:.1f}/100.
    - Ключевые факторы риска: {', '.join(risk_factors) if risk_factors else 'не выявлены'}.
    """
    return {
        "context": context, 
        "safe_query": sanitize_user_query(raw_data["user_query"]),
    }
