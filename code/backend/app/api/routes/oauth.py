from datetime import timedelta
from typing import Any, Literal
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app import crud
from app.api.deps import SessionDep
from app.core import security
from app.core.config import settings

OAuthProvider = Literal["google", "facebook", "microsoft"]

router = APIRouter(prefix="/oauth", tags=["oauth"])

STATE_COOKIE_NAME = "vintrade_oauth_state_nonce"
STATE_MAX_AGE_SECONDS = 10 * 60


class OAuthError(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason


def _frontend_url() -> str:
    return (settings.FRONTEND_URL or settings.FRONTEND_HOST).rstrip("/")


def _backend_url() -> str:
    return settings.BACKEND_URL.rstrip("/")


def _redirect_to_login_error(reason: str) -> RedirectResponse:
    url = f"{_frontend_url()}/login?{urlencode({'oauth_error': reason})}"
    return RedirectResponse(url=url, status_code=303)


def _redirect_to_callback(provider: str, token: str) -> RedirectResponse:
    query = urlencode({"token": token, "provider": provider})
    return RedirectResponse(
        url=f"{_frontend_url()}/auth/callback?{query}",
        status_code=303,
    )


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.OAUTH_STATE_SECRET or settings.SECRET_KEY)


def _create_state(provider: OAuthProvider) -> tuple[str, str]:
    import secrets

    nonce = secrets.token_urlsafe(32)
    state = _serializer().dumps({"provider": provider, "nonce": nonce})
    return state, nonce


def _validate_state(
    *, provider: str, state: str | None, expected_nonce: str | None
) -> dict[str, Any]:
    if not state or not expected_nonce:
        raise OAuthError("invalid_state")
    try:
        payload = _serializer().loads(state, max_age=STATE_MAX_AGE_SECONDS)
    except SignatureExpired:
        raise OAuthError("expired_state")
    except BadSignature:
        raise OAuthError("invalid_state")

    if payload.get("provider") != provider or payload.get("nonce") != expected_nonce:
        raise OAuthError("invalid_state")
    return payload


def _provider_config(provider: OAuthProvider) -> dict[str, str]:
    if provider == "google":
        client_id = settings.GOOGLE_CLIENT_ID
        client_secret = settings.GOOGLE_CLIENT_SECRET
        authorize_url = "https://accounts.google.com/o/oauth2/v2/auth"
        token_url = "https://oauth2.googleapis.com/token"
        userinfo_url = "https://openidconnect.googleapis.com/v1/userinfo"
        scope = "openid email profile"
    elif provider == "facebook":
        client_id = settings.FACEBOOK_CLIENT_ID
        client_secret = settings.FACEBOOK_CLIENT_SECRET
        authorize_url = "https://www.facebook.com/v19.0/dialog/oauth"
        token_url = "https://graph.facebook.com/v19.0/oauth/access_token"
        userinfo_url = "https://graph.facebook.com/me?fields=id,email,name,picture.type(large)"
        scope = "email,public_profile"
    else:
        client_id = settings.MICROSOFT_CLIENT_ID
        client_secret = settings.MICROSOFT_CLIENT_SECRET
        tenant_id = settings.MICROSOFT_TENANT_ID or "common"
        authorize_url = (
            f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize"
        )
        token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
        userinfo_url = "https://graph.microsoft.com/oidc/userinfo"
        scope = "openid email profile User.Read"

    if not client_id or not client_secret:
        raise OAuthError("provider_not_configured")

    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "authorize_url": authorize_url,
        "token_url": token_url,
        "userinfo_url": userinfo_url,
        "scope": scope,
    }


def _callback_url(provider: str) -> str:
    return f"{_backend_url()}/api/auth/oauth/{provider}/callback"


def _authorization_url(provider: OAuthProvider, state: str) -> str:
    config = _provider_config(provider)
    params = {
        "client_id": config["client_id"],
        "redirect_uri": _callback_url(provider),
        "response_type": "code",
        "scope": config["scope"],
        "state": state,
    }
    return f"{config['authorize_url']}?{urlencode(params)}"


async def _exchange_code_for_token(provider: OAuthProvider, code: str) -> str:
    config = _provider_config(provider)
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            config["token_url"],
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": _callback_url(provider),
                "client_id": config["client_id"],
                "client_secret": config["client_secret"],
            },
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        token_data = response.json()

    access_token = token_data.get("access_token")
    if not access_token:
        raise OAuthError("token_exchange_failed")
    return str(access_token)


async def _fetch_userinfo(provider: OAuthProvider, access_token: str) -> dict[str, Any]:
    config = _provider_config(provider)
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(
            config["userinfo_url"],
            headers={"Authorization": f"Bearer {access_token}"},
        )
        response.raise_for_status()
        return response.json()


def _normalize_profile(provider: OAuthProvider, data: dict[str, Any]) -> dict[str, str | None]:
    if provider == "google":
        provider_user_id = data.get("sub")
        email = data.get("email")
        full_name = data.get("name")
        avatar_url = data.get("picture")
    elif provider == "facebook":
        provider_user_id = data.get("id")
        email = data.get("email")
        full_name = data.get("name")
        picture = data.get("picture") or {}
        avatar_url = (picture.get("data") or {}).get("url")
    else:
        provider_user_id = data.get("sub") or data.get("id") or data.get("oid")
        email = (
            data.get("email")
            or data.get("preferred_username")
            or data.get("upn")
            or data.get("mail")
            or data.get("userPrincipalName")
        )
        full_name = data.get("name") or data.get("displayName")
        avatar_url = data.get("picture")

    if not provider_user_id or not email:
        raise OAuthError("profile_missing_email")

    return {
        "provider": provider,
        "provider_user_id": str(provider_user_id),
        "email": str(email).strip().lower(),
        "full_name": str(full_name).strip() if full_name else None,
        "avatar_url": str(avatar_url) if avatar_url else None,
    }


@router.get("/{provider}/login")
def oauth_login(provider: OAuthProvider) -> RedirectResponse:
    try:
        state, nonce = _create_state(provider)
        authorization_url = _authorization_url(provider, state)
    except OAuthError as exc:
        return _redirect_to_login_error(exc.reason)

    response = RedirectResponse(url=authorization_url, status_code=303)
    response.set_cookie(
        STATE_COOKIE_NAME,
        nonce,
        max_age=STATE_MAX_AGE_SECONDS,
        httponly=True,
        secure=settings.ENVIRONMENT != "local",
        samesite="lax",
    )
    return response


@router.get("/{provider}/callback")
async def oauth_callback(
    provider: OAuthProvider,
    request: Request,
    session: SessionDep,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    response: RedirectResponse
    try:
        if error:
            raise OAuthError("provider_denied")
        if not code:
            raise OAuthError("missing_code")

        _validate_state(
            provider=provider,
            state=state,
            expected_nonce=request.cookies.get(STATE_COOKIE_NAME),
        )
        provider_token = await _exchange_code_for_token(provider, code)
        provider_profile = await _fetch_userinfo(provider, provider_token)
        profile = _normalize_profile(provider, provider_profile)
        user = crud.upsert_oauth_user(session=session, **profile)

        if not user.is_active:
            raise OAuthError("inactive_user")

        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        internal_token = security.create_access_token(
            user.id,
            expires_delta=access_token_expires,
        )
        response = _redirect_to_callback(provider, internal_token)
    except OAuthError as exc:
        response = _redirect_to_login_error(exc.reason)
    except httpx.HTTPError:
        response = _redirect_to_login_error("oauth_login_failed")

    response.delete_cookie(STATE_COOKIE_NAME)
    return response
