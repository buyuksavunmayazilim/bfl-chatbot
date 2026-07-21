"""
Katman 2 — pgvector Embedding Similarity Servisi

Aktif model ve sütun config'den okunur:
  similarity_model  → BAAI/bge-m3
  similarity_column → embedding_bge_1024

Model değiştirmek için sadece config.py güncellenir.
"""
from dataclasses import dataclass
from functools import lru_cache

import asyncpg
from sentence_transformers import SentenceTransformer

from app.core.config import settings


# ─── Veri yapısı ─────────────────────────────────────────────────────────────
@dataclass
class SimilarityResult:
    matched: bool
    score: float = 0.0
    question: str | None = None
    answer: str | None = None
    intent_category: str | None = None


# ─── Model singleton ─────────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def get_model() -> SentenceTransformer:
    print(f"[SimilarityService] Model yukleniyor: {settings.similarity_model}")
    model = SentenceTransformer(settings.similarity_model)
    print("[SimilarityService] Model hazir.")
    return model


def embed(text: str) -> list[float]:
    return get_model().encode(text, normalize_embeddings=True).tolist()


# ─── Similarity sorgusu ───────────────────────────────────────────────────────
async def search_similar(
    message: str,
    threshold: float | None = None,
    top_k: int = 1,
) -> SimilarityResult:
    if threshold is None:
        threshold = settings.similarity_threshold_high

    col = settings.similarity_column
    vector_str = str(embed(message))

    # NOT: intent_category='fallback' HARİÇ tutulur. "fallback" gerçek bir cevap
    # intenti değil; bot anlamadığında fallback_service (iletişim toplama) devreye
    # girmeli. Aksi halde "bir problemim var" gibi sorgular canned cevaba takılıp
    # gerçek fallback akışını engelliyordu.
    query = f"""
        SELECT
            question,
            answer,
            intent_category,
            1 - ({col} <=> $1::vector) AS score
        FROM qa_embeddings
        WHERE {col} IS NOT NULL
          AND intent_category <> 'fallback'
        ORDER BY {col} <=> $1::vector
        LIMIT $2
    """

    conn = await asyncpg.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        database=settings.postgres_db,
        user=settings.postgres_user,
        password=settings.postgres_password,
    )

    try:
        rows = await conn.fetch(query, vector_str, top_k)
    finally:
        await conn.close()

    if not rows:
        return SimilarityResult(matched=False)

    best = rows[0]
    score = float(best["score"])

    print(
        f"[SimilarityService] model={settings.similarity_model.split('/')[-1]} "
        f"score={score:.4f} threshold={threshold} "
        f"intent={best['intent_category']} "
        f"soru='{best['question'][:40]}'"
    )

    if score >= threshold:
        return SimilarityResult(
            matched=True,
            score=score,
            question=best["question"],
            answer=best["answer"],
            intent_category=best["intent_category"],
        )

    return SimilarityResult(matched=False, score=score)