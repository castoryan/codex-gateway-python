from __future__ import annotations

import base64
import json
from typing import Any

import httpx
from fastapi import HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.codex_auth import CodexAuthError, codex_auth_manager
from app.config import settings
from app.models import ApiKey, UsageLog, UpstreamCredential
from app.oauth_manual import get_active_upstream_credential

JWT_CLAIM_PATH = 'https://api.openai.com/auth'
CODEX_TOOL_CALL_PROVIDERS = {'openai', 'openai-codex', 'opencode'}


async def resolve_upstream_credential(db: AsyncSession | None = None) -> tuple[str, str | None]:
    mode = settings.upstream_auth_mode.strip().lower() or 'oauth_manual'
    if mode == 'env_token':
        if not settings.upstream_bearer_token:
            raise HTTPException(status_code=500, detail='UPSTREAM_BEARER_TOKEN is not configured')
        return settings.upstream_bearer_token, None
    if mode == 'codex_auth_file':
        try:
            return codex_auth_manager.load_bearer_token(), None
        except CodexAuthError as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
    if mode == 'oauth_manual':
        if db is None:
            raise HTTPException(status_code=500, detail='database session required for oauth_manual mode')
        credential = await get_active_upstream_credential(db)
        if not credential or not credential.access_token:
            raise HTTPException(status_code=401, detail='no active oauth credential; start login first')
        return credential.access_token, credential.account_id

    if settings.upstream_bearer_token:
        return settings.upstream_bearer_token, None
    if db is not None:
        credential = await get_active_upstream_credential(db)
        if credential and credential.access_token:
            return credential.access_token, credential.account_id
    try:
        return codex_auth_manager.load_bearer_token(), None
    except CodexAuthError as e:
        raise HTTPException(status_code=500, detail=f'no usable upstream auth found: {e}') from e


async def resolve_upstream_bearer_token(db: AsyncSession | None = None) -> str:
    token, _ = await resolve_upstream_credential(db)
    return token


def _decode_jwt_payload(access_token: str) -> dict[str, Any] | None:
    try:
        parts = access_token.split('.')
        if len(parts) != 3:
            return None
        payload = parts[1]
        padding = '=' * (-len(payload) % 4)
        decoded = base64.urlsafe_b64decode(payload + padding).decode('utf-8')
        obj = json.loads(decoded)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def extract_account_id_from_token(access_token: str) -> str | None:
    payload = _decode_jwt_payload(access_token)
    if not payload:
        return None
    auth_claim = payload.get(JWT_CLAIM_PATH)
    if isinstance(auth_claim, dict):
        account_id = auth_claim.get('chatgpt_account_id')
        if isinstance(account_id, str) and account_id:
            return account_id
    return None


def _convert_messages_to_input(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for msg in messages:
        role = msg.get('role')
        content = msg.get('content')
        if isinstance(content, str):
            parts = [{'type': 'input_text', 'text': content}]
        elif isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict) and block.get('type') in ('text', 'input_text'):
                    text = block.get('text') or block.get('content') or ''
                    if text:
                        parts.append({'type': 'input_text', 'text': text})
        else:
            parts = []
        if not parts:
            continue
        items.append({'role': role or 'user', 'content': parts})
    return items


def build_codex_request_body(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    model = payload.get('model')
    body: dict[str, Any] = {
        'model': model,
        'store': False,
        'stream': False,
        'text': {'verbosity': 'medium'},
        'include': ['reasoning.encrypted_content'],
        'tool_choice': 'auto',
        'parallel_tool_calls': True,
    }

    if path == '/v1/chat/completions':
        messages = payload.get('messages') or []
        body['input'] = _convert_messages_to_input(messages)
    elif path == '/v1/responses':
        if 'input' in payload:
            input_value = payload.get('input')
            if isinstance(input_value, str):
                body['input'] = [{'role': 'user', 'content': [{'type': 'input_text', 'text': input_value}]}]
            else:
                body['input'] = input_value
        if payload.get('instructions'):
            body['instructions'] = payload.get('instructions')
    else:
        raise HTTPException(status_code=400, detail=f'unsupported codex backend path: {path}')

    if payload.get('temperature') is not None:
        body['temperature'] = payload.get('temperature')
    return body


def normalize_codex_response_to_chat(data: dict[str, Any], model: str) -> dict[str, Any]:
    output_text = data.get('output_text')
    if not output_text:
        parts: list[str] = []
        for item in data.get('output', []) or []:
            if not isinstance(item, dict):
                continue
            for content in item.get('content', []) or []:
                if isinstance(content, dict):
                    text = content.get('text') or content.get('output_text')
                    if text:
                        parts.append(text)
        output_text = ''.join(parts)

    usage = data.get('usage') or {}
    prompt_tokens = int(usage.get('input_tokens') or usage.get('prompt_tokens') or 0)
    completion_tokens = int(usage.get('output_tokens') or usage.get('completion_tokens') or 0)
    total_tokens = int(usage.get('total_tokens') or (prompt_tokens + completion_tokens))

    return {
        'id': data.get('id', 'codex_response'),
        'object': 'chat.completion',
        'created': data.get('created_at') or 0,
        'model': model,
        'choices': [{
            'index': 0,
            'message': {'role': 'assistant', 'content': output_text or ''},
            'finish_reason': 'stop',
        }],
        'usage': {
            'prompt_tokens': prompt_tokens,
            'completion_tokens': completion_tokens,
            'total_tokens': total_tokens,
        },
        '_codex_raw': data,
    }


def normalize_codex_response_to_responses(data: dict[str, Any]) -> dict[str, Any]:
    usage = data.get('usage') or {}
    return {
        'id': data.get('id'),
        'object': 'response',
        'model': data.get('model'),
        'output': data.get('output', []),
        'output_text': data.get('output_text', ''),
        'usage': {
            'input_tokens': int(usage.get('input_tokens') or 0),
            'output_tokens': int(usage.get('output_tokens') or 0),
            'total_tokens': int(usage.get('total_tokens') or 0),
        },
        '_codex_raw': data,
    }


async def forward_to_upstream(path: str, payload: dict[str, Any], db: AsyncSession | None = None) -> tuple[int, dict[str, Any], str | None]:
    bearer_token, account_id = await resolve_upstream_credential(db)
    account_id = account_id or extract_account_id_from_token(bearer_token)
    if not account_id:
        raise HTTPException(status_code=500, detail='failed to extract chatgpt_account_id from token')

    if path == '/v1/embeddings':
        raise HTTPException(status_code=400, detail='embeddings are not supported in codex backend mode')

    codex_body = build_codex_request_body(path, payload)
    url = f"{settings.upstream_base_url.rstrip('/')}/codex/responses"
    headers = {
        'Authorization': f'Bearer {bearer_token}',
        'chatgpt-account-id': account_id,
        'OpenAI-Beta': settings.upstream_openai_beta,
        'originator': settings.oauth_originator,
        'User-Agent': 'pi (linux x86_64)',
        'accept': 'application/json, text/event-stream',
        'content-type': 'application/json',
    }

    async with httpx.AsyncClient(timeout=settings.upstream_timeout_seconds) as client:
        resp = await client.post(url, headers=headers, json=codex_body)

    req_id = resp.headers.get('x-request-id') or resp.headers.get('openai-request-id')
    try:
        data = resp.json()
    except Exception:
        data = {'error': {'message': resp.text}}

    if resp.status_code >= 400:
        return resp.status_code, data, req_id

    if path == '/v1/chat/completions':
        return resp.status_code, normalize_codex_response_to_chat(data, payload.get('model') or data.get('model') or ''), req_id
    if path == '/v1/responses':
        return resp.status_code, normalize_codex_response_to_responses(data), req_id
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
