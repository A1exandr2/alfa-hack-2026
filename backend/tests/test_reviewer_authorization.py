from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.auth.dependencies import get_current_reviewer
from app.auth.schemas import RegisterRequest
from app.models import User


def _user(role: str) -> User:
    return User(
        id=uuid4(),
        email=f"{uuid4()}@example.com",
        password_hash="test-hash",
        full_name="Test User",
        role=role,
    )


def test_registration_cannot_assign_reviewer_role() -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(
            email="user@example.com",
            password="StrongPass123!",
            full_name="Test User",
            role="REVIEWER",
        )


@pytest.mark.asyncio
async def test_reviewer_dependency_rejects_regular_user() -> None:
    user = _user("USER")

    with pytest.raises(HTTPException) as error:
        await get_current_reviewer(user)

    assert error.value.status_code == 403
    assert error.value.detail == "Reviewer role required"


@pytest.mark.asyncio
async def test_reviewer_dependency_accepts_reviewer() -> None:
    user = _user("REVIEWER")

    assert await get_current_reviewer(user) is user
