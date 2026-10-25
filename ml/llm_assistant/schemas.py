from typing import List, Literal

from pydantic import BaseModel, Field, model_validator


class CreditAdvice(BaseModel):
    decision: Literal["APPROVED", "CONDITIONAL_APPROVAL", "REJECTED"] = Field(
        description="Исход рассмотрения заявки."
    )

    conditions: List[str] = Field(
        max_length=5,
        description="Условия ручной проверки; пустой список для безусловного исхода.",
    )

    recommended_product: Literal["Оборотный", "Инвестиционный", "Рефинансирование"] = (
        Field(description="Строго один из трёх продуктов.")
    )

    explanation: str = Field(
        min_length=1,
        description="Объяснение для клиента, максимум 2 предложения, без банковского сленга.",
    )

    top_risk_factors: List[str] = Field(
        max_length=3, description="Топ-3 фактора риска из предоставленных данных."
    )

    next_step: str = Field(
        min_length=1, description="Что клиенту сделать прямо сейчас."
    )

    @model_validator(mode="after")
    def validate_conditions(self) -> "CreditAdvice":
        if self.decision == "CONDITIONAL_APPROVAL" and not self.conditions:
            raise ValueError("Conditional approval must include review conditions")
        if self.decision != "CONDITIONAL_APPROVAL" and self.conditions:
            raise ValueError("Only conditional approval may include review conditions")
        if any(not condition.strip() for condition in self.conditions):
            raise ValueError("Review conditions cannot be blank")
        return self
