import httpx
import uvicorn
from fastapi import FastAPI, Request

app = FastAPI(docs_url=None)

_bot_token = ""
_chat_id = 0
_webhook_secret = ""


def configure(token: str, chat_id: int, webhook_secret: str = "") -> None:
    global _bot_token, _chat_id, _webhook_secret
    _bot_token = token
    _chat_id = chat_id
    _webhook_secret = webhook_secret


def _check_auth(request: Request) -> bool:
    if not _webhook_secret:
        return True
    token = request.query_params.get("token") or ""
    if token == _webhook_secret:
        return True
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer ") and auth[7:] == _webhook_secret:
        return True
    return False


@app.get("/")
async def root():
    return {"status": "ok", "service": "telegram-bot-webhook"}


@app.post("/webhook")
async def webhook(request: Request):
    if not _check_auth(request):
        return {"error": "unauthorized"}, 401

    try:
        data = await request.json()
    except Exception:
        body = await request.body()
        data = body.decode(errors="replace")

    text = f"Received:\n{data}"

    async with httpx.AsyncClient() as client:
        await client.post(
            f"https://api.telegram.org/bot{_bot_token}/sendMessage",
            json={"chat_id": _chat_id, "text": text},
        )

    return {"ok": True}


def run_fastapi(port: int = 3000) -> None:
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
