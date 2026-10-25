from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgreSQLUUID
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

    full_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    kpp: Mapped[str | None] = mapped_column(String(9), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)

    users: Mapped[list["User"]] = relationship(back_populates="company")
    financials: Mapped["Financials"] = relationship(
        back_populates="company", uselist=False
    )
    credit_history: Mapped["CreditHistory"] = relationship(
        back_populates="company", uselist=False
    )


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('USER', 'REVIEWER', 'ADMIN')", name="ck_users_role"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        String(16), nullable=False, default="USER", server_default="USER"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
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
    revenue_annual: Mapped[Decimal | None] = mapped_column(
        Numeric(15, 2), nullable=True
    )
    profit_annual: Mapped[Decimal | None] = mapped_column(
        Numeric(15, 2), nullable=True
    )
    expenses_annual: Mapped[Decimal | None] = mapped_column(
        Numeric(15, 2), nullable=True
    )
    employees: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_debt: Mapped[Decimal | None] = mapped_column(
        Numeric(15, 2), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    source: Mapped[str] = mapped_column(
        String(32), nullable=False, default="USER_INPUT"
    )

    report_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    field_sources: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")

    company: Mapped[Company] = relationship(back_populates="financials")


class CreditHistory(Base):
    __tablename__ = "credit_history"
    __table_args__ = (
        CheckConstraint(
            "active_credits >= 0", name="ck_credit_history_active_nonnegative"
        ),
        CheckConstraint(
            "closed_credits >= 0", name="ck_credit_history_closed_nonnegative"
        ),
        CheckConstraint(
            "overdue_count >= 0", name="ck_credit_history_overdue_nonnegative"
        ),
        CheckConstraint(
            "overdue_amount >= 0", name="ck_credit_history_amount_nonnegative"
        ),
    )

    company_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("companies.id"), primary_key=True
    )
    active_credits: Mapped[int | None] = mapped_column(Integer, nullable=True)
    closed_credits: Mapped[int | None] = mapped_column(Integer, nullable=True)
    overdue_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    overdue_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(15, 2), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="UNAVAILABLE")
    report_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    field_sources: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")

    as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    company: Mapped[Company] = relationship(back_populates="credit_history")


class CreditProduct(Base):
    __tablename__ = "credit_products"
    __table_args__ = (
        CheckConstraint("min_amount >= 0", name="ck_credit_products_min_amount_nonnegative"),
        CheckConstraint("max_amount >= min_amount", name="ck_credit_products_amount_range"),
        CheckConstraint("min_term_months > 0", name="ck_credit_products_min_term_positive"),
        CheckConstraint("max_term_months >= min_term_months", name="ck_credit_products_term_range"),
        CheckConstraint("interest_rate >= 0", name="ck_credit_products_rate_nonnegative"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    name: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    min_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    max_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    min_term_months: Mapped[int] = mapped_column(Integer, nullable=False)
    max_term_months: Mapped[int] = mapped_column(Integer, nullable=False)
    interest_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    data_source: Mapped[str] = mapped_column(String(32), nullable=False, default="DEMO")


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (
        CheckConstraint(
            "requested_amount > 0", name="ck_applications_amount_positive"
        ),
        CheckConstraint("term_months > 0", name="ck_applications_term_positive"),
        Index("ix_applications_user_created_at", "user_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    company_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("companies.id"), nullable=False
    )
    product_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("credit_products.id"), nullable=False
    )
    requested_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    term_months: Mapped[int] = mapped_column(Integer, nullable=False)
    purpose: Mapped[str] = mapped_column(String(500), nullable=False)
    additional_info: Mapped[str] = mapped_column(String(1000), nullable=False, default="", server_default="")
    purpose_category: Mapped[str] = mapped_column(String(32), nullable=False, default="other", server_default="other")
    pricing: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="DRAFT", server_default="DRAFT"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ApplicationSnapshot(Base):
    __tablename__ = "application_snapshots"
    __table_args__ = (
        CheckConstraint(
            "schema_version > 0", name="ck_application_snapshot_version_positive"
        ),
        CheckConstraint(
            "snapshot_version > 0", name="ck_application_snapshot_attempt_positive"
        ),
        UniqueConstraint(
            "application_id",
            "snapshot_version",
            name="uq_application_snapshots_version",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    application_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    snapshot_version: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)


class ApplicationDecision(Base):
    __tablename__ = "application_decisions"
    __table_args__ = (
        CheckConstraint(
            "outcome IN ('APPROVED', 'CONDITIONAL_APPROVAL', 'REJECTED')",
            name="ck_application_decisions_outcome",
        ),
        CheckConstraint(
            "source IN ('AI', 'Fallback_Rules')",
            name="ck_application_decisions_source",
        ),
        CheckConstraint(
            "risk_score >= 0 AND risk_score <= 100",
            name="ck_application_decisions_score_range",
        ),
        CheckConstraint(
            "risk_level IN ('Low', 'Medium', 'High')",
            name="ck_application_decisions_risk_level",
        ),
        CheckConstraint(
            "recommended_product IN ('Оборотный', 'Инвестиционный', 'Рефинансирование')",
            name="ck_application_decisions_recommended_product",
        ),
        UniqueConstraint(
            "application_id", name="uq_application_decisions_application_id"
        ),
        UniqueConstraint("snapshot_id", name="uq_application_decisions_snapshot_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    application_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    snapshot_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("application_snapshots.id", ondelete="CASCADE"),
        nullable=False,
    )
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    risk_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_product: Mapped[str] = mapped_column(String(32), nullable=False)
    next_step: Mapped[str] = mapped_column(Text, nullable=False)
    top_factors: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    conditions: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ApplicationReview(Base):
    __tablename__ = "application_reviews"
    __table_args__ = (
        CheckConstraint(
            "outcome IN ('APPROVED', 'REJECTED')",
            name="ck_application_reviews_outcome",
        ),
        UniqueConstraint(
            "application_id", name="uq_application_reviews_application_id"
        ),
        UniqueConstraint("decision_id", name="uq_application_reviews_decision_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    application_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    decision_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("application_decisions.id", ondelete="CASCADE"),
        nullable=False,
    )
    reviewer_user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ApplicationEvent(Base):
    __tablename__ = "application_events"
    __table_args__ = (
        UniqueConstraint(
            "application_id", "sequence", name="uq_application_events_sequence"
        ),
        CheckConstraint(
            "sequence > 0", name="ck_application_events_sequence_positive"
        ),
        CheckConstraint(
            "actor_type IN ('USER', 'SYSTEM')", name="ck_application_events_actor_type"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    application_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    actor_type: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_user_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    details: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict
    )


class CreditHistoryConsent(Base):
    __tablename__ = "credit_history_consents"
    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    company_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    text_version: Mapped[str] = mapped_column(String(32), nullable=False, default="credit-report-v1")


class DocumentImport(Base):
    __tablename__ = "document_imports"
    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    company_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    extracted: Mapped[dict] = mapped_column(JSONB, nullable=False)
    accepted_values: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AdminAudit(Base):
    __tablename__ = "admin_audit"
    __table_args__ = (Index("ix_admin_audit_created_at", "created_at"),)
    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    actor_user_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    actor_email: Mapped[str] = mapped_column(String(320), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
