from __future__ import annotations

from typing import Any

import httpx
from fastapi import HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.codex_auth import CodexAuthError, codex_auth_manager
from app.config import settings
from app.models import ApiKey, UsageLog
from app.oauth_manual import get_active_upstream_credential


async def resolve_upstream_bearer_token(db: AsyncSession | None = None) -> str:
    mode = settings.upstream_auth_mode.strip().lower() or 'auto'
    if mode == 'env_token':
        if not settings.upstream_bearer_token:
            raise HTTPException(status_code=500, detail='UPSTREAM_BEARER_TOKEN is not configured')
        return settings.upstream_bearer_token
    if mode == 'codex_auth_file':
        try:
            return codex_auth_manager.load_bearer_token()
        except CodexAuthError as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
    if mode == 'oauth_manual':
        if db is None:
            raise HTTPException(status_code=500, detail='database session required for oauth_manual mode')
        credential = await get_active_upstream_credential(db)
        if not credential or not credential.access_token:
            raise HTTPException(status_code=401, detail='no active oauth credential; start login first')
        return credential.access_token

    if settings.upstream_bearer_token:
        return settings.upstream_bearer_token
    if db is not None:
        credential = await get_active_upstream_credential(db)
        if credential and credential.access_token:
            return credential.access_token
    try:
        return codex_auth_manager.load_bearer_token()
    except CodexAuthError as e:
        raise HTTPException(status_code=500, detail=f'no usable upstream auth found: {e}') from e


async def forward_to_upstream(path: str, payload: dict[str, Any], db: AsyncSession | None = None) -> tuple[int, dict[str, Any], str | None]:
    bearer_token = await resolve_upstream_bearer_token(db)

    url = f"{settings.upstream_base_url.rstrip('/')}{path}"
    headers = {
        'Authorization': f'Bearer {bearer_token}',
        'Content-Type': 'application/json',
    }

    async with httpx.AsyncClient(timeout=settings.upstream_timeout_seconds) as client:
        resp = await client.post(url, headers=headers, json=payload)

    req_id = resp.headers.get('x-request-id') or resp.headers.get('openai-request-id')
    try:
        data = resp.json()
    except Exception:
        data = {'error': {'message': resp.text}}
    return resp.status_code, data, req_id


async def record_usage(
    db: AsyncSession,
    api_key: ApiKey,
    path: str,
    model: str | None,
    status_code: int,
    response_json: dict[str, Any],
    upstream_request_id: str | None,
) -> None:
    usage = response_json.get('usage') or {}
    prompt_tokens = int(usage.get('prompt_tokens') or usage.get('input_tokens') or 0)
    completion_tokens = int(usage.get('completion_tokens') or usage.get('output_tokens') or 0)
    total_tokens = int(usage.get('total_tokens') or (prompt_tokens + completion_tokens))

    api_key.request_count += 1
    api_key.prompt_tokens += prompt_tokens
    api_key.completion_tokens += completion_tokens
    api_key.total_tokens += total_tokens

    error_message = None
    if status_code >= 400:
        error_message = ((response_json.get('error') or {}).get('message')) if isinstance(response_json, dict) else None

    db.add(UsageLog(
        api_key_id=api_key.id,
        user_id=api_key.user_id,
        path=path,
        model=model,
        status_code=status_code,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        upstream_request_id=upstream_request_id,
        error_message=error_message,
    ))
    await db.commit()


def validate_model(model: str | None) -> None:
    allowed = settings.allowed_models
    if allowed and model and model not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f'model not allowed: {model}',
        )


async def parse_request_json(request: Request) -> dict[str, Any]:
    try:
        return await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail='invalid json body')
