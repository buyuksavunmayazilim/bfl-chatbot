"""Admin panel kimlik dogrulama + yetkilendirme (RBAC) — e-posta tabanli.

Bagimsiz (SSO yok): e-posta/sifre veritabaninda tutulur.
  - Sifre: pbkdf2_sha256 (stdlib hashlib) — ek bagimlilik yok.
  - Oturum: HS256 JWT (stdlib hmac) — ek bagimlilik yok.

Tablolar KAYIT veritabanindadir (settings.postgres_db), tenant'lardan bagimsiz:
  admin_users(id, email, password_hash, display_name, role, is_active, created_at)
  admin_user_tenants(user_id, tenant_id)          -- manager'in yonetebildigi chatbot'lar

Roller:
  super_admin -> tum chatbot'lar + yeni chatbot + kullanici yonetimi
  manager     -> yalnizca kendisine atanan chatbot'lar; olusturma/kullanici yok
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time

import psycopg2
from fastapi import Depends, Header, HTTPException, Request

from app.core.config import settings

ROLE_SUPER = "super_admin"
ROLE_MANAGER = "manager"
_VALID_ROLES = {ROLE_SUPER, ROLE_MANAGER}


# ─── Kayit DB baglantisi ──────────────────────────────────────────────────────
def _connect():
    return psycopg2.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        dbname=settings.postgres_db,
        user=settings.postgres_user,
        password=settings.postgres_password,
    )


# ─── Sifre (pbkdf2_sha256) ────────────────────────────────────────────────────
def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _ub64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def hash_password(pw: str, iterations: int = 200_000) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, iterations)
    return f"pbkdf2_sha256${iterations}${_b64(salt)}${_b64(dk)}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        algo, iters, salt_b, hash_b = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), _ub64(salt_b), int(iters))
        return hmac.compare_digest(_b64(dk), hash_b)
    except Exception:
        return False


# ─── JWT (HS256) ──────────────────────────────────────────────────────────────
def _secret() -> str:
    return settings.admin_secret


def make_token(uid: int, role: str, ttl: int | None = None) -> str:
    ttl = ttl or settings.admin_token_ttl
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"uid": uid, "role": role, "iat": now, "exp": now + ttl}
    seg = (
        _b64(json.dumps(header, separators=(",", ":")).encode())
        + "."
        + _b64(json.dumps(payload, separators=(",", ":")).encode())
    )
    sig = _b64(hmac.new(_secret().encode(), seg.encode(), hashlib.sha256).digest())
    return seg + "." + sig


def decode_token(token: str) -> dict | None:
    try:
        seg, sig = token.rsplit(".", 1)
        expected = _b64(hmac.new(_secret().encode(), seg.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(_ub64(seg.split(".", 1)[1]))
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        return payload
    except Exception:
        return None


def _norm_email(email: str) -> str:
    return (email or "").strip().lower()


# ─── Tablolar + goc + ilk super admin ─────────────────────────────────────────
def ensure_admin_tables() -> None:
    """Tablolari olusturur, eski 'username' semasini e-postaya tasir ve ilk super admin'i seed'ler."""
    conn = _connect()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS admin_users (
                    id            SERIAL PRIMARY KEY,
                    email         TEXT UNIQUE,
                    password_hash TEXT NOT NULL,
                    display_name  TEXT,
                    role          TEXT NOT NULL DEFAULT 'manager',
                    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS admin_user_tenants (
                    user_id   INTEGER NOT NULL REFERENCES admin_users(id) ON DELETE CASCADE,
                    tenant_id TEXT NOT NULL,
                    PRIMARY KEY (user_id, tenant_id)
                )
                """
            )
            # --- Eski 'username' semasindan goc ---
            cur.execute("ALTER TABLE admin_users ADD COLUMN IF NOT EXISTS email TEXT")
            cur.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'admin_users'"
            )
            cols = {r[0] for r in cur.fetchall()}
            if "username" in cols:
                cur.execute("UPDATE admin_users SET email = username WHERE email IS NULL")
                cur.execute("ALTER TABLE admin_users ALTER COLUMN username DROP NOT NULL")
            # Bos email guvenligi + benzersiz index
            cur.execute("UPDATE admin_users SET email = 'user' || id::text WHERE email IS NULL")
            cur.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS admin_users_email_uidx ON admin_users (email)"
            )
            # Eski tek super admin'in girisini, ayarlanan ADMIN_EMAIL'e yukselt
            cfg_email = _norm_email(settings.admin_email)
            if cfg_email:
                cur.execute(
                    "SELECT id, email FROM admin_users WHERE role = %s ORDER BY id", (ROLE_SUPER,)
                )
                supers = cur.fetchall()
                if len(supers) == 1 and "@" not in (supers[0][1] or ""):
                    cur.execute(
                        "UPDATE admin_users SET email = %s WHERE id = %s", (cfg_email, supers[0][0])
                    )
                    print(f"[admin_auth] mevcut super admin e-postasi guncellendi: {cfg_email}")

            # Hic super admin yoksa env'den olustur
            cur.execute("SELECT COUNT(*) FROM admin_users WHERE role = %s", (ROLE_SUPER,))
            if cur.fetchone()[0] == 0:
                email = cfg_email or _norm_email(settings.admin_user if "@" in (settings.admin_user or "") else "")
                if not email:
                    email = "admin@buyukfilo.local"
                pw = settings.admin_pass or "admin123"
                cur.execute(
                    """
                    INSERT INTO admin_users (email, password_hash, display_name, role)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (email) DO NOTHING
                    """,
                    (email, hash_password(pw), "Süper Admin", ROLE_SUPER),
                )
                if not settings.admin_pass:
                    print(
                        f"[admin_auth] UYARI: ilk super admin '{email}' varsayilan sifre "
                        "'admin123' ile olusturuldu. ADMIN_PASS env ile degistirin!"
                    )
                else:
                    print(f"[admin_auth] ilk super admin olusturuldu: {email}")
    finally:
        conn.close()


# ─── Kullanici sorgulari ──────────────────────────────────────────────────────
def _user_row(row) -> dict:
    return {
        "id": row[0], "email": row[1], "display_name": row[2],
        "role": row[3], "is_active": row[4],
    }


def get_user_by_email(email: str) -> dict | None:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, email, display_name, role, is_active, password_hash "
                "FROM admin_users WHERE email = %s",
                (_norm_email(email),),
            )
            r = cur.fetchone()
            if not r:
                return None
            d = _user_row(r)
            d["password_hash"] = r[5]
            return d
    finally:
        conn.close()


def get_user_by_id(uid: int) -> dict | None:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, email, display_name, role, is_active FROM admin_users WHERE id = %s",
                (uid,),
            )
            r = cur.fetchone()
            return _user_row(r) if r else None
    finally:
        conn.close()


def list_user_tenant_ids(uid: int) -> list[str]:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT tenant_id FROM admin_user_tenants WHERE user_id = %s", (uid,))
            return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()


def authenticate(email: str, password: str) -> dict | None:
    u = get_user_by_email(email)
    if not u or not u["is_active"]:
        return None
    if not verify_password(password, u["password_hash"]):
        return None
    u.pop("password_hash", None)
    return u


# ─── Kullanici yonetimi (super admin) ─────────────────────────────────────────
def list_users() -> list[dict]:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, email, display_name, role, is_active FROM admin_users ORDER BY id"
            )
            users = [_user_row(r) for r in cur.fetchall()]
            cur.execute("SELECT user_id, tenant_id FROM admin_user_tenants")
            by_user: dict[int, list[str]] = {}
            for uid, tid in cur.fetchall():
                by_user.setdefault(uid, []).append(tid)
            for u in users:
                u["tenant_ids"] = sorted(by_user.get(u["id"], []))
            return users
    finally:
        conn.close()


def _set_user_tenants(cur, uid: int, tenant_ids: list[str]) -> None:
    cur.execute("DELETE FROM admin_user_tenants WHERE user_id = %s", (uid,))
    for tid in sorted(set(t.strip() for t in tenant_ids if t and t.strip())):
        cur.execute(
            "INSERT INTO admin_user_tenants (user_id, tenant_id) VALUES (%s, %s) "
            "ON CONFLICT DO NOTHING",
            (uid, tid),
        )


def create_user(email: str, password: str, display_name: str, role: str,
                tenant_ids: list[str]) -> dict:
    email = _norm_email(email)
    if not email or "@" not in email:
        raise ValueError("Geçerli bir e-posta adresi girin.")
    if not password:
        raise ValueError("Şifre zorunlu.")
    if role not in _VALID_ROLES:
        raise ValueError("Geçersiz rol.")
    conn = _connect()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT 1 FROM admin_users WHERE email = %s", (email,))
            if cur.fetchone():
                raise ValueError(f"Bu e-posta zaten kayıtlı: {email}")
            cur.execute(
                "INSERT INTO admin_users (email, password_hash, display_name, role) "
                "VALUES (%s, %s, %s, %s) RETURNING id",
                (email, hash_password(password), display_name.strip() or email, role),
            )
            uid = cur.fetchone()[0]
            if role == ROLE_MANAGER:
                _set_user_tenants(cur, uid, tenant_ids)
    finally:
        conn.close()
    return {"id": uid, "email": email, "role": role}


def update_user(uid: int, *, display_name: str | None = None, role: str | None = None,
                password: str | None = None, is_active: bool | None = None,
                tenant_ids: list[str] | None = None) -> dict:
    conn = _connect()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT role FROM admin_users WHERE id = %s", (uid,))
            cur_row = cur.fetchone()
            if not cur_row:
                raise ValueError("Kullanıcı bulunamadı.")
            sets, args = [], []
            if display_name is not None:
                sets.append("display_name = %s"); args.append(display_name.strip())
            if role is not None:
                if role not in _VALID_ROLES:
                    raise ValueError("Geçersiz rol.")
                sets.append("role = %s"); args.append(role)
            if password:
                sets.append("password_hash = %s"); args.append(hash_password(password))
            if is_active is not None:
                sets.append("is_active = %s"); args.append(is_active)
            if sets:
                args.append(uid)
                cur.execute(f"UPDATE admin_users SET {', '.join(sets)} WHERE id = %s", args)
            eff_role = role if role is not None else cur_row[0]
            if tenant_ids is not None:
                if eff_role == ROLE_SUPER:
                    cur.execute("DELETE FROM admin_user_tenants WHERE user_id = %s", (uid,))
                else:
                    _set_user_tenants(cur, uid, tenant_ids)
    finally:
        conn.close()
    return {"id": uid}


def delete_user(uid: int) -> dict:
    conn = _connect()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT role FROM admin_users WHERE id = %s", (uid,))
            r = cur.fetchone()
            if not r:
                raise ValueError("Kullanıcı bulunamadı.")
            if r[0] == ROLE_SUPER:
                cur.execute("SELECT COUNT(*) FROM admin_users WHERE role = %s", (ROLE_SUPER,))
                if cur.fetchone()[0] <= 1:
                    raise ValueError("Son süper admin silinemez.")
            cur.execute("DELETE FROM admin_users WHERE id = %s", (uid,))
    finally:
        conn.close()
    return {"deleted": uid}


# ─── FastAPI bagimliliklari ───────────────────────────────────────────────────
def get_current_user(authorization: str | None = Header(None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Oturum gerekli.")
    payload = decode_token(authorization.split(" ", 1)[1].strip())
    if not payload:
        raise HTTPException(status_code=401, detail="Oturum geçersiz veya süresi dolmuş.")
    user = get_user_by_id(int(payload["uid"]))
    if not user or not user["is_active"]:
        raise HTTPException(status_code=401, detail="Kullanıcı pasif veya bulunamadı.")
    user["tenant_ids"] = list_user_tenant_ids(user["id"]) if user["role"] == ROLE_MANAGER else []
    return user


def require_super_admin(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != ROLE_SUPER:
        raise HTTPException(status_code=403, detail="Bu işlem için süper admin yetkisi gerekir.")
    return user


def tenant_guard(request: Request, user: dict = Depends(get_current_user)) -> dict:
    """URL'de {tenant} varsa, manager yalnizca kendi chatbot'larina erisebilir."""
    tenant = request.path_params.get("tenant")
    if tenant and user["role"] != ROLE_SUPER and tenant not in user["tenant_ids"]:
        raise HTTPException(status_code=403, detail="Bu chatbot için yetkiniz yok.")
    return user
