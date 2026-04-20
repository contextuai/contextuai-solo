"""Twitter/X connection REST API.

Endpoints:
- GET  /api/v1/twitter/account        — current config (secrets redacted)
- POST /api/v1/twitter/account        — create/replace config
- PUT  /api/v1/twitter/account/{id}   — update keywords/poll flags/enabled
- DELETE /api/v1/twitter/account/{id}
- POST /api/v1/twitter/test           — verify creds against Twitter API
- POST /api/v1/twitter/reply          — manual reply to a tweet or DM
"""
import uuid
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from database import get_database
from models.twitter_models import (
    TwitterAccountCreate,
    TwitterAccountUpdate,
    TwitterPostReply,
)
from repositories.twitter_repository import TwitterRepository
from services.twitter_client import TwitterClient

router = APIRouter(prefix="/api/v1/twitter", tags=["twitter"])

_SECRET_FIELDS = ("api_secret", "access_token_secret", "bearer_token")


def _repo(db=Depends(get_database)) -> TwitterRepository:
    return TwitterRepository(db)


def _redact(doc: Dict[str, Any]) -> Dict[str, Any]:
    if not doc:
        return doc
    out = {**doc}
    for f in _SECRET_FIELDS:
        if out.get(f):
            out[f] = "***"
    # Partially mask access_token (not secret-level, but user-identifying)
    if out.get("access_token"):
        tok = out["access_token"]
        out["access_token"] = (tok[:6] + "***") if len(tok) > 8 else "***"
    return out


def _client_from_account(account: Dict[str, Any]) -> TwitterClient:
    return TwitterClient(
        api_key=account.get("api_key"),
        api_secret=account.get("api_secret"),
        access_token=account.get("access_token"),
        access_token_secret=account.get("access_token_secret"),
        bearer_token=account.get("bearer_token"),
    )


@router.get("/account")
async def get_account(repo: TwitterRepository = Depends(_repo)) -> Dict[str, Any]:
    doc = await repo.get_active()
    return {"account": _redact(doc) if doc else None}


@router.post("/account")
async def create_account(
    payload: TwitterAccountCreate, repo: TwitterRepository = Depends(_repo)
) -> Dict[str, Any]:
    # Require either OAuth 1.0a set OR bearer_token
    has_oauth1 = all(
        [
            payload.api_key,
            payload.api_secret,
            payload.access_token,
            payload.access_token_secret,
        ]
    )
    if not has_oauth1 and not payload.bearer_token:
        raise HTTPException(
            400,
            "Either OAuth 1.0a creds (api_key + api_secret + access_token + "
            "access_token_secret) or bearer_token is required",
        )

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
    await repo.create(doc)
    return {"account": _redact(doc)}


@router.put("/account/{account_id}")
async def update_account(
    account_id: str,
    payload: TwitterAccountUpdate,
    repo: TwitterRepository = Depends(_repo),
) -> Dict[str, Any]:
    updated = await repo.update(
        account_id,
        {**payload.model_dump(exclude_none=True), "updated_at": datetime.utcnow().isoformat()},
    )
    if not updated:
        raise HTTPException(404, "Account not found")
    return {"account": _redact(updated)}


@router.delete("/account/{account_id}")
async def delete_account(
    account_id: str, repo: TwitterRepository = Depends(_repo)
) -> Dict[str, Any]:
    ok = await repo.delete(account_id)
    if not ok:
        raise HTTPException(404, "Account not found")
    return {"deleted": True}


@router.post("/test")
async def test_connection(repo: TwitterRepository = Depends(_repo)) -> Dict[str, Any]:
    account = await repo.get_active()
    if not account:
        raise HTTPException(400, "No Twitter account configured")
    client = _client_from_account(account)
    try:
        return await client.test_connection()
    except Exception as e:
        raise HTTPException(400, f"Twitter auth failed: {e}") from e


@router.post("/reply")
async def send_reply(
    payload: TwitterPostReply, repo: TwitterRepository = Depends(_repo)
) -> Dict[str, Any]:
    account = await repo.get_active()
    if not account:
        raise HTTPException(400, "No Twitter account configured")
    client = _client_from_account(account)
    try:
        if payload.target_type == "tweet":
            return await client.reply_to_tweet(payload.target_id, payload.text)
        if payload.target_type == "dm":
            recipient = payload.recipient or payload.target_id
            if not recipient:
                raise HTTPException(400, "'recipient' required for DM replies")
            return await client.send_dm(recipient, payload.text)
        raise HTTPException(400, f"Unsupported target_type: {payload.target_type}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Twitter reply failed: {e}") from e
