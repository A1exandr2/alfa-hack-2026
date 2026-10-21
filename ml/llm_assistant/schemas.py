from typing import List, Literal

from pydantic import BaseModel, Field


class CreditAdvice(BaseModel):
    recommended_product: Literal[
        "Оборотный", "Инвестиционный", "Рефинансирование"
    ] = Field(description="Строго один из трёх продуктов.")

    explanation: str = Field(
        description="Объяснение для клиента, максимум 2 предложения, без банковского сленга."
    )

    top_risk_factors: List[str] = Field(
        description="Топ-3 фактора риска из предоставленных данных."
    )

    next_step: str = Field(
        description="Что клиенту сделать прямо сейчас."
    )