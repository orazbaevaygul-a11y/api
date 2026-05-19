"""
To'lov API — FastAPI + PostgreSQL (Railway)
==========================================
Endpointlar:
  POST /create   — yangi to'lov yaratish
  GET  /check    — to'lov holatini tekshirish
  POST /confirm  — admin to'lovni tasdiqlash (qo'lda)
  POST /cancel   — admin to'lovni bekor qilish
  GET  /list     — barcha to'lovlar ro'yxati (admin)
  GET  /stats    — statistika (admin)
"""

import os
import uuid
import hashlib
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Request, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import asyncpg
from contextlib import asynccontextmanager

# ─── SOZLAMALAR ───────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost/paydb")
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "admin-secret-key-change-me")
# Bot o'zi ishlatadigan key (to'lov yaratish/tekshirish uchun)
BOT_API_KEY = os.getenv("BOT_API_KEY", "bot-secret-key-change-me")

# ─── DB POOL ──────────────────────────────────────────────────
db_pool: asyncpg.Pool = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    await init_db()
    print("✅ DB ulandi va jadvallar yaratildi")
    yield
    await db_pool.close()

app = FastAPI(
    title="To'lov API",
    description="Telegram bot uchun to'lov API",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── DB INIT ──────────────────────────────────────────────────
async def init_db():
    async with db_pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id          SERIAL PRIMARY KEY,
                order_id    TEXT UNIQUE NOT NULL,
                user_id     BIGINT NOT NULL,
                fullname    TEXT NOT NULL DEFAULT '',
                amount      INTEGER NOT NULL,
                status      TEXT NOT NULL DEFAULT 'pending',
                note        TEXT DEFAULT '',
                created_at  TIMESTAMPTZ DEFAULT NOW(),
                updated_at  TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_payments_order_id ON payments(order_id);
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_payments_user_id ON payments(user_id);
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status);
        """)

# ─── AUTH YORDAMCHILARI ───────────────────────────────────────
def verify_bot_key(api_key: str = Query(..., alias="api_key")):
    """Bot API key tekshirish"""
    if api_key not in (BOT_API_KEY, ADMIN_API_KEY):
        raise HTTPException(status_code=401, detail="Noto'g'ri API key")
    return api_key

def verify_admin_key(api_key: str = Query(..., alias="api_key")):
    """Faqat admin API key tekshirish"""
    if api_key != ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Admin huquqi talab etiladi")
    return api_key

def generate_order_id() -> str:
    """Unikal order ID yaratish"""
    return str(uuid.uuid4()).replace("-", "")[:16].upper()

# ═══════════════════════════════════════════════════════════════
#  ENDPOINTLAR
# ═══════════════════════════════════════════════════════════════

@app.get("/")
async def root():
    return {"status": "ok", "message": "To'lov API ishlamoqda ✅"}

@app.get("/health")
async def health():
    try:
        async with db_pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return {"status": "ok", "db": "connected"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "db": str(e)})


# ─── 1. TO'LOV YARATISH ───────────────────────────────────────
@app.post("/create")
async def create_payment(
    request: Request,
    api_key: str = Depends(verify_bot_key)
):
    """
    Yangi to'lov yaratadi.

    Body (form-data yoki JSON):
      user_id  : int   — Telegram user ID
      amount   : int   — So'm (1000 dan yuqori)
      fullname : str   — Foydalanuvchi ismi (ixtiyoriy)

    Qaytaradi:
      { "status": "success", "order": "ORDER_ID", "insert_id": 123, "amount": 5000 }
    """
    # Form-data yoki JSON qabul qilish
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        body = await request.json()
    else:
        form = await request.form()
        body = dict(form)

    # Validatsiya
    try:
        user_id = int(body.get("user_id", 0))
        amount  = int(body.get("amount", 0))
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="user_id va amount raqam bo'lishi kerak")

    if user_id <= 0:
        raise HTTPException(status_code=400, detail="Noto'g'ri user_id")
    if amount < 1000:
        raise HTTPException(status_code=400, detail="Minimal summa 1000 so'm")
    if amount > 10_000_000:
        raise HTTPException(status_code=400, detail="Maksimal summa 10,000,000 so'm")

    fullname = str(body.get("fullname", "")).strip()[:100]

    order_id = generate_order_id()

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO payments (order_id, user_id, fullname, amount, status)
            VALUES ($1, $2, $3, $4, 'pending')
            RETURNING id, order_id, amount
        """, order_id, user_id, fullname, amount)

    return {
        "status": "success",
        "order": row["order_id"],
        "insert_id": row["id"],
        "amount": row["amount"]
    }


# ─── 2. TO'LOV TEKSHIRISH ─────────────────────────────────────
@app.get("/check")
async def check_payment(
    order: str = Query(..., description="Order ID"),
    api_key: str = Depends(verify_bot_key)
):
    """
    To'lov holatini qaytaradi.

    Qaytaradi:
      { "status": "success", "data": { "status": "pending|paid|cancel", ... } }
    """
    if not order or len(order) < 4:
        raise HTTPException(status_code=400, detail="Noto'g'ri order ID")

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT id, order_id, user_id, fullname, amount, status, note, created_at, updated_at
            FROM payments WHERE order_id = $1
        """, order.upper())

    if not row:
        return JSONResponse(
            status_code=404,
            content={"status": "error", "message": "To'lov topilmadi"}
        )

    return {
        "status": "success",
        "data": {
            "status":     row["status"],
            "order_id":   row["order_id"],
            "user_id":    row["user_id"],
            "fullname":   row["fullname"],
            "amount":     row["amount"],
            "note":       row["note"] or "",
            "created_at": row["created_at"].isoformat(),
            "updated_at": row["updated_at"].isoformat(),
        }
    }


# ─── 3. TO'LOVNI TASDIQLASH (ADMIN / QO'LDA) ─────────────────
@app.post("/confirm")
async def confirm_payment(
    request: Request,
    api_key: str = Depends(verify_admin_key)
):
    """
    Admin to'lovni qo'lda tasdiqlaydi → status = 'paid'

    Body:
      order : str  — Order ID
      note  : str  — Izoh (ixtiyoriy)
    """
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        body = await request.json()
    else:
        form = await request.form()
        body = dict(form)

    order = str(body.get("order", "")).strip().upper()
    note  = str(body.get("note", "")).strip()[:200]

    if not order:
        raise HTTPException(status_code=400, detail="order maydoni bo'sh")

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, status, user_id, amount FROM payments WHERE order_id = $1",
            order
        )
        if not row:
            raise HTTPException(status_code=404, detail="To'lov topilmadi")
        if row["status"] == "paid":
            raise HTTPException(status_code=400, detail="To'lov allaqachon tasdiqlangan")
        if row["status"] == "cancel":
            raise HTTPException(status_code=400, detail="Bekor qilingan to'lovni tasdiqlash mumkin emas")

        updated = await conn.fetchrow("""
            UPDATE payments
            SET status = 'paid', note = $1, updated_at = NOW()
            WHERE order_id = $2
            RETURNING id, order_id, user_id, amount, status
        """, note, order)

    return {
        "status":   "success",
        "message":  "To'lov tasdiqlandi",
        "order_id": updated["order_id"],
        "user_id":  updated["user_id"],
        "amount":   updated["amount"],
    }


# ─── 4. TO'LOVNI BEKOR QILISH (ADMIN) ────────────────────────
@app.post("/cancel")
async def cancel_payment(
    request: Request,
    api_key: str = Depends(verify_admin_key)
):
    """
    Admin to'lovni bekor qiladi → status = 'cancel'

    Body:
      order : str  — Order ID
      note  : str  — Sabab (ixtiyoriy)
    """
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        body = await request.json()
    else:
        form = await request.form()
        body = dict(form)

    order = str(body.get("order", "")).strip().upper()
    note  = str(body.get("note", "Bekor qilindi")).strip()[:200]

    if not order:
        raise HTTPException(status_code=400, detail="order maydoni bo'sh")

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, status FROM payments WHERE order_id = $1", order
        )
        if not row:
            raise HTTPException(status_code=404, detail="To'lov topilmadi")
        if row["status"] in ("paid", "cancel"):
            raise HTTPException(status_code=400, detail=f"To'lov holati allaqachon: {row['status']}")

        updated = await conn.fetchrow("""
            UPDATE payments
            SET status = 'cancel', note = $1, updated_at = NOW()
            WHERE order_id = $2
            RETURNING order_id, user_id, amount
        """, note, order)

    return {
        "status":   "success",
        "message":  "To'lov bekor qilindi",
        "order_id": updated["order_id"],
        "user_id":  updated["user_id"],
        "amount":   updated["amount"],
    }


# ─── 5. BARCHA TO'LOVLAR RO'YXATI (ADMIN) ────────────────────
@app.get("/list")
async def list_payments(
    status: Optional[str] = Query(None, description="pending|paid|cancel"),
    user_id: Optional[int] = Query(None, description="Foydalanuvchi ID"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    api_key: str = Depends(verify_admin_key)
):
    """
    To'lovlar ro'yxati. Admin uchun.
    """
    conditions = []
    params = []
    idx = 1

    if status:
        if status not in ("pending", "paid", "cancel"):
            raise HTTPException(status_code=400, detail="status: pending|paid|cancel")
        conditions.append(f"status = ${idx}")
        params.append(status)
        idx += 1

    if user_id:
        conditions.append(f"user_id = ${idx}")
        params.append(user_id)
        idx += 1

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.extend([limit, offset])

    async with db_pool.acquire() as conn:
        rows = await conn.fetch(f"""
            SELECT id, order_id, user_id, fullname, amount, status, note, created_at
            FROM payments
            {where}
            ORDER BY created_at DESC
            LIMIT ${idx} OFFSET ${idx+1}
        """, *params)

        total = await conn.fetchval(f"SELECT COUNT(*) FROM payments {where}", *params[:-2])

    return {
        "status": "success",
        "total":  total,
        "limit":  limit,
        "offset": offset,
        "data": [
            {
                "id":         r["id"],
                "order_id":   r["order_id"],
                "user_id":    r["user_id"],
                "fullname":   r["fullname"],
                "amount":     r["amount"],
                "status":     r["status"],
                "note":       r["note"] or "",
                "created_at": r["created_at"].isoformat(),
            }
            for r in rows
        ]
    }


# ─── 6. STATISTIKA (ADMIN) ────────────────────────────────────
@app.get("/stats")
async def stats(api_key: str = Depends(verify_admin_key)):
    """
    Umumiy statistika.
    """
    async with db_pool.acquire() as conn:
        total_all    = await conn.fetchval("SELECT COUNT(*) FROM payments")
        total_paid   = await conn.fetchval("SELECT COUNT(*) FROM payments WHERE status='paid'")
        total_pending= await conn.fetchval("SELECT COUNT(*) FROM payments WHERE status='pending'")
        total_cancel = await conn.fetchval("SELECT COUNT(*) FROM payments WHERE status='cancel'")
        revenue      = await conn.fetchval("SELECT COALESCE(SUM(amount),0) FROM payments WHERE status='paid'")
        today_rev    = await conn.fetchval("""
            SELECT COALESCE(SUM(amount),0) FROM payments
            WHERE status='paid' AND created_at::date = CURRENT_DATE
        """)
        today_count  = await conn.fetchval("""
            SELECT COUNT(*) FROM payments WHERE created_at::date = CURRENT_DATE
        """)

    return {
        "status": "success",
        "data": {
            "total_payments":   total_all,
            "paid":             total_paid,
            "pending":          total_pending,
            "cancelled":        total_cancel,
            "total_revenue":    revenue,
            "today_revenue":    today_rev,
            "today_payments":   today_count,
        }
    }
