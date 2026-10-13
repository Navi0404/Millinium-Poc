from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routes import auth, emails
from app.core.config import get_settings
from app.core.exceptions import GmailAuthError, GmailNotFoundError, LLMError

settings = get_settings()

app = FastAPI(title=settings.app_name)

app.include_router(auth.router)
app.include_router(emails.router)


@app.exception_handler(GmailAuthError)
def gmail_auth_handler(request: Request, exc: GmailAuthError):
    return JSONResponse(status_code=401, content={"detail": str(exc)})


@app.exception_handler(GmailNotFoundError)
def gmail_not_found_handler(request: Request, exc: GmailNotFoundError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(LLMError)
def llm_handler(request: Request, exc: LLMError):
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.get("/health", tags=["health"])
def health():
    return {
        "health": "ok",
        "message": "AI server is running"
    }
