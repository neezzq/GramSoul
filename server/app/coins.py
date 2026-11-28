"""Coins for generation (a scene picture, an AI avatar) and purchases: coin packs and Elite.

Payments go through YooKassa once YOOKASSA_SHOP_ID and YOOKASSA_SECRET_KEY are set (deploy/.env). Until then a stub
creates the payment and leaves it pending: nothing is charged and nothing is credited. Only with
PAYMENTS_TEST_MODE=on (tests) can the stub "pay" a payment at once. The owner can grant coins and Elite on the admin
page. Prices are preliminary."""
from __future__ import annotations

import logging
import uuid

import httpx
from pydantic import BaseModel, Field

from .common import ApiError, User, new_id
from .config import settings
from .db import Database, now_ms

log = logging.getLogger("fonar.coins")


def products() -> list[dict]:
    """What can be bought (prices in rubles; preliminary)."""
    return [
        {"id": "coins_100", "kind": "coins", "title": "100 монеток", "coins": 100, "price_rub": 99, "elite_days": 0},
        {"id": "coins_300", "kind": "coins", "title": "300 монеток", "coins": 300, "price_rub": 249, "elite_days": 0,
         "badge": "выгодно"},
        {"id": "coins_1000", "kind": "coins", "title": "1000 монеток", "coins": 1000, "price_rub": 699, "elite_days": 0,
         "badge": "−30%"},
        {"id": "elite_month", "kind": "elite", "title": "Elite на 30 дней", "coins": settings.elite_monthly_coins,
         "price_rub": settings.elite_price_rub, "elite_days": settings.elite_days},
    ]


def provider() -> str:
    return "yookassa" if settings.yookassa_shop_id and settings.yookassa_secret_key else "stub"


# ---------------------------------------------------------------------------
# balance and the ledger (call inside a transaction: the balance and its record change together)
# ---------------------------------------------------------------------------
def _write(db: Database, user_id: int, delta: int, reason: str, ref: str | None) -> int:
    bal = db.one("SELECT coins FROM users WHERE id=?", (user_id,))["coins"]
    db.run("INSERT INTO coin_ledger(user_id, delta, balance_after, reason, ref, created_at) VALUES(?,?,?,?,?,?)",
           (user_id, delta, bal, reason, ref, now_ms()))
    return bal


def credit(db: Database, user_id: int, amount: int, reason: str, ref: str | None = None) -> int:
    db.run("UPDATE users SET coins=coins+? WHERE id=?", (amount, user_id))
    return _write(db, user_id, amount, reason, ref)


def charge(db: Database, user_id: int, amount: int, reason: str, ref: str | None = None) -> int:
    """Takes coins or refuses (402) without changing anything."""
    if amount <= 0:
        return db.one("SELECT coins FROM users WHERE id=?", (user_id,))["coins"]
    cur = db.run("UPDATE users SET coins=coins-? WHERE id=? AND coins>=?", (amount, user_id, amount))
    if cur.rowcount != 1:
        have = db.one("SELECT coins FROM users WHERE id=?", (user_id,))["coins"]
        raise ApiError(402, "no_coins", f"Не хватает монеток: нужно {amount}, у тебя {have}. Пополнить — в разделе «Монетки».")
    return _write(db, user_id, -amount, reason, ref)


def give_start_bonus(db: Database, user_id: int) -> None:
    if settings.coins_start_bonus > 0:
        credit(db, user_id, settings.coins_start_bonus, "start_bonus")


def start_bonus_for_existing(db: Database) -> int:
    """Once: players who registered before coins existed get the same welcome coins."""
    if db.one("SELECT 1 FROM meta WHERE key='coins_start_bonus_given'"):
        return 0
    n = 0
    with db.tx():
        for r in db.all("SELECT id FROM users WHERE id NOT IN (SELECT DISTINCT user_id FROM coin_ledger)"):
            give_start_bonus(db, r["id"])
            n += 1
        db.run("INSERT INTO meta(key, value) VALUES('coins_start_bonus_given', ?)", (str(now_ms()),))
    return n


REASONS = {"start_bonus": "Подарок за регистрацию", "scene_image": "Картинка сцены", "scene_image_refund": "Возврат: картинка не получилась",
           "avatar": "ИИ-аватар", "avatar_refund": "Возврат: аватар не получился", "purchase": "Покупка", "elite_bonus": "Монетки Elite",
           "admin": "Подарок от администратора"}


def ledger(db: Database, user: User, limit: int = 50) -> list[dict]:
    rows = db.all("SELECT * FROM coin_ledger WHERE user_id=? ORDER BY id DESC LIMIT ?", (user.id, limit))
    return [{"delta": r["delta"], "balance": r["balance_after"], "reason": r["reason"],
             "title": REASONS.get(r["reason"], r["reason"]), "created_at": r["created_at"]} for r in rows]


def shop(db: Database, user: User) -> dict:
    row = db.one("SELECT coins, elite_until FROM users WHERE id=?", (user.id,))
    until = row["elite_until"] if row["elite_until"] and row["elite_until"] > now_ms() else None
    return {"coins": row["coins"], "elite": {"active": until is not None, "until": until},
            "costs": {"scene_image": settings.cost_scene_image, "avatar": settings.cost_avatar},
            "products": products(), "provider": provider(), "test_mode": settings.payments_test_mode,
            "elite_perks": ["Баннер в профиле", "Светящийся переливающийся ник", "Особые анимированные рамки",
                            f"{settings.elite_monthly_coins} монеток каждый месяц", "Значок Elite рядом с ником"]}


# ---------------------------------------------------------------------------
# payments
# ---------------------------------------------------------------------------
class PaymentIn(BaseModel):
    product: str = Field(max_length=40)


def payment_dict(p) -> dict:
    return {"id": p["public_id"], "product": p["product"], "title": p["title"], "amount_rub": p["amount_kopecks"] / 100,
            "status": p["status"], "provider": p["provider"], "confirmation_url": p["confirmation_url"],
            "created_at": p["created_at"], "paid_at": p["paid_at"]}


async def create_payment(db: Database, user: User, body: PaymentIn) -> dict:
    prod = next((p for p in products() if p["id"] == body.product), None)
    if not prod:
        raise ApiError(400, "bad_product", "Такого товара нет.")
    pid = new_id(12)
    prov = provider()
    with db.tx():
        db.run("INSERT INTO payments(public_id, user_id, product, title, amount_kopecks, coins, elite_days, status, provider, "
               "created_at) VALUES(?,?,?,?,?,?,?, 'pending', ?, ?)",
               (pid, user.id, prod["id"], prod["title"], prod["price_rub"] * 100, prod["coins"], prod["elite_days"], prov, now_ms()))
    if prov == "yookassa":
        res = await _yookassa("POST", "/payments", {
            "amount": {"value": f"{prod['price_rub']}.00", "currency": "RUB"}, "capture": True,
            "confirmation": {"type": "redirect", "return_url": f"{settings.public_url}/app/#/coins?payment={pid}"},
            "description": f"GramSoul: {prod['title']}", "metadata": {"payment_id": pid}}, idempotence_key=pid)
        url = (res.get("confirmation") or {}).get("confirmation_url")
        db.run("UPDATE payments SET provider_id=?, confirmation_url=? WHERE public_id=?", (res.get("id"), url, pid))
    return payment_dict(db.one("SELECT * FROM payments WHERE public_id=?", (pid,)))


def get_payment(db: Database, user: User, pid: str) -> dict:
    p = db.one("SELECT * FROM payments WHERE public_id=? AND user_id=?", (pid, user.id))
    if not p:
        raise ApiError(404, "not_found", "Платёж не найден.")
    return payment_dict(p)


def confirm_test_payment(db: Database, user: User, pid: str) -> dict:
    """The stub "pays" (PAYMENTS_TEST_MODE=on only; otherwise the payment stays pending)."""
    p = db.one("SELECT * FROM payments WHERE public_id=? AND user_id=?", (pid, user.id))
    if not p:
        raise ApiError(404, "not_found", "Платёж не найден.")
    if p["provider"] != "stub" or not settings.payments_test_mode:
        raise ApiError(403, "payments_disabled", "Оплата пока не подключена. Скоро здесь будет ЮKassa.")
    fulfill(db, p["id"])
    return payment_dict(db.one("SELECT * FROM payments WHERE id=?", (p["id"],)))


def fulfill(db: Database, payment_id: int) -> bool:
    """Credits a paid payment once (repeated calls, e.g. a repeated webhook, change nothing)."""
    with db.tx():
        p = db.one("SELECT * FROM payments WHERE id=?", (payment_id,))
        if not p or p["status"] != "pending":
            return False
        db.run("UPDATE payments SET status='succeeded', paid_at=? WHERE id=?", (now_ms(), p["id"]))
        if p["elite_days"]:
            extend_elite(db, p["user_id"], p["elite_days"])
            if p["coins"]:
                credit(db, p["user_id"], p["coins"], "elite_bonus", p["public_id"])
        elif p["coins"]:
            credit(db, p["user_id"], p["coins"], "purchase", p["public_id"])
    return True


def extend_elite(db: Database, user_id: int, days: int) -> int:
    row = db.one("SELECT elite_until FROM users WHERE id=?", (user_id,))
    start = max(now_ms(), row["elite_until"] or 0)
    until = start + days * 86_400_000
    db.run("UPDATE users SET elite_until=? WHERE id=?", (until, user_id))
    return until


async def yookassa_webhook(db: Database, payload: dict) -> None:
    """A notification from YooKassa. It is not trusted as such: the payment is read back from YooKassa's API
    (with our secret key) and only its own answer counts."""
    if provider() != "yookassa":
        raise ApiError(404, "not_found", "Не найдено")
    obj = (payload or {}).get("object") or {}
    ext_id = str(obj.get("id") or "")[:64]
    if not ext_id:
        raise ApiError(400, "bad_request", "Нет платежа.")
    real = await _yookassa("GET", f"/payments/{ext_id}")
    p = db.one("SELECT * FROM payments WHERE provider='yookassa' AND provider_id=?", (ext_id,))
    if not p or (real.get("metadata") or {}).get("payment_id") != p["public_id"]:
        log.warning("yookassa webhook for an unknown payment %s", ext_id)
        return
    paid = real.get("status") == "succeeded" and real.get("paid") is True
    amount = real.get("amount") or {}
    if paid and amount.get("currency") == "RUB" and round(float(amount.get("value", 0)) * 100) == p["amount_kopecks"]:
        fulfill(db, p["id"])
    elif real.get("status") == "canceled":
        db.run("UPDATE payments SET status='canceled' WHERE id=? AND status='pending'", (p["id"],))


async def _yookassa(method: str, path: str, body: dict | None = None, idempotence_key: str | None = None) -> dict:
    headers = {"Idempotence-Key": idempotence_key or uuid.uuid4().hex} if method == "POST" else {}
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.request(method, settings.yookassa_api_url.rstrip("/") + path, json=body, headers=headers,
                                     auth=(settings.yookassa_shop_id, settings.yookassa_secret_key))
    except httpx.HTTPError as e:
        raise ApiError(502, "payment_failed", f"ЮKassa не ответила ({type(e).__name__}). Попробуй ещё раз.")
    if r.status_code >= 400:
        log.warning("yookassa %s %s: %s %s", method, path, r.status_code, r.text[:500])
        raise ApiError(502, "payment_failed", "ЮKassa не приняла платёж. Попробуй позже.")
    return r.json()


# ---------------------------------------------------------------------------
# the admin page: give coins or Elite (to try things out, to reward someone)
# ---------------------------------------------------------------------------
class GrantIn(BaseModel):
    coins: int = Field(default=0, ge=0, le=100_000)
    elite_days: int = Field(default=0, ge=0, le=3650)


def grant(db: Database, public_id: str, body: GrantIn) -> dict | None:
    u = db.one("SELECT id FROM users WHERE public_id=?", (public_id,))
    if not u:
        return None
    with db.tx():
        if body.coins:
            credit(db, u["id"], body.coins, "admin")
        if body.elite_days:
            extend_elite(db, u["id"], body.elite_days)
    row = db.one("SELECT coins, elite_until FROM users WHERE id=?", (u["id"],))
    return {"coins": row["coins"], "elite_until": row["elite_until"]}
