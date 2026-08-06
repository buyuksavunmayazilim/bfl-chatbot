"""
Katman 2 — pgvector Embedding Similarity Servisi

Aktif model ve sütun config'den okunur:
  similarity_model  → BAAI/bge-m3
  similarity_column → embedding_bge_1024

Model değiştirmek için sadece config.py güncellenir.
"""
from dataclasses import dataclass
from functools import lru_cache
import re

import asyncpg
from sentence_transformers import SentenceTransformer

from app.core.config import settings
from app.core.context import TenantContext


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


# Embedding oncesi temizlik: soru isareti ve benzeri noktalama, vektore gereksiz
# etki etmesin diye kaldirilir. Hem Q&A eklerken hem gelen mesajda uygulanir, boylece
# "Yolda kaldim?" ile "Yolda kaldim" ayni embedding'i uretir.
_PUNCT_RE = re.compile(r"""[?!.,;:…“”"«»()\[\]{}<>/\\|@#*_~^]+""")


def clean_for_embedding(text: str) -> str:
    text = _PUNCT_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def embed(text: str) -> list[float]:
    return get_model().encode(clean_for_embedding(text), normalize_embeddings=True).tolist()


# ─── Similarity sorgusu ───────────────────────────────────────────────────────
async def search_similar(
    ctx: TenantContext,
    message: str,
    threshold: float | None = None,
    top_k: int = 1,
) -> SimilarityResult:
    if threshold is None:
        threshold = ctx.content.setting(
            "similarity_threshold_high", ctx.config.similarity_threshold_high
        )

    col = ctx.similarity_column
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

    async with ctx.pool.acquire() as conn:
        rows = await conn.fetch(query, vector_str, top_k)

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