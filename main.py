from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.core.config import settings
from app.api.chat import router as chat_router
import asyncpg
import redis.asyncio as aioredis
import httpx
import os

app = FastAPI(title="BFL Chatbot API", version="0.1.0")

# Chat router
app.include_router(chat_router, prefix="/api/v1", tags=["chat"])

# Static files
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
async def root():
    return FileResponse(os.path.join(static_dir, "index.html"))


@app.get("/health")
async def health():
    results = {
        "status": "ok",
        "env": {
            "postgres_host": settings.postgres_host,
            "postgres_db": settings.postgres_db,
            "redis_host": settings.redis_host,
            "ollama_host": settings.ollama_host,
            "similarity_model": settings.similarity_model,
            "similarity_threshold": settings.similarity_threshold_high,
        },
        "connections": {
            "postgres": "unknown",
            "redis": "unknown",
            "ollama": "unknown",
        }
    }

    try:
        conn = await asyncpg.connect(
            host=settings.postgres_host, port=settings.postgres_port,
            database=settings.postgres_db, user=settings.postgres_user,
            password=settings.postgres_password,
        )
        await conn.fetchval("SELECT 1")
        await conn.close()
        results["connections"]["postgres"] = "ok"
    except Exception as e:
        results["connections"]["postgres"] = f"error: {e}"
        results["status"] = "degraded"

    try:
        r = aioredis.from_url(settings.redis_url)
        await r.ping()
        await r.aclose()
        results["connections"]["redis"] = "ok"
    except Exception as e:
        results["connections"]["redis"] = f"error: {e}"
        results["status"] = "degraded"

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{settings.ollama_host}/api/tags")
            if resp.status_code == 200:
                models = [m["name"] for m in resp.json().get("models", [])]
                results["connections"]["ollama"] = "ok"
                results["env"]["ollama_models"] = models
    except Exception as e:
        results["connections"]["ollama"] = f"error: {e}"

    return results