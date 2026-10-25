from uuid import UUID

from pydantic import BaseModel, ConfigDict


class CreditProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str
    min_amount: float
    max_amount: float
    min_term_months: int
    max_term_months: int
    interest_rate: float
    is_active: bool
    data_source: str
