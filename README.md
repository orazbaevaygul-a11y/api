# 💳 To'lov API — Railway + FastAPI + PostgreSQL

## 📁 Fayllar

| Fayl | Vazifasi |
|------|----------|
| `main.py` | Asosiy API server |
| `pay_client.py` | Bot ichida ishlatish uchun helper |
| `requirements.txt` | Kutubxonalar |
| `Procfile` | Railway start komandasi |
| `.env.example` | Environment variables namunasi |

---

## 🚀 Railway ga deploy qilish

### 1. GitHub repozitoriy yarating
```bash
git init
git add .
git commit -m "To'lov API"
git remote add origin https://github.com/SIZMNIKI/pay-api.git
git push -u origin main
```

### 2. Railway da yangi loyiha
1. https://railway.app ga kiring
2. **New Project → Deploy from GitHub repo** tanlang
3. Repozitoriyni tanlang

### 3. PostgreSQL qo'shing
1. Railway loyihada **+ New** → **Database → PostgreSQL**
2. DATABASE_URL avtomatik qo'shiladi

### 4. Environment Variables
Railway loyihada **Variables** bo'limiga qo'shing:
```
ADMIN_API_KEY = kuchli_admin_parol_kamida_32_belgi
BOT_API_KEY   = kuchli_bot_parol_kamida_32_belgi
```
`DATABASE_URL` PostgreSQL qo'shilganda avtomatik bo'ladi.

### 5. Deploy
Variables saqlanganidan keyin Railway avtomatik deploy qiladi.

---

## 🔌 Bot ga ulash

`bot.py` yoniga `pay_client.py` ni qo'ying va `.env` ga qo'shing:
```env
PAY_API_BASE = https://your-app.up.railway.app
BOT_API_KEY  = kuchli_bot_parol_kamida_32_belgi
ADMIN_API_KEY= kuchli_admin_parol_kamida_32_belgi
```

Bot ichida:
```python
from pay_client import pay_create, pay_check, pay_confirm, pay_cancel_order

# To'lov yaratish
result = await pay_create(user_id=123456789, amount=5000, fullname="Ali Valiyev")
order_id = result["order"]  # "ABC1234567890123"

# Holatni tekshirish (polling)
status = await pay_check(order_id)  # "pending" | "paid" | "cancel"

# Admin tasdiqlash (qo'lda to'lov uchun)
await pay_confirm(order_id, note="Tasdiqlandi")

# Bekor qilish
await pay_cancel_order(order_id, note="Noto'g'ri summa")
```

---

## 📡 API Endpointlar

| Method | URL | Tavsif | Key |
|--------|-----|--------|-----|
| GET | `/` | Sog'liq tekshiruvi | - |
| GET | `/health` | DB tekshiruvi | - |
| POST | `/create` | To'lov yaratish | BOT_API_KEY |
| GET | `/check?order=ID` | Holat tekshirish | BOT_API_KEY |
| POST | `/confirm` | Tasdiqlash | ADMIN_API_KEY |
| POST | `/cancel` | Bekor qilish | ADMIN_API_KEY |
| GET | `/list` | Ro'yxat | ADMIN_API_KEY |
| GET | `/stats` | Statistika | ADMIN_API_KEY |

---

## 📊 To'lov holatlari

```
pending  →  paid    (tasdiqlandi)
pending  →  cancel  (bekor qilindi)
```

---

## 🔒 Xavfsizlik maslahatlar

- API keylarni kamida 32 belgi qiling
- `ADMIN_API_KEY` ni faqat admin bot handler ichida ishlating
- `BOT_API_KEY` faqat `/create` va `/check` uchun yetarli
