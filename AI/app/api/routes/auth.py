from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_gmail_service
from app.core.exceptions import GmailAuthError
from app.schemas.email import AuthStatus
from app.services.gmail_service import GmailService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login", response_model=AuthStatus)
def login(gmail: GmailService = Depends(get_gmail_service)):
    """Opens the Google consent screen in the browser on this machine and
    waits (up to 5 minutes) for the user to approve access."""
    try:
        email = gmail.authorize()
    except GmailAuthError:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Gmail authorisation failed: {exc}")
    return AuthStatus(authenticated=True, email=email)


@router.get("/status", response_model=AuthStatus)
def status(gmail: GmailService = Depends(get_gmail_service)):
    if not gmail.is_authenticated():
        return AuthStatus(authenticated=False)
    return AuthStatus(authenticated=True, email=gmail.profile_email())


@router.post("/logout", response_model=AuthStatus)
def logout(gmail: GmailService = Depends(get_gmail_service)):
    gmail.logout()
    return AuthStatus(authenticated=False)
