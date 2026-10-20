from fastapi import FastAPI


app = FastAPI(
    title="Smart Credit Cabinet API",
    description="Backend API цифрового кредитного конвейера",
    version="0.1.0",
)


@app.get("/api/v1/health", tags=["system"])
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "backend"}
