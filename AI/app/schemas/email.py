from pydantic import BaseModel


class EmailSummary(BaseModel):
    id: str
    thread_id: str
    subject: str
    sender: str
    date: str
    snippet: str
    unread: bool


class Attachment(BaseModel):
    filename: str
    mime_type: str
    size: int
    # Extracted text; None when it was not read (see `note` for the reason).
    text: str | None = None
    truncated: bool = False
    note: str | None = None


class EmailDetail(EmailSummary):
    to: str
    body: str
    attachments: list[Attachment] = []


class EmailListResponse(BaseModel):
    emails: list[EmailSummary]
    next_page_token: str | None = None


class EmailAISummary(BaseModel):
    id: str
    subject: str
    summary: str
    model: str


class AuthStatus(BaseModel):
    authenticated: bool
    email: str | None = None
