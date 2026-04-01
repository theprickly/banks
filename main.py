from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import sqlite3
import hashlib
import hmac
import json
import time
import os

app = FastAPI(title="UZ Football Collector API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BOT_TOKEN = os.getenv("BOT_TOKEN", "8769534921:AAGJqVc8qGMiidQxsXwjPgpLryPcjuAiQxY")
DB_PATH = "game.db"

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                username    TEXT,
                first_name  TEXT,
                collected   TEXT DEFAULT '[]',
                completed_at TEXT DEFAULT NULL,
                created_at  REAL DEFAULT (unixepoch())
            )
        """)
        db.commit()

init_db()

# ---------------------------------------------------------------------------
# Telegram auth validation
# ---------------------------------------------------------------------------

def validate_init_data(init_data: str) -> dict:
    """Validate Telegram WebApp initData and return user dict."""
    parsed = {}
    for part in init_data.split("&"):
        if "=" in part:
            k, v = part.split("=", 1)
            parsed[k] = v

    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise HTTPException(status_code=401, detail="Missing hash")

    data_check = "\n".join(
        f"{k}={v}" for k, v in sorted(parsed.items())
    )
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret_key, data_check.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected, received_hash):
        raise HTTPException(status_code=401, detail="Invalid signature")

    user_json = parsed.get("user", "{}")
    return json.loads(user_json)

def get_user_from_header(x_init_data: Optional[str]) -> dict:
    """In dev mode (no token), allow a fake user header."""
    if not x_init_data:
        raise HTTPException(status_code=401, detail="Missing X-Init-Data header")

    # Dev shortcut: if BOT_TOKEN not configured, accept JSON directly
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        try:
            return json.loads(x_init_data)
        except Exception:
            pass

    return validate_init_data(x_init_data)

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class CollectionUpdate(BaseModel):
    collected: list[int]   # list of player indices

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok", "time": int(time.time())}


@app.post("/auth")
def auth(x_init_data: Optional[str] = Header(None)):
    """Login / register user via Telegram initData."""
    user = get_user_from_header(x_init_data)
    tid = user["id"]

    with get_db() as db:
        row = db.execute("SELECT * FROM users WHERE telegram_id=?", (tid,)).fetchone()
        if not row:
            db.execute(
                "INSERT INTO users (telegram_id, username, first_name) VALUES (?,?,?)",
                (tid, user.get("username", ""), user.get("first_name", "")),
            )
            db.commit()
            row = db.execute("SELECT * FROM users WHERE telegram_id=?", (tid,)).fetchone()

    return {
        "telegram_id": row["telegram_id"],
        "first_name": row["first_name"],
        "username": row["username"],
        "collected": json.loads(row["collected"]),
        "completed": row["completed_at"] is not None,
    }


@app.get("/collection")
def get_collection(x_init_data: Optional[str] = Header(None)):
    """Get current user's collected players."""
    user = get_user_from_header(x_init_data)
    tid = user["id"]

    with get_db() as db:
        row = db.execute("SELECT collected, completed_at FROM users WHERE telegram_id=?", (tid,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User not found. Call /auth first.")

    return {
        "collected": json.loads(row["collected"]),
        "completed": row["completed_at"] is not None,
    }


@app.put("/collection")
def update_collection(
    body: CollectionUpdate,
    x_init_data: Optional[str] = Header(None),
):
    """Save the full list of collected player indices."""
    user = get_user_from_header(x_init_data)
    tid = user["id"]

    TOTAL_PLAYERS = 8
    for idx in body.collected:
        if idx < 0 or idx >= TOTAL_PLAYERS:
            raise HTTPException(status_code=400, detail=f"Invalid player index: {idx}")

    completed_at = None
    if len(set(body.collected)) == TOTAL_PLAYERS:
        with get_db() as db:
            existing = db.execute("SELECT completed_at FROM users WHERE telegram_id=?", (tid,)).fetchone()
            if existing and existing["completed_at"] is None:
                completed_at = str(int(time.time()))

    with get_db() as db:
        if completed_at:
            db.execute(
                "UPDATE users SET collected=?, completed_at=? WHERE telegram_id=?",
                (json.dumps(sorted(set(body.collected))), completed_at, tid),
            )
        else:
            db.execute(
                "UPDATE users SET collected=? WHERE telegram_id=?",
                (json.dumps(sorted(set(body.collected))), tid),
            )
        db.commit()

    return {"ok": True, "collected": sorted(set(body.collected)), "just_completed": completed_at is not None}


@app.get("/leaderboard")
def leaderboard(x_init_data: Optional[str] = Header(None)):
    """Top-20 users by number of collected players."""
    user = get_user_from_header(x_init_data)
    tid = user["id"]

    with get_db() as db:
        rows = db.execute("""
            SELECT telegram_id, first_name, username, collected, completed_at
            FROM users
            ORDER BY json_array_length(collected) DESC, completed_at ASC
            LIMIT 20
        """).fetchall()

    result = []
    my_rank = None
    for i, row in enumerate(rows, 1):
        entry = {
            "rank": i,
            "name": row["first_name"] or row["username"] or "Игрок",
            "score": len(json.loads(row["collected"])),
            "completed": row["completed_at"] is not None,
            "is_me": row["telegram_id"] == tid,
        }
        result.append(entry)
        if row["telegram_id"] == tid:
            my_rank = i

    # If current user not in top-20, append them at the bottom
    if my_rank is None:
        with get_db() as db:
            me = db.execute("SELECT first_name, username, collected FROM users WHERE telegram_id=?", (tid,)).fetchone()
        if me:
            result.append({
                "rank": "20+",
                "name": me["first_name"] or me["username"] or "Вы",
                "score": len(json.loads(me["collected"])),
                "completed": False,
                "is_me": True,
            })

    return {"leaderboard": result, "my_rank": my_rank}
