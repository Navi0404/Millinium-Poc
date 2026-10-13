from fastapi import APIRouter, Depends, Query

from app.api.deps import get_gmail_service, get_llm_service
from app.schemas.email import EmailAISummary, EmailDetail, EmailListResponse
from app.services.gmail_service import GmailService
from app.services.llm_service import LLMService

router = APIRouter(prefix="/emails", tags=["emails"])


@router.get("", response_model=EmailListResponse)
def list_inbox(
    max_results: int = Query(10, ge=1, le=50),
    page_token: str | None = None,
    q: str | None = Query(None, description="Gmail search query, e.g. 'from:boss'"),
    unread_only: bool = False,
    gmail: GmailService = Depends(get_gmail_service),
):
    return gmail.list_inbox(max_results, page_token, q, unread_only)


@router.get("/{message_id}", response_model=EmailDetail)
def read_email(
    message_id: str,
    include_attachments: bool = Query(
        True, description="Download attachments and extract their text"
    ),
    gmail: GmailService = Depends(get_gmail_service),
):
    return gmail.get_email(message_id, include_attachments)


@router.get("/{message_id}/summary", response_model=EmailAISummary)
def summarize_email(
    message_id: str,
    gmail: GmailService = Depends(get_gmail_service),
    llm: LLMService = Depends(get_llm_service),
):
    email = gmail.get_email(message_id)
    return EmailAISummary(
        id=email.id,
        subject=email.subject,
        summary=llm.summarize_email(email),
        model=llm.model,
    )
