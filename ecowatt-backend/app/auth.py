"""Authenticate the Flutter app's Supabase session.

Flutter sends `Authorization: Bearer <supabase access_token>`. We ask Supabase Auth
who the token belongs to, which works for both legacy (HS256) and new asymmetric
JWT signing keys without handling key material here.
"""
from __future__ import annotations

from fastapi import HTTPException, Request


async def current_user(request: Request) -> dict:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(401, "Missing bearer token")
    s, http = request.app.state.settings, request.app.state.http
    r = await http.get(
        f"{s.supabase_url}/auth/v1/user",
        headers={"Authorization": header, "apikey": s.supabase_anon_key},
        timeout=10,
    )
    if r.status_code != 200:
        raise HTTPException(401, "Invalid or expired session")
    return r.json()          # contains "id", "email", ...
