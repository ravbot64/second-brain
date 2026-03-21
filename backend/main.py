from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from secrets import compare_digest, token_urlsafe
from api.router import router
from core.config import settings
from core.init_db import init_postgres, init_qdrant

app = FastAPI(title="Second Brain API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Simple rate limiting: track requests per IP
from collections import defaultdict
from datetime import datetime, timedelta

request_tracker = defaultdict(list)

@app.middleware("http")
async def rate_limit_middleware(request, call_next):
    client_ip = request.client.host if request.client else "unknown"
    now = datetime.now()
    cutoff = now - timedelta(minutes=1)
    
    # Clean old request timestamps for this IP
    request_tracker[client_ip] = [t for t in request_tracker[client_ip] if t > cutoff]
    
    # Check rate limit: max 60 requests per minute per IP
    if len(request_tracker[client_ip]) >= 60:
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded: 60 requests per minute"}
        )
    
    request_tracker[client_ip].append(now)

    # Periodically evict stale IPs to prevent unbounded dict growth
    if len(request_tracker) > 5000:
        stale = [ip for ip, times in list(request_tracker.items()) if not times]
        for ip in stale:
            request_tracker.pop(ip, None)
    
    response = await call_next(request)
    return response

app.include_router(router, prefix="/api")

@app.on_event("startup")
async def startup_init_datastores():
    insecure_defaults = {"", "change-this-in-production"}
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
            raise RuntimeError("JWT_SECRET must be set to a strong secret (min 32 chars) before starting the API")

    # Avoid hard-failing app startup if a managed service is temporarily unreachable.
    try:
        init_postgres()
    except Exception as e:
        print(f"Startup warning: Postgres init failed: {e}")

    try:
        init_qdrant()
    except Exception as e:
        print(f"Startup warning: Qdrant init failed: {e}")

@app.get("/")
def read_root():
    return {"status": "healthy", "service": "Second Brain"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
