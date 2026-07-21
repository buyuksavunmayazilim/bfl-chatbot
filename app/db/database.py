from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings


# ── Async Engine ──────────────────────────────────────────────────────────────
engine = create_async_engine(
    settings.database_url,
    echo=False,           # True yapınca tüm SQL'leri loglar — debug için kullan
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,   # bağlantı kopmuşsa otomatik yenile
)

# ── Session Factory ───────────────────────────────────────────────────────────
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# ── Base Model ────────────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    pass


# ── Dependency (FastAPI route'larında kullanılır) ─────────────────────────────
async def get_db() -> AsyncSession:
    """
    FastAPI Depends() ile kullanım:

        @router.post("/chat")
        async def chat(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()