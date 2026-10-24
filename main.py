import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, EmailStr, Field
from pwdlib import PasswordHash
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from dotenv import load_dotenv

load_dotenv()
BASE_DIR = Path(__file__).resolve().parent
SECRET_KEY = os.getenv("SECRET_KEY", "")
MONGODB_URI = os.getenv("MONGODB_URI", "")
DATABASE_NAME = os.getenv("DATABASE_NAME", "aether_ai")
SESSION_COOKIE = "aether_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 14
password_hash = PasswordHash.recommended()
serializer = URLSafeTimedSerializer(SECRET_KEY, salt="aether-ai-session") if SECRET_KEY else None

app = FastAPI(title="Aether AI", version="0.1.0")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
mongo_client = None
db = None


@app.on_event("startup")
async def startup():
    global mongo_client, db
    if MONGODB_URI:
        mongo_client = AsyncIOMotorClient(MONGODB_URI, serverSelectionTimeoutMS=7000)
        db = mongo_client[DATABASE_NAME]
        try:
            await mongo_client.admin.command("ping")
            await db.users.create_index("username_lower", unique=True)
            await db.users.create_index("email_lower", unique=True)
            await db.chats.create_index([("user_id", 1), ("created_at", -1)])
        except Exception as exc:
            print(f"MongoDB startup check failed: {exc}")
    else:
        print("WARNING: MONGODB_URI is not configured; authentication endpoints will return 503.")


@app.on_event("shutdown")
async def shutdown():
    if mongo_client:
        mongo_client.close()


def require_config():
    if db is None:
        raise HTTPException(status_code=503, detail="MongoDB is not configured or unavailable. Set MONGODB_URI in the environment.")


def get_user_id(request: Request) -> Optional[str]:
    if not serializer:
        return None
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    try:
        payload = serializer.loads(token, max_age=SESSION_MAX_AGE)
        return payload.get("uid")
    except (BadSignature, SignatureExpired):
        return None


async def current_user(request: Request):
    require_config()
    uid = get_user_id(request)
    if not uid:
        raise HTTPException(status_code=401, detail="Please sign in.")
    from bson import ObjectId
    try:
        user = await db.users.find_one({"_id": ObjectId(uid)}, {"password_hash": 0})
    except Exception:
        user = None
    if not user:
        raise HTTPException(status_code=401, detail="Session expired. Please sign in again.")
    return user


class RegisterBody(BaseModel):
    username: str = Field(min_length=3, max_length=24)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginBody(BaseModel):
    login: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=128)


class ChatBody(BaseModel):
    message: str = Field(min_length=1, max_length=8000)


@app.get("/")
async def index():
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/api/health")
async def health():
    mongo_ok = False
    if db is not None:
        try:
            await mongo_client.admin.command("ping")
            mongo_ok = True
        except Exception:
            pass
    return {"ok": True, "service": "Aether AI", "database": "connected" if mongo_ok else "not_configured_or_unavailable"}


@app.post("/api/auth/register")
async def register(body: RegisterBody, request: Request):
    require_config()
    if not serializer:
        raise HTTPException(status_code=503, detail="SECRET_KEY is not configured.")
    username = body.username.strip()
    email = str(body.email).strip().lower()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{3,24}", username):
        raise HTTPException(status_code=422, detail="Nickname must be 3–24 characters: letters, numbers, _, . or -.")
    username_lower = username.lower()
    if await db.users.find_one({"$or": [{"username_lower": username_lower}, {"email_lower": email}]}):
        raise HTTPException(status_code=409, detail="This nickname or email is already registered.")
    now = datetime.now(timezone.utc)
    result = await db.users.insert_one({
        "username": username,
        "username_lower": username_lower,
        "email": email,
        "email_lower": email,
        "password_hash": password_hash.hash(body.password),
        "created_at": now,
        "settings": {"theme": "dark"},
    })
    response = JSONResponse({"ok": True, "user": {"username": username}})
    set_session(response, str(result.inserted_id), request)
    return response


@app.post("/api/auth/login")
async def login(body: LoginBody, request: Request):
    require_config()
    if not serializer:
        raise HTTPException(status_code=503, detail="SECRET_KEY is not configured.")
    value = body.login.strip().lower()
    user = await db.users.find_one({"$or": [{"username_lower": value}, {"email_lower": value}]})
    if not user or not password_hash.verify(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Incorrect nickname/email or password.")
    response = JSONResponse({"ok": True, "user": {"username": user["username"]}})
    set_session(response, str(user["_id"]), request)
    return response


def set_session(response, uid: str, request: Request):
    token = serializer.dumps({"uid": uid})
    response.set_cookie(
        SESSION_COOKIE, token, httponly=True, secure=request.url.scheme == "https",
        samesite="lax", max_age=SESSION_MAX_AGE, path="/"
    )


@app.post("/api/auth/logout")
async def logout():
    response = JSONResponse({"ok": True})
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, samesite="lax")
    return response


@app.get("/api/auth/me")
async def me(request: Request):
    user = await current_user(request)
    return {"ok": True, "user": {"username": user["username"], "email": user["email"]}}


@app.get("/api/chat/history")
async def chat_history(request: Request):
    user = await current_user(request)
    cursor = db.chats.find({"user_id": str(user["_id"])}).sort("created_at", 1).limit(100)
    messages = []
    async for item in cursor:
        messages.append({"role": item["role"], "content": item["content"], "created_at": item["created_at"].isoformat()})
    return {"messages": messages}


async def generate_reply(message: str, user: dict) -> str:
    # Provider adapter seam: connect Groq here in the next phase.
    # Never expose provider keys to browser JavaScript.
    if os.getenv("GROQ_API_KEY"):
        try:
            from groq import AsyncGroq
            client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))
            model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
            completion = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are Aether, a helpful AI assistant. Be clear and friendly. If a capability is not connected, say so honestly."},
                    {"role": "user", "content": message},
                ],
                temperature=0.7,
                max_tokens=1800,
            )
            return completion.choices[0].message.content or "I couldn't produce a response this time."
        except Exception as exc:
            print(f"Groq request failed: {exc}")
            return "I couldn't reach the AI provider right now. Please try again in a moment."
    return (
        "Привет! Я Aether — твой ИИ-компаньон. Сейчас работает стартовая версия: регистрация, "
        "история чата и интерактивная сфера. Подключение Groq ещё не настроено. "
        "Добавь GROQ_API_KEY в переменные окружения Render, чтобы включить реальные ответы ИИ.\n\n"
        f"Твоё сообщение: «{message[:500]}»"
    )


@app.post("/api/chat")
async def chat(body: ChatBody, request: Request):
    user = await current_user(request)
    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Message cannot be empty.")
    now = datetime.now(timezone.utc)
    await db.chats.insert_one({"user_id": str(user["_id"]), "role": "user", "content": message, "created_at": now})
    reply = await generate_reply(message, user)
    await db.chats.insert_one({"user_id": str(user["_id"]), "role": "assistant", "content": reply, "created_at": datetime.now(timezone.utc)})
    return {"reply": reply}


@app.get("/{path:path}")
async def frontend_fallback(path: str):
    candidate = (BASE_DIR / "static" / path).resolve()
    static_root = (BASE_DIR / "static").resolve()
    if candidate.is_file() and static_root in candidate.parents:
        return FileResponse(candidate)
    return FileResponse(BASE_DIR / "static" / "index.html")
