from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ApplicationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: UUID | None = None
    purpose_category: Literal["working_capital", "investment", "urgent", "other"] = "other"
    requested_amount: Decimal = Field(
        gt=Decimal("0"), max_digits=15, decimal_places=2
    )
    term_months: int = Field(gt=0)
    purpose: str = Field(min_length=1, max_length=500)
    additional_info: str = Field(default="", max_length=1000)

    @field_validator("purpose")
    @classmethod
    def normalize_purpose(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Purpose cannot be blank")
        return value


class ApplicationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    product_id: UUID
    requested_amount: Decimal
    term_months: int
    purpose: str
    additional_info: str = ""
    purpose_category: str = "other"
    pricing: dict[str, object] | None = None
    status: str
    created_at: datetime
    updated_at: datetime


class ApplicationUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: UUID | None = None
    purpose_category: Literal["working_capital", "investment", "urgent", "other"] | None = None
    requested_amount: Decimal | None = Field(
        default=None,
        gt=Decimal("0"),
        max_digits=15,
        decimal_places=2,
    )
    term_months: int | None = Field(default=None, gt=0)
    purpose: str | None = Field(default=None, min_length=1, max_length=500)
    additional_info: str | None = Field(default=None, max_length=1000)

    @field_validator("purpose")
    @classmethod
    def normalize_purpose(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("Purpose cannot be blank")
        return value

    @model_validator(mode="after")
    def validate_changes(self) -> "ApplicationUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("At least one application field must be provided")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Application fields cannot be null")
        return self


class ApplicationEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sequence: int
    event_type: str
    from_status: str | None
    to_status: str | None
    actor_type: str
    actor_user_id: UUID | None
    occurred_at: datetime
    details: dict[str, object]


class ScoringAdviceDataSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["APPROVED", "CONDITIONAL_APPROVAL", "REJECTED"]
    conditions: list[str]
    recommended_product: Literal[
        "Оборотный", "Инвестиционный", "Рефинансирование"
    ]
    explanation: str
    top_risk_factors: list[str]
    next_step: str


class ScoringAdviceSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Literal["AI", "Fallback_Rules"]
    data: ScoringAdviceDataSnapshot


class ApplicationRiskAssessment(BaseModel):
    model_config = ConfigDict(extra="ignore")

    decision: Literal["APPROVED", "CONDITIONAL_APPROVAL", "REJECTED"]
    risk_score: float = Field(ge=0, le=100, allow_inf_nan=False)
    risk_level: Literal["Low", "Medium", "High"]
    top_factors: list[str]
    ai_advice: ScoringAdviceSnapshot

    @model_validator(mode="after")
    def validate_decision_consistency(self) -> "ApplicationRiskAssessment":
        if self.decision != self.ai_advice.data.decision:
            raise ValueError("Decision does not match the normalized AI advice")
        if self.decision == "CONDITIONAL_APPROVAL" and not self.ai_advice.data.conditions:
            raise ValueError("Conditional approval must include review conditions")
        if self.decision != "CONDITIONAL_APPROVAL" and self.ai_advice.data.conditions:
            raise ValueError("Only conditional approval may include review conditions")
        return self


class ApplicationDecisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    outcome: Literal["APPROVED", "CONDITIONAL_APPROVAL", "REJECTED"]
    source: Literal["AI", "Fallback_Rules"]
    risk_score: float
    risk_level: Literal["Low", "Medium", "High"]
    explanation: str
    recommended_product: Literal[
        "Оборотный", "Инвестиционный", "Рефинансирование"
    ]
    next_step: str
    top_factors: list[str]
    conditions: list[str]
    created_at: datetime


class ApplicationReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: Literal["APPROVED", "REJECTED"]
    comment: str | None = Field(default=None, max_length=1000)

    @field_validator("comment")
    @classmethod
    def normalize_comment(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class ApplicationReviewRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    outcome: Literal["APPROVED", "REJECTED"]
    reviewer_user_id: UUID
    comment: str | None
    created_at: datetime


class ApplicationReviewResponse(BaseModel):
    application_id: UUID
    status: Literal["DECISION", "REJECTED"]
    review: ApplicationReviewRecordResponse
    original_decision: ApplicationDecisionResponse


class ApplicationSubmissionResponse(ApplicationResponse):
    decision: ApplicationDecisionResponse | None = None
    required_fields: list[str] = Field(default_factory=list)

class ApplicationQuoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requested_amount: Decimal = Field(gt=Decimal("0"), max_digits=15, decimal_places=2)
    term_months: int = Field(gt=0, le=600)
    purpose_category: Literal["working_capital", "investment", "urgent", "other"] = "other"
