"""
Agentic Archive - Google Drive Document Archive Manager with Pydantic AI

A package for managing and archiving documents in Google Drive using AI-powered
classification and intelligent organization.
"""

from agentic_archive.archive_docs import (
    create_drive_service,
    process_document,
    archive_with_agent,
    main,
)

__version__ = "0.1.0"
__all__ = [
    "create_drive_service",
    "process_document",
    "archive_with_agent",
    "main",
]
