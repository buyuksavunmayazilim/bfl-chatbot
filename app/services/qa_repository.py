"""qa_embeddings icin async CRUD + semantik arama (admin API kullanir).

qa_crud.py (CLI, psycopg2) ile ayni islemleri yapar; fakat burasi async'tir,
tenant'in asyncpg havuzunu (ctx.pool) ve uygulamada ZATEN yuklu embedding
modelini (similarity_service.embed) kullanir -> model ikinci kez yuklenmez.

Soru degistiginde embedding otomatik yeniden uretilir. Embedding sutunu
tenant'a gore ctx.similarity_column'dan gelir (bge-m3 -> embedding_bge_1024).
"""
from __future__ import annotations

from typing import Any

from app.core.context import TenantContext
from app.services.similarity_service import embed


class QAError(Exception):
    """Admin QA islemlerinde beklenen hata (endpoint 400/404'e cevirir)."""


def _vec(text: str) -> str:
    # asyncpg'ye metin olarak verilir, SQL'de ::vector'e cast edilir.
    return str(embed(text))


async def list_qa(
    ctx: TenantContext,
    intent: str | None = None,
    text: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    col = ctx.similarity_column
    conditions: list[str] = []
    params: list[Any] = []

    if intent:
        params.append(intent)
        conditions.append(f"intent_category = ${len(params)}")
    if text:
        params.append(f"%{text}%")
        idx = len(params)
        conditions.append(f"(question ILIKE ${idx} OR answer ILIKE ${idx})")

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    params.append(limit)
    limit_idx = len(params)
    params.append(offset)
    offset_idx = len(params)

    query = f"""
        SELECT id, question, answer, intent_category, is_augmented, created_at,
               {col} IS NOT NULL AS has_embedding,
               COUNT(*) OVER() AS total
        FROM qa_embeddings
        {where}
        ORDER BY id DESC
        LIMIT ${limit_idx} OFFSET ${offset_idx}
    """
    async with ctx.pool.acquire() as conn:
        rows = await conn.fetch(query, *params)

    total = rows[0]["total"] if rows else 0
    items = []
    for r in rows:
        d = dict(r)
        d.pop("total", None)
        items.append(d)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


async def get_qa(ctx: TenantContext, qa_id: int) -> dict[str, Any]:
    col = ctx.similarity_column
    async with ctx.pool.acquire() as conn:
        row = await conn.fetchrow(
            f"""
            SELECT id, question, answer, intent_category, is_augmented, created_at,
                   {col} IS NOT NULL AS has_embedding
            FROM qa_embeddings WHERE id = $1
            """,
            qa_id,
        )
    if row is None:
        raise QAError(f"Kayit bulunamadi: id={qa_id}")
    return dict(row)


async def create_qa(
    ctx: TenantContext,
    question: str,
    answer: str,
    intent: str,
    is_augmented: bool = False,
    allow_duplicate: bool = False,
) -> dict[str, Any]:
    question = question.strip()
    answer = answer.strip()
    intent = intent.strip()
    if not question or not answer or not intent:
        raise QAError("question, answer ve intent bos olamaz.")

    col = ctx.similarity_column
    vector = _vec(question)

    async with ctx.pool.acquire() as conn:
        async with conn.transaction():
            if not allow_duplicate:
                dup = await conn.fetchval(
                    "SELECT id FROM qa_embeddings WHERE question = $1 LIMIT 1",
                    question,
                )
                if dup is not None:
                    raise QAError(f"Bu soru zaten kayitli: id={dup}")

            row = await conn.fetchrow(
                f"""
                INSERT INTO qa_embeddings
                    (question, answer, intent_category, is_augmented, {col}, created_at)
                VALUES ($1, $2, $3, $4, $5::vector, NOW())
                RETURNING id, question, answer, intent_category, is_augmented, created_at
                """,
                question, answer, intent, is_augmented, vector,
            )
    return dict(row)


async def update_qa(
    ctx: TenantContext,
    qa_id: int,
    question: str | None = None,
    answer: str | None = None,
    intent: str | None = None,
    is_augmented: bool | None = None,
) -> dict[str, Any]:
    if question is None and answer is None and intent is None and is_augmented is None:
        raise QAError("Guncellenecek en az bir alan verilmelidir.")

    col = ctx.similarity_column
    async with ctx.pool.acquire() as conn:
        async with conn.transaction():
            current = await conn.fetchrow(
                """
                SELECT id, question, answer, intent_category, is_augmented
                FROM qa_embeddings WHERE id = $1 FOR UPDATE
                """,
                qa_id,
            )
            if current is None:
                raise QAError(f"Kayit bulunamadi: id={qa_id}")

            new_q = question.strip() if question is not None else current["question"]
            new_a = answer.strip() if answer is not None else current["answer"]
            new_i = intent.strip() if intent is not None else current["intent_category"]
            new_aug = is_augmented if is_augmented is not None else current["is_augmented"]

            if not new_q or not new_a or not new_i:
                raise QAError("question, answer ve intent bos olamaz.")

            if new_q != current["question"]:
                vector = _vec(new_q)
                row = await conn.fetchrow(
                    f"""
                    UPDATE qa_embeddings
                    SET question=$1, answer=$2, intent_category=$3,
                        is_augmented=$4, {col}=$5::vector
                    WHERE id=$6
                    RETURNING id, question, answer, intent_category, is_augmented, created_at
                    """,
                    new_q, new_a, new_i, new_aug, vector, qa_id,
                )
            else:
                row = await conn.fetchrow(
                    """
                    UPDATE qa_embeddings
                    SET answer=$1, intent_category=$2, is_augmented=$3
                    WHERE id=$4
                    RETURNING id, question, answer, intent_category, is_augmented, created_at
                    """,
                    new_a, new_i, new_aug, qa_id,
                )
    return dict(row)


async def delete_qa(ctx: TenantContext, qa_id: int) -> dict[str, Any]:
    async with ctx.pool.acquire() as conn:
        row = await conn.fetchrow(
            "DELETE FROM qa_embeddings WHERE id=$1 RETURNING id, question",
            qa_id,
        )
    if row is None:
        raise QAError(f"Kayit bulunamadi: id={qa_id}")
    return {"deleted": True, "id": row["id"], "question": row["question"]}


async def search_qa(
    ctx: TenantContext,
    query_text: str,
    intent: str | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    query_text = query_text.strip()
    if not query_text:
        raise QAError("Arama metni bos olamaz.")

    col = ctx.similarity_column
    vector = _vec(query_text)
    params: list[Any] = [vector]
    intent_filter = ""
    if intent:
        params.append(intent)
        intent_filter = f"AND intent_category = ${len(params)}"
    params.append(limit)
    limit_idx = len(params)

    sql = f"""
        SELECT id, question, answer, intent_category, is_augmented,
               1 - ({col} <=> $1::vector) AS similarity
        FROM qa_embeddings
        WHERE {col} IS NOT NULL
        {intent_filter}
        ORDER BY {col} <=> $1::vector
        LIMIT ${limit_idx}
    """
    async with ctx.pool.acquire() as conn:
        rows = await conn.fetch(sql, *params)
    return [dict(r) for r in rows]