class GmailAuthError(Exception):
    """No usable Gmail credentials; the user has to (re)authorise."""


class GmailNotFoundError(Exception):
    """The requested Gmail message does not exist."""


class UnsupportedAttachmentError(Exception):
    """The attachment's content cannot be turned into text."""


class LLMError(Exception):
    """The LLM provider call failed."""
