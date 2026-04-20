"""Reddit connection REST API.

Endpoints:
- GET  /api/v1/reddit/account        — current config (password redacted)
- POST /api/v1/reddit/account        — create/replace config
- PUT  /api/v1/reddit/account/{id}   — update subreddits/keywords/enabled
- DELETE /api/v1/reddit/account/{id}
- POST /api/v1/reddit/test           — verify creds against Reddit API
- POST /api/v1/reddit/reply          — manual reply to a comment or DM
"""
import uuid
from datetime import datetime
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException

from database import get_database
from models.reddit_models import (
    RedditAccountCreate,
    RedditAccountUpdate,
    RedditPostReply,
)
from repositories.reddit_repository import RedditRepository
from services.reddit_client import RedditClient

router = APIRouter(prefix="/api/v1/reddit", tags=["reddit"])


def _repo(db=Depends(get_database)) -> RedditRepository:
    return RedditRepository(db)


def _redact(doc: Dict[str, Any]) -> Dict[str, Any]:
    if not doc:
        return doc
    out = {**doc}
    out["password"] = "***"
    out["client_secret"] = "***"
    return out


@router.get("/account")
async def get_account(repo: RedditRepository = Depends(_repo)) -> Dict[str, Any]:
    doc = await repo.get_active()
    return {"account": _redact(doc) if doc else None}


@router.post("/account")
async def create_account(
    payload: RedditAccountCreate, repo: RedditRepository = Depends(_repo)
) -> Dict[str, Any]:
    existing = await repo.get_active()
    if existing:
        await repo.delete(existing["_id"])

    doc = {
        "_id": str(uuid.uuid4()),
        **payload.model_dump(exclude_none=True),
        "enabled": True,
        "last_seen_ids": {},
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }
    doc.setdefault("user_agent", "ContextuAI-Solo/1.0")
    await repo.create(doc)
    return {"account": _redact(doc)}


@router.put("/account/{account_id}")
async def update_account(
    account_id: str,
    payload: RedditAccountUpdate,
    repo: RedditRepository = Depends(_repo),
) -> Dict[str, Any]:
    updated = await repo.update(
        account_id,
        {**payload.model_dump(exclude_none=True), "updated_at": datetime.utcnow().isoformat()},
    )
    if not updated:
        raise HTTPException(404, "Account not found")
    return {"account": _redact(updated)}


@router.delete("/account/{account_id}")
async def delete_account(account_id: str, repo: RedditRepository = Depends(_repo)) -> Dict[str, Any]:
    ok = await repo.delete(account_id)
    if not ok:
        raise HTTPException(404, "Account not found")
    return {"deleted": True}


@router.post("/test")
async def test_connection(repo: RedditRepository = Depends(_repo)) -> Dict[str, Any]:
    account = await repo.get_active()
    if not account:
        raise HTTPException(400, "No Reddit account configured")
    client = RedditClient(
        client_id=account["client_id"],
        client_secret=account["client_secret"],
        username=account["username"],
        password=account["password"],
        user_agent=account.get("user_agent", "ContextuAI-Solo/1.0"),
    )
    try:
        return await client.test_connection()
    except Exception as e:
        raise HTTPException(400, f"Reddit auth failed: {e}") from e


@router.post("/reply")
async def send_reply(
    payload: RedditPostReply, repo: RedditRepository = Depends(_repo)
) -> Dict[str, Any]:
    account = await repo.get_active()
    if not account:
        raise HTTPException(400, "No Reddit account configured")
    client = RedditClient(
        client_id=account["client_id"],
        client_secret=account["client_secret"],
        username=account["username"],
        password=account["password"],
        user_agent=account.get("user_agent", "ContextuAI-Solo/1.0"),
    )
    try:
        if payload.target_type == "comment":
            reply_id = await client.reply_to_comment(payload.target_id, payload.text)
            return {"ok": True, "reply_id": reply_id}
        if payload.target_type == "dm":
            if not payload.recipient:
                raise HTTPException(400, "'recipient' required for DM replies")
            ok = await client.send_dm(payload.recipient, "Re: your message", payload.text)
            return {"ok": ok}
        raise HTTPException(400, f"Unsupported target_type: {payload.target_type}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Reddit reply failed: {e}") from e
