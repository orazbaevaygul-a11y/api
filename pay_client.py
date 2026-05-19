"""
pay_client.py — Botdan API ga murojaat qilish uchun tayyor modul
================================================================
Bot ichida shu faylni import qiling:
    from pay_client import pay_create, pay_check, pay_confirm, pay_cancel
"""

import os
import aiohttp
import asyncio
import json

# ─── SOZLAMALAR ───────────────────────────────────────────────
PAY_API_BASE = os.getenv("PAY_API_BASE", "https://your-app.railway.app")
BOT_API_KEY  = os.getenv("BOT_API_KEY",  "bot-secret-key-change-me")
ADMIN_API_KEY= os.getenv("ADMIN_API_KEY","admin-secret-key-change-me")

TIMEOUT = aiohttp.ClientTimeout(total=15)


async def _post(path: str, data: dict, api_key: str) -> dict:
    url = f"{PAY_API_BASE}{path}?api_key={api_key}"
    try:
        async with aiohttp.ClientSession(timeout=TIMEOUT) as s:
            async with s.post(url, data=data) as r:
                raw = await r.text()
        if not raw.strip():
            return {"status": "error", "message": "Server bo'sh javob qaytardi"}
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"status": "error", "message": f"JSON xato: {raw[:80]}"}
    except aiohttp.ClientConnectorError:
        return {"status": "error", "message": "Serverga ulanib bo'lmadi"}
    except asyncio.TimeoutError:
        return {"status": "error", "message": "Server vaqt tugadi (timeout)"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def _get(path: str, params: dict, api_key: str) -> dict:
    params["api_key"] = api_key
    url = f"{PAY_API_BASE}{path}"
    try:
        async with aiohttp.ClientSession(timeout=TIMEOUT) as s:
            async with s.get(url, params=params) as r:
                raw = await r.text()
        if not raw.strip():
            return {"status": "error", "message": "Server bo'sh javob qaytardi"}
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"status": "error", "message": f"JSON xato: {raw[:80]}"}
    except aiohttp.ClientConnectorError:
        return {"status": "error", "message": "Serverga ulanib bo'lmadi"}
    except asyncio.TimeoutError:
        return {"status": "error", "message": "Timeout"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ─── OCHIQ FUNKSIYALAR ─────────────────────────────────────────

async def pay_create(user_id: int, amount: int, fullname: str = "") -> dict:
    """
    Yangi to'lov yaratadi.
    Muvaffaqiyatli: {"status":"success","order":"ABC123","insert_id":1,"amount":5000}
    Xato:           {"status":"error","message":"..."}
    """
    result = await _post("/create", {
        "user_id":  str(user_id),
        "amount":   str(amount),
        "fullname": fullname,
    }, BOT_API_KEY)
    return result


async def pay_check(order_id: str) -> str:
    """
    To'lov holatini qaytaradi: 'paid' | 'pending' | 'cancel' | 'error'
    """
    result = await _get("/check", {"order": order_id}, BOT_API_KEY)
    if result.get("status") != "success":
        return "error"
    return result.get("data", {}).get("status", "error")


async def pay_confirm(order_id: str, note: str = "") -> dict:
    """
    Admin: to'lovni qo'lda tasdiqlash.
    """
    return await _post("/confirm", {"order": order_id, "note": note}, ADMIN_API_KEY)


async def pay_cancel_order(order_id: str, note: str = "Bekor qilindi") -> dict:
    """
    Admin: to'lovni bekor qilish.
    """
    return await _post("/cancel", {"order": order_id, "note": note}, ADMIN_API_KEY)


async def pay_list(status: str = None, limit: int = 50) -> dict:
    """
    Admin: to'lovlar ro'yxatini olish.
    status = 'pending' | 'paid' | 'cancel' | None (hammasi)
    """
    params = {"limit": str(limit)}
    if status:
        params["status"] = status
    return await _get("/list", params, ADMIN_API_KEY)


async def pay_stats() -> dict:
    """
    Admin: statistika.
    """
    return await _get("/stats", {}, ADMIN_API_KEY)
