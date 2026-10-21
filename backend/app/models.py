from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    inn: Mapped[str] = mapped_column(String(12), unique=True, nullable=False)
    ogrn: Mapped[str] = mapped_column(String(15), unique=True, nullable=True)
    registration_date: Mapped[date] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    director_name: Mapped[str] = mapped_column(String(255), nullable=True)
    okved: Mapped[str] = mapped_column(String(16), nullable=True)
    data_source: Mapped[str] = mapped_column(
        String(32), nullable=False, default="DEMO"
    )

    users: Mapped[list["User"]] = relationship(back_populates="company")
    financials: Mapped["Financials"] = relationship(
        back_populates="company", uselist=False
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    company_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("companies.id"), nullable=True
    )

    company: Mapped[Company | None] = relationship(back_populates="users")


class Financials(Base):
    __tablename__ = "financials"
    __table_args__ = (
        CheckConstraint("revenue_annual >= 0", name="ck_financials_revenue_nonnegative"),
        CheckConstraint("expenses_annual >= 0", name="ck_financials_expenses_nonnegative"),
        CheckConstraint("current_debt >= 0", name="ck_financials_debt_nonnegative"),
        CheckConstraint("employees >= 0", name="ck_financials_employees_nonnegative"),
    )

    company_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("companies.id"), primary_key=True
    )
    revenue_annual: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, default=0
    )
    profit_annual: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, default=0
    )
    expenses_annual: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, default=0
    )
    employees: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_debt: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, default=0
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    source: Mapped[str] = mapped_column(
        String(32), nullable=False, default="USER_VERIFIED"
    )

    company: Mapped[Company] = relationship(back_populates="financials")
