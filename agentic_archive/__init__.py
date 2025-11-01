"""
Agentic Archive - Google Drive Document Archive Manager with Google AI

A package for managing and archiving documents in Google Drive using Google's
Gemini AI for classification and intelligent organization.
"""

from agentic_archive.archive_docs import (
    create_drive_service,
    process_document,
    archive_with_ai,
    main,
)

__version__ = "0.2.0"
__all__ = [
    "create_drive_service",
    "process_document",
    "archive_with_ai",
    "main",
]
