from fastapi import FastAPI

from app.auth.router import router as auth_router


app = FastAPI(
    title="Smart Credit Cabinet API",
    description="Backend API цифрового кредитного конвейера",
    version="0.1.0",
)
app.include_router(auth_router)


@app.get("/api/v1/health", tags=["system"])
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "backend"}
