from sqlalchemy import inspect

from app.models import Base, Company, Financials, User


def test_credit_domain_tables_are_registered() -> None:
    table_names = set(Base.metadata.tables)

    assert table_names == {"companies", "financials", "users"}


def test_user_belongs_to_company() -> None:
    company_id = User.__table__.c.company_id

    assert str(company_id.type) == "UUID"
    assert list(company_id.foreign_keys)[0].target_fullname == "companies.id"


def test_financials_have_database_level_money_constraints() -> None:
    constraints = {
        str(constraint.sqltext)
        for constraint in Financials.__table__.constraints
        if hasattr(constraint, "sqltext")
    }

    assert "revenue_annual >= 0" in constraints
    assert "current_debt >= 0" in constraints


def test_companies_and_users_have_unique_business_identifiers() -> None:
    assert inspect(Company).local_table.c.inn.unique is True
    assert inspect(User).local_table.c.email.unique is True
