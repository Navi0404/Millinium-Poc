import base64
import html
import threading

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.core.config import Settings
from app.core.exceptions import (
    GmailAuthError,
    GmailNotFoundError,
    UnsupportedAttachmentError,
)
from app.schemas.email import Attachment, EmailDetail, EmailListResponse, EmailSummary
from app.services.attachment_service import (
    MAX_ATTACHMENT_BYTES,
    MAX_TEXT_CHARS,
    extract_text,
    html_to_text,
    is_image,
)

METADATA_HEADERS = ["Subject", "From", "To", "Date"]


class GmailService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._login_lock = threading.Lock()

    # ---- auth -----------------------------------------------------------

    def authorize(self) -> str:
        """Run the OAuth consent flow in the local browser and store the token."""
        if not self.settings.client_secret_path.exists():
            raise GmailAuthError(
                f"OAuth client secret not found at {self.settings.client_secret_path}"
            )
        if not self._login_lock.acquire(blocking=False):
            raise GmailAuthError(
                "A Gmail login is already in progress. Finish it in the browser "
                "tab that was opened, or wait for it to time out."
            )
        try:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(self.settings.client_secret_path), self.settings.gmail_scopes
            )
            creds = flow.run_local_server(
                port=self.settings.gmail_oauth_port,
                access_type="offline",
                prompt="consent",
                timeout_seconds=300,
            )
        finally:
            self._login_lock.release()
        self._save(creds)
        return self.profile_email()

    def logout(self) -> None:
        self.settings.token_path.unlink(missing_ok=True)

    def is_authenticated(self) -> bool:
        try:
            self._credentials()
            return True
        except GmailAuthError:
            return False

    def profile_email(self) -> str:
        profile = self._client().users().getProfile(userId="me").execute()
        return profile["emailAddress"]

    def _credentials(self) -> Credentials:
        token_path = self.settings.token_path
        if not token_path.exists():
            raise GmailAuthError("Gmail is not connected. Open /auth/login first.")

        creds = Credentials.from_authorized_user_file(
            str(token_path), self.settings.gmail_scopes
        )
        if creds.valid:
            return creds
        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError as exc:
                raise GmailAuthError(
                    "Gmail access was revoked or expired. Open /auth/login again."
                ) from exc
            self._save(creds)
            return creds
        raise GmailAuthError("Stored Gmail token is invalid. Open /auth/login again.")

    def _save(self, creds: Credentials) -> None:
        self.settings.token_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings.token_path.write_text(creds.to_json(), encoding="utf-8")

    def _client(self):
        # Built per call: the underlying httplib2 transport is not thread-safe.
        return build(
            "gmail", "v1", credentials=self._credentials(), cache_discovery=False
        )

    # ---- inbox ----------------------------------------------------------

    def list_inbox(
        self,
        max_results: int = 10,
        page_token: str | None = None,
        query: str | None = None,
        unread_only: bool = False,
    ) -> EmailListResponse:
        client = self._client()
        labels = ["INBOX", "UNREAD"] if unread_only else ["INBOX"]
        listing = (
            client.users()
            .messages()
            .list(
                userId="me",
                labelIds=labels,
                maxResults=max_results,
                pageToken=page_token,
                q=query,
            )
            .execute()
        )
        ids = [m["id"] for m in listing.get("messages", [])]

        fetched: dict[str, dict] = {}

        def on_message(request_id, response, exception):
            if exception is None:
                fetched[request_id] = response

        if ids:
            batch = client.new_batch_http_request(callback=on_message)
            for message_id in ids:
                batch.add(
                    client.users()
                    .messages()
                    .get(
                        userId="me",
                        id=message_id,
                        format="metadata",
                        metadataHeaders=METADATA_HEADERS,
                    ),
                    request_id=message_id,
                )
            batch.execute()

        return EmailListResponse(
            emails=[
                EmailSummary(**_summary_fields(fetched[i])) for i in ids if i in fetched
            ],
            next_page_token=listing.get("nextPageToken"),
        )

    def get_email(
        self, message_id: str, include_attachments: bool = True
    ) -> EmailDetail:
        client = self._client()
        try:
            message = (
                client.users()
                .messages()
                .get(userId="me", id=message_id, format="full")
                .execute()
            )
        except HttpError as exc:
            if exc.resp.status in (400, 404):
                raise GmailNotFoundError(f"Email {message_id} not found") from exc
            raise

        headers = _headers(message)
        payload = message.get("payload", {})
        return EmailDetail(
            **_summary_fields(message),
            to=headers.get("to", ""),
            body=_extract_body(payload),
            attachments=[
                self._read_attachment(client, message_id, part, include_attachments)
                for part in _attachment_parts(payload)
            ],
        )

    def _read_attachment(
        self, client, message_id: str, part: dict, read_content: bool
    ) -> Attachment:
        body = part.get("body", {})
        attachment = Attachment(
            filename=part["filename"],
            mime_type=part.get("mimeType", ""),
            size=body.get("size", 0),
        )
        if not read_content:
            return attachment
        if attachment.size > MAX_ATTACHMENT_BYTES:
            attachment.note = "Skipped: file is too large to read"
            return attachment
        if _is_inline(part) and is_image(attachment.filename, attachment.mime_type):
            attachment.note = "Skipped: inline image (e.g. signature or logo)"
            return attachment

        try:
            data = body.get("data")
            if data is None:
                data = (
                    client.users()
                    .messages()
                    .attachments()
                    .get(userId="me", messageId=message_id, id=body["attachmentId"])
                    .execute()["data"]
                )
            text = extract_text(
                attachment.filename, attachment.mime_type, _decode_bytes(data)
            )
        except UnsupportedAttachmentError as exc:
            attachment.note = f"Not read: {exc}"
            return attachment
        except Exception as exc:
            attachment.note = f"Could not read file: {exc}"
            return attachment

        attachment.truncated = len(text) > MAX_TEXT_CHARS
        attachment.text = text[:MAX_TEXT_CHARS]
        if not text:
            attachment.note = "No text found in file"
        return attachment


def _headers(message: dict) -> dict[str, str]:
    return {
        h["name"].lower(): h["value"]
        for h in message.get("payload", {}).get("headers", [])
    }


def _summary_fields(message: dict) -> dict:
    headers = _headers(message)
    return {
        "id": message["id"],
        "thread_id": message.get("threadId", ""),
        "subject": headers.get("subject", "(no subject)"),
        "sender": headers.get("from", ""),
        "date": headers.get("date", ""),
        "snippet": html.unescape(message.get("snippet", "")),
        "unread": "UNREAD" in message.get("labelIds", []),
    }


def _decode_bytes(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _decode(data: str) -> str:
    return _decode_bytes(data).decode("utf-8", errors="replace")


def _attachment_parts(payload: dict) -> list[dict]:
    parts = []
    if payload.get("filename"):
        parts.append(payload)
    for part in payload.get("parts", []):
        parts.extend(_attachment_parts(part))
    return parts


def _is_inline(part: dict) -> bool:
    for header in part.get("headers", []):
        if header["name"].lower() == "content-disposition":
            return header["value"].lower().startswith("inline")
    return False


def _find_part(payload: dict, mime_type: str) -> str | None:
    if payload.get("mimeType") == mime_type and not payload.get("filename"):
        data = payload.get("body", {}).get("data")
        if data:
            return _decode(data)
    for part in payload.get("parts", []):
        found = _find_part(part, mime_type)
        if found:
            return found
    return None


def _extract_body(payload: dict) -> str:
    plain = _find_part(payload, "text/plain")
    if plain and plain.strip():
        return plain.strip()
    markup = _find_part(payload, "text/html")
    return html_to_text(markup) if markup else ""
