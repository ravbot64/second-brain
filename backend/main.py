from contextlib import asynccontextmanager
from collections import defaultdict
from datetime import datetime, timedelta
from secrets import compare_digest, token_urlsafe

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.router import router
from core.config import settings
from core.init_db import init_postgres, init_qdrant


def _ensure_jwt_secret() -> None:
    """Fail fast in production if a strong JWT secret is not configured."""
    insecure_defaults = {"", "change-this-in-production", "replace_with_a_long_random_secret_min_32_chars"}
    jwt_secret = (settings.JWT_SECRET or "").strip()

    localhost_prefixes = (
        "http://localhost",
        "http://127.0.0.1",
        "https://localhost",
        "https://127.0.0.1",
    )
    local_origins_only = bool(settings.cors_origins_list) and all(
        origin.startswith(localhost_prefixes) for origin in settings.cors_origins_list
    )
    is_local_dev = settings.DB_URL.startswith("sqlite") or local_origins_only

    if any(compare_digest(jwt_secret, value) for value in insecure_defaults) or len(jwt_secret) < 32:
        if is_local_dev:
            settings.JWT_SECRET = token_urlsafe(48)
            print("Startup warning: using ephemeral JWT_SECRET for local development only")
        else:
            raise RuntimeError(
                "JWT_SECRET must be set to a strong secret (min 32 chars) before starting the API"
            )


@asynccontextmanager
async def lifespan(app: FastAPI):
    _ensure_jwt_secret()

    # Avoid hard-failing app startup if a managed service is temporarily unreachable
    # (e.g. free-tier cold starts). Endpoints degrade gracefully instead.
    try:
        init_postgres()
    except Exception as e:
        print(f"Startup warning: Postgres init failed: {e}")

    try:
        init_qdrant()
    except Exception as e:
        print(f"Startup warning: Qdrant init failed: {e}")

    yield


app = FastAPI(title="Second Brain API", version="1.1.0", lifespan=lifespan)

# CORS is restricted to explicit origins and the methods/headers this API actually uses.
# Wildcards are avoided because credentials are allowed.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    max_age=600,
)


# ── Rate limiting ─────────────────────────────────────────────────────────────
# In-memory sliding-window limiter. Auth endpoints get a much stricter budget to
# slow credential-stuffing/brute-force attempts.
GENERAL_LIMIT_PER_MIN = 120
AUTH_LIMIT_PER_MIN = 15

request_tracker: defaultdict = defaultdict(list)
auth_tracker: defaultdict = defaultdict(list)


def _is_auth_path(path: str) -> bool:
    return path.startswith("/api/auth/")


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    client_ip = request.client.host if request.client else "unknown"
    now = datetime.now()
    cutoff = now - timedelta(minutes=1)

    tracker = auth_tracker if _is_auth_path(request.url.path) else request_tracker
    limit = AUTH_LIMIT_PER_MIN if _is_auth_path(request.url.path) else GENERAL_LIMIT_PER_MIN

    tracker[client_ip] = [t for t in tracker[client_ip] if t > cutoff]

    if len(tracker[client_ip]) >= limit:
        return JSONResponse(
            status_code=429,
            content={"detail": f"Rate limit exceeded: {limit} requests per minute"},
            headers={"Retry-After": "60"},
        )

    tracker[client_ip].append(now)

    # Periodically evict stale IPs to prevent unbounded dict growth.
    for store in (request_tracker, auth_tracker):
        if len(store) > 5000:
            for ip in [ip for ip, times in list(store.items()) if not times]:
                store.pop(ip, None)

    return await call_next(request)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)

    # Defense-in-depth headers. This is a JSON API (no HTML rendered), so a strict
    # deny-all CSP is safe and blocks any accidental content sniffing/framing.
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    response.headers.setdefault("Cross-Origin-Resource-Policy", "same-site")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
    )
    response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")

    # HSTS only when the request reached us over HTTPS (Render terminates TLS and
    # forwards the original scheme via X-Forwarded-Proto).
    forwarded_proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    if forwarded_proto == "https":
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )

    return response


app.include_router(router, prefix="/api")


@app.get("/")
def read_root():
    # Lightweight health/warmup endpoint (no datastore calls) used by uptime
    # pingers and the frontend warmup probe to avoid free-tier cold-start stalls.
    return {"status": "healthy", "service": "Second Brain"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
