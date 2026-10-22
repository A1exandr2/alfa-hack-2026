import asyncio

from fastapi import FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.company.router import router as company_router
from app.credit_products.router import router as credit_products_router
from app.database import engine

from app.auth.router import router as auth_router
from app.applications.router import router as applications_router


app = FastAPI(
    title="Smart Credit Cabinet API",
    description="Backend API цифрового кредитного конвейера",
    version="0.1.0",
)
app.include_router(auth_router)
app.include_router(company_router)
app.include_router(credit_products_router)
app.include_router(applications_router)


@app.get("/api/v1/health", tags=["system"])
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "backend"}


@app.get("/api/v1/ready", tags=["system"])
async def readiness_check() -> dict[str, str]:
    try:
        async with asyncio.timeout(3):
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError, TimeoutError) as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    return {"status": "ok", "service": "backend", "database": "ok"}
