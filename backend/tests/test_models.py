from sqlalchemy import CheckConstraint, inspect

from app.models import (
    Application,
    Base,
    Company,
    CreditHistory,
    CreditProduct,
    Financials,
    User,
)


def test_credit_domain_tables_are_registered() -> None:
    table_names = set(Base.metadata.tables)

    assert table_names == {
        "applications",
        "companies",
        "credit_history",
        "credit_products",
        "financials",
        "users",
    }


def test_user_belongs_to_company() -> None:
    company_id = User.__table__.c.company_id

    assert str(company_id.type) == "UUID"
    assert list(company_id.foreign_keys)[0].target_fullname == "companies.id"
    assert company_id.nullable is True


def test_financials_have_database_level_money_constraints() -> None:
    constraints = {
        str(constraint.sqltext)
        for constraint in Financials.__table__.constraints
        if hasattr(constraint, "sqltext")
    }

    assert "revenue_annual >= 0" in constraints
    assert "expenses_annual >= 0" in constraints
    assert "current_debt >= 0" in constraints
    assert "employees >= 0" in constraints


def test_credit_history_has_database_level_nonnegative_constraints() -> None:
    constraints = {
        str(constraint.sqltext)
        for constraint in CreditHistory.__table__.constraints
        if hasattr(constraint, "sqltext")
    }

    assert "active_credits >= 0" in constraints
    assert "closed_credits >= 0" in constraints
    assert "overdue_count >= 0" in constraints
    assert "overdue_amount >= 0" in constraints


def test_credit_products_have_database_level_range_constraints() -> None:
    constraints = {
        str(constraint.sqltext)
        for constraint in CreditProduct.__table_args__
        if isinstance(constraint, CheckConstraint)
    }

    assert "min_amount >= 0" in constraints
    assert "max_amount >= min_amount" in constraints
    assert "min_term_months > 0" in constraints
    assert "max_term_months >= min_term_months" in constraints
    assert "interest_rate >= 0" in constraints


def test_applications_have_database_level_amount_and_term_constraints() -> None:
    constraints = {
        str(constraint.sqltext)
        for constraint in Application.__table_args__
        if isinstance(constraint, CheckConstraint)
    }

    assert "requested_amount > 0" in constraints
    assert "term_months > 0" in constraints


def test_companies_and_users_have_unique_business_identifiers() -> None:
    assert inspect(Company).local_table.c.inn.unique is True
    assert inspect(User).local_table.c.email.unique is True
