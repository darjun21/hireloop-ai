"""
Deterministic resume text extraction (PDF / DOCX / TXT).

This service does exactly one thing: turn a file into plain text. It does
NOT interpret meaning — that's the Profile Agent's job, on a separate call,
with the file itself never reaching the LLM. Keeping these separate means a
parsing bug can never masquerade as a hallucinated resume fact.

No OCR: a scanned/image-only PDF yields no extractable text and is reported
as a failure, never silently treated as an empty-but-successful parse.
"""

from __future__ import annotations

import io
from pathlib import Path

import pypdf
from docx import Document

from src.models.resume_parse import ResumeParseResult

_SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt"}
_MIN_REASONABLE_CHARS = 50
_MAX_CHARS_BEFORE_TRUNCATION = 20_000


def _extract_pdf_text(data: bytes) -> str:
    reader = pypdf.PdfReader(io.BytesIO(data))
    pages_text = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages_text)


def _extract_docx_text(data: bytes) -> str:
    document = Document(io.BytesIO(data))
    return "\n".join(paragraph.text for paragraph in document.paragraphs)


def _extract_txt_text(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def parse_resume_bytes(data: bytes, filename: str) -> ResumeParseResult:
    extension = Path(filename).suffix.lower()

    if extension not in _SUPPORTED_EXTENSIONS:
        return ResumeParseResult(
            file_type=extension or "unknown",
            success=False,
            error=f"unsupported file type: {extension or '(none)'}",
        )

    file_type = extension.lstrip(".")

    if len(data) == 0:
        return ResumeParseResult(file_type=file_type, success=False, error="empty file")

    try:
        if extension == ".pdf":
            text = _extract_pdf_text(data)
        elif extension == ".docx":
            text = _extract_docx_text(data)
        else:
            text = _extract_txt_text(data)
    except Exception as exc:  # noqa: BLE001 - any parser library exception means "corrupt/unreadable"
        return ResumeParseResult(
            file_type=file_type,
            success=False,
            error=f"corrupt or unreadable {file_type} file: {exc}",
        )

    stripped = text.strip()
    warnings: list[str] = []

    if not stripped:
        return ResumeParseResult(
            file_type=file_type,
            extracted_text="",
            character_count=0,
            success=False,
            error=(
                "no extractable text found in file "
                "(if this is a scanned/image-only PDF, OCR is not supported in this phase)"
            ),
        )

    if len(stripped) < _MIN_REASONABLE_CHARS:
        warnings.append(f"resume text is unusually short ({len(stripped)} characters); extraction may be incomplete")

    if len(stripped) > _MAX_CHARS_BEFORE_TRUNCATION:
        warnings.append(
            f"resume text is unusually large ({len(stripped)} characters); truncated to first "
            f"{_MAX_CHARS_BEFORE_TRUNCATION} characters for downstream processing"
        )
        stripped = stripped[:_MAX_CHARS_BEFORE_TRUNCATION]

    return ResumeParseResult(
        file_type=file_type,
        extracted_text=stripped,
        character_count=len(stripped),
        warnings=warnings,
        success=True,
    )


def parse_resume(file_path: str) -> ResumeParseResult:
    path = Path(file_path)
    if not path.exists():
        return ResumeParseResult(file_type=path.suffix.lstrip(".") or "unknown", success=False, error="file not found")
    data = path.read_bytes()
    return parse_resume_bytes(data, path.name)
