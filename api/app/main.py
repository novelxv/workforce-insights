import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import get_settings
from app.db import engine
from app.routes import analytics, auth, exports, risk

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

app = FastAPI(
    title="Arunika Life workforce insights",
    version="0.1.0",
    description=(
        "Governed HR metrics over a star schema, natural-language questions compiled to "
        "parameterised SQL, attrition risk with explanations, and Excel / Power BI exports. "
        "Synthetic data only."
    ),
)

if get_settings().environment == "development":
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.middleware("http")
async def headers(request: Request, call_next):
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
    response = await call_next(request)
    response.headers["x-request-id"] = rid
    response.headers["cache-control"] = "no-store"
    response.headers["x-content-type-options"] = "nosniff"
    return response


@app.get("/live", include_in_schema=False)
def live():
    """Liveness for the platform. Does not touch the database, so health checks do not
    keep a scale-to-zero Postgres awake."""
    return {"status": "ok"}


@app.get("/health", tags=["meta"])
def health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok"}


for module in (auth, analytics, risk, exports):
    app.include_router(module.router)
app.include_router(risk.model_router)
