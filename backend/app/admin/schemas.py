from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class UserAccessUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    role: Literal['USER', 'REVIEWER']
    is_active: bool
    reason: str = Field(min_length=3, max_length=500)


class StaffReviewRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    outcome: Literal['APPROVED', 'REJECTED']
    comment: str = Field(min_length=3, max_length=1000)
