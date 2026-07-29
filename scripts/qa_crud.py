#!/usr/bin/env python3
"""qa_embeddings tablosu icin CLI CRUD ve benzerlik arama araci.

Ornekler:
    python scripts/qa_crud.py create \
        --question "Büyük Filo ne iş yapar?" \
        --answer "Büyük Filo kurumsal filo kiralama hizmeti sunar." \
        --intent hakkimizda

    python scripts/qa_crud.py list --intent hakkimizda --limit 20
    python scripts/qa_crud.py get --id 1692

    python scripts/qa_crud.py update --id 1692 \
        --question "Büyük Filo hangi hizmetleri sunuyor?" \
        --answer "..." \
        --intent hakkimizda

    python scripts/qa_crud.py delete --id 1692
    python scripts/qa_crud.py search --query "Yolda kaldım" --limit 5
    python scripts/qa_crud.py reembed --all

Notlar:
- BAAI/bge-m3, 1024 boyutlu embedding uretir.
- Veritabanindaki embedding kolonu vector(1024) olmalidir.
- Soru degistiginde embedding otomatik yeniden uretilir.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from contextlib import contextmanager
from typing import Any, Iterator

import psycopg2
from psycopg2.extras import RealDictCursor
from sentence_transformers import SentenceTransformer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import Settings  # noqa: E402


EMBEDDING_MODEL = "BAAI/bge-m3"
EXPECTED_EMBEDDING_DIM = 1024
TABLE_NAME = "qa_embeddings"
EMBEDDING_COLUMN = "embedding_bge_1024"

_env_file = ".env.local" if os.path.exists(".env.local") else ".env"
settings = Settings(_env_file=_env_file)
_model: SentenceTransformer | None = None


def get_model() -> SentenceTransformer:
    """Modeli yalnizca embedding gerektiginde yukler."""
    global _model

    if _model is None:
        print(f"Model yukleniyor: {EMBEDDING_MODEL}", file=sys.stderr)
        _model = SentenceTransformer(EMBEDDING_MODEL)

        dimension = _model.get_sentence_embedding_dimension()
        if dimension != EXPECTED_EMBEDDING_DIM:
            raise RuntimeError(
                f"Beklenmeyen embedding boyutu: {dimension}. "
                f"Beklenen: {EXPECTED_EMBEDDING_DIM}."
            )

    return _model


def create_embedding(text: str) -> list[float]:
    text = text.strip()
    if not text:
        raise ValueError("Embedding uretilecek metin bos olamaz.")

    embedding = get_model().encode(
        text,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return embedding.tolist()


@contextmanager
def db_connection() -> Iterator[Any]:
    conn = psycopg2.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        dbname=settings.postgres_db,
        user=settings.postgres_user,
        password=settings.postgres_password,
    )
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def check_embedding_column_dimension(conn: Any) -> None:
    """BGE embedding kolonunun vector(1024) oldugunu kontrol eder."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT format_type(a.atttypid, a.atttypmod)
            FROM pg_attribute AS a
            JOIN pg_class AS c ON c.oid = a.attrelid
            JOIN pg_namespace AS n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
              AND c.relname = %s
              AND a.attname = %s
              AND a.attnum > 0
              AND NOT a.attisdropped
            """,
            (TABLE_NAME, EMBEDDING_COLUMN),
        )
        row = cur.fetchone()

    if row is None:
        raise RuntimeError(
            f"public.{TABLE_NAME}.{EMBEDDING_COLUMN} kolonu bulunamadi. "
            "Veritabani kolon adini ve migration durumunu kontrol edin."
        )

    column_type = row[0]
    expected_type = f"vector({EXPECTED_EMBEDDING_DIM})"

    if column_type != expected_type:
        raise RuntimeError(
            f"{EMBEDDING_COLUMN} kolonu {column_type}, "
            f"fakat {EMBEDDING_MODEL} icin {expected_type} olmali."
        )


def print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "evet"}:
        return True
    if normalized in {"0", "false", "no", "hayir", "hayır"}:
        return False
    raise argparse.ArgumentTypeError("Deger true veya false olmalidir.")


def create_record(args: argparse.Namespace) -> None:
    question = args.question.strip()
    answer = args.answer.strip()
    intent = args.intent.strip()

    if not question or not answer or not intent:
        raise ValueError("question, answer ve intent bos olamaz.")

    embedding = create_embedding(question)

    with db_connection() as conn:
        check_embedding_column_dimension(conn)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if not args.allow_duplicate:
                cur.execute(
                    f"SELECT id FROM {TABLE_NAME} WHERE question = %s LIMIT 1",
                    (question,),
                )
                duplicate = cur.fetchone()
                if duplicate:
                    raise ValueError(
                        f"Bu soru zaten kayitli. id={duplicate['id']}. "
                        "Guncellemek icin update komutunu kullanin."
                    )

            cur.execute(
                f"""
                INSERT INTO {TABLE_NAME}
                    (
                        question,
                        answer,
                        intent_category,
                        is_augmented,
                        {EMBEDDING_COLUMN},
                        created_at
                    )
                VALUES
                    (%s, %s, %s, %s, %s::vector, NOW())
                RETURNING id, question, answer, intent_category,
                          is_augmented, created_at
                """,
                (
                    question,
                    answer,
                    intent,
                    args.augmented,
                    str(embedding),
                ),
            )
            record = cur.fetchone()

    print_json(record)


def get_record(args: argparse.Namespace) -> None:
    with db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                f"""
                SELECT id, question, answer, intent_category,
                       is_augmented, created_at,
                       {EMBEDDING_COLUMN} IS NOT NULL AS has_embedding
                FROM {TABLE_NAME}
                WHERE id = %s
                """,
                (args.id,),
            )
            record = cur.fetchone()

    if record is None:
        raise LookupError(f"Kayit bulunamadi. id={args.id}")

    print_json(record)


def list_records(args: argparse.Namespace) -> None:
    conditions: list[str] = []
    params: list[Any] = []

    if args.intent:
        conditions.append("intent_category = %s")
        params.append(args.intent.strip())

    if args.augmented is not None:
        conditions.append("is_augmented = %s")
        params.append(args.augmented)

    if args.text:
        conditions.append("(question ILIKE %s OR answer ILIKE %s)")
        pattern = f"%{args.text.strip()}%"
        params.extend([pattern, pattern])

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    params.extend([args.limit, args.offset])

    with db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                f"""
                SELECT id, question, answer, intent_category,
                       is_augmented, created_at,
                       {EMBEDDING_COLUMN} IS NOT NULL AS has_embedding
                FROM {TABLE_NAME}
                {where_clause}
                ORDER BY id DESC
                LIMIT %s OFFSET %s
                """,
                params,
            )
            records = cur.fetchall()

    print_json(records)


def update_record(args: argparse.Namespace) -> None:
    if all(
        value is None
        for value in (args.question, args.answer, args.intent, args.augmented)
    ):
        raise ValueError("Guncellenecek en az bir alan verilmelidir.")

    with db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                f"""
                SELECT id, question, answer, intent_category, is_augmented
                FROM {TABLE_NAME}
                WHERE id = %s
                FOR UPDATE
                """,
                (args.id,),
            )
            current = cur.fetchone()

            if current is None:
                raise LookupError(f"Kayit bulunamadi. id={args.id}")

            new_question = (
                args.question.strip() if args.question is not None else current["question"]
            )
            new_answer = (
                args.answer.strip() if args.answer is not None else current["answer"]
            )
            new_intent = (
                args.intent.strip()
                if args.intent is not None
                else current["intent_category"]
            )
            new_augmented = (
                args.augmented
                if args.augmented is not None
                else current["is_augmented"]
            )

            if not new_question or not new_answer or not new_intent:
                raise ValueError("question, answer ve intent bos olamaz.")

            question_changed = new_question != current["question"]

            if question_changed:
                check_embedding_column_dimension(conn)
                new_embedding = create_embedding(new_question)
                cur.execute(
                    f"""
                    UPDATE {TABLE_NAME}
                    SET question = %s,
                        answer = %s,
                        intent_category = %s,
                        is_augmented = %s,
                        {EMBEDDING_COLUMN} = %s::vector
                    WHERE id = %s
                    RETURNING id, question, answer, intent_category,
                              is_augmented, created_at
                    """,
                    (
                        new_question,
                        new_answer,
                        new_intent,
                        new_augmented,
                        str(new_embedding),
                        args.id,
                    ),
                )
            else:
                cur.execute(
                    f"""
                    UPDATE {TABLE_NAME}
                    SET answer = %s,
                        intent_category = %s,
                        is_augmented = %s
                    WHERE id = %s
                    RETURNING id, question, answer, intent_category,
                              is_augmented, created_at
                    """,
                    (new_answer, new_intent, new_augmented, args.id),
                )

            record = cur.fetchone()

    print_json(record)


def delete_record(args: argparse.Namespace) -> None:
    with db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                f"""
                DELETE FROM {TABLE_NAME}
                WHERE id = %s
                RETURNING id, question
                """,
                (args.id,),
            )
            deleted = cur.fetchone()

    if deleted is None:
        raise LookupError(f"Kayit bulunamadi. id={args.id}")

    print_json({"deleted": True, "record": deleted})


def search_records(args: argparse.Namespace) -> None:
    query_embedding = create_embedding(args.query)

    with db_connection() as conn:
        check_embedding_column_dimension(conn)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            params: list[Any] = [str(query_embedding)]
            intent_filter = ""

            if args.intent:
                intent_filter = "AND intent_category = %s"
                params.append(args.intent.strip())

            params.append(args.limit)

            cur.execute(
                f"""
                SELECT id,
                    question,
                    answer,
                    intent_category,
                    is_augmented,
                    1 - ({EMBEDDING_COLUMN} <=> %s::vector) AS similarity
                FROM {TABLE_NAME}
                WHERE {EMBEDDING_COLUMN} IS NOT NULL
                {intent_filter}
                ORDER BY {EMBEDDING_COLUMN} <=> %s::vector
                LIMIT %s
                """,
                [*params[:-1], str(query_embedding), params[-1]]
                if args.intent
                else [
                    str(query_embedding),
                    str(query_embedding),
                    args.limit,
                ],
            )
            records = cur.fetchall()

    print_json(records)


def reembed_records(args: argparse.Namespace) -> None:
    if not args.all and args.id is None:
        raise ValueError("reembed icin --all veya --id verilmelidir.")

    with db_connection() as conn:
        check_embedding_column_dimension(conn)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if args.all:
                cur.execute(
                    f"SELECT id, question FROM {TABLE_NAME} ORDER BY id"
                )
            else:
                cur.execute(
                    f"SELECT id, question FROM {TABLE_NAME} WHERE id = %s",
                    (args.id,),
                )

            records = cur.fetchall()
            if not records:
                raise LookupError("Yeniden vektorlestirilecek kayit bulunamadi.")

            questions = [record["question"] for record in records]
            embeddings = get_model().encode(
                questions,
                normalize_embeddings=True,
                show_progress_bar=True,
                batch_size=args.batch_size,
            )

            for record, embedding in zip(records, embeddings, strict=True):
                cur.execute(
                    f"""
                    UPDATE {TABLE_NAME}
                    SET {EMBEDDING_COLUMN} = %s::vector
                    WHERE id = %s
                    """,
                    (
                        str(embedding.tolist()),
                        record["id"],
                    ),
                )

    print_json({"reembedded": len(records), "model": EMBEDDING_MODEL})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="qa_embeddings CRUD ve vektor arama araci"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create", help="Yeni Q&A kaydi ekle")
    create_parser.add_argument("--question", required=True)
    create_parser.add_argument("--answer", required=True)
    create_parser.add_argument("--intent", required=True)
    create_parser.add_argument("--augmented", action="store_true")
    create_parser.add_argument("--allow-duplicate", action="store_true")
    create_parser.set_defaults(handler=create_record)

    get_parser = subparsers.add_parser("get", help="ID ile kayit getir")
    get_parser.add_argument("--id", type=int, required=True)
    get_parser.set_defaults(handler=get_record)

    list_parser = subparsers.add_parser("list", help="Kayitlari listele")
    list_parser.add_argument("--intent")
    list_parser.add_argument("--augmented", type=parse_bool)
    list_parser.add_argument("--text", help="Soru veya cevap icinde metin ara")
    list_parser.add_argument("--limit", type=int, default=50)
    list_parser.add_argument("--offset", type=int, default=0)
    list_parser.set_defaults(handler=list_records)

    update_parser = subparsers.add_parser("update", help="Kayit guncelle")
    update_parser.add_argument("--id", type=int, required=True)
    update_parser.add_argument("--question")
    update_parser.add_argument("--answer")
    update_parser.add_argument("--intent")
    update_parser.add_argument("--augmented", type=parse_bool)
    update_parser.set_defaults(handler=update_record)

    delete_parser = subparsers.add_parser("delete", help="Kayit sil")
    delete_parser.add_argument("--id", type=int, required=True)
    delete_parser.set_defaults(handler=delete_record)

    search_parser = subparsers.add_parser(
        "search", help="Cosine benzerligi ile semantik arama"
    )
    search_parser.add_argument("--query", required=True)
    search_parser.add_argument("--intent")
    search_parser.add_argument("--limit", type=int, default=5)
    search_parser.set_defaults(handler=search_records)

    reembed_parser = subparsers.add_parser(
        "reembed", help="Mevcut kayitlarin embeddinglerini yeniden uret"
    )
    target = reembed_parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--all", action="store_true")
    target.add_argument("--id", type=int)
    reembed_parser.add_argument("--batch-size", type=int, default=32)
    reembed_parser.set_defaults(handler=reembed_records)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if hasattr(args, "limit") and args.limit <= 0:
        parser.error("--limit 0'dan buyuk olmalidir.")
    if hasattr(args, "offset") and args.offset < 0:
        parser.error("--offset negatif olamaz.")
    if hasattr(args, "batch_size") and args.batch_size <= 0:
        parser.error("--batch-size 0'dan buyuk olmalidir.")

    try:
        args.handler(args)
        return 0
    except (ValueError, LookupError, RuntimeError) as exc:
        print(f"Hata: {exc}", file=sys.stderr)
        return 1
    except psycopg2.Error as exc:
        print(f"Veritabani hatasi: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())