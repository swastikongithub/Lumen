"""Fixed value sets shared by the database models and the API schemas (SPEC §7.1).

The string values are what gets stored and sent over the API, so treat them as part of
the v1 contract: add values freely, but never rename or remove one.
"""

from enum import StrEnum


class DocumentCategory(StrEnum):
    ACADEMICS = "academics"
    EXAMS = "exams"
    HOSTEL = "hostel"
    FEES = "fees"
    PLACEMENTS = "placements"
    OTHER = "other"


class DocumentStatus(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"


class Client(StrEnum):
    WEB = "web"
    ANDROID = "android"


class Role(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class FeedbackReason(StrEnum):
    WRONG = "wrong"
    OUTDATED = "outdated"
    NOT_FOUND = "not_found"
    UNCLEAR = "unclear"
    # Required by Google Play's AI-Generated Content policy. Never remove (CLAUDE.md rule 13).
    OFFENSIVE = "offensive"
    OTHER = "other"
