import io

from docx import Document
from pypdf import PdfWriter

from src.services.resume_parser import parse_resume_bytes

SAMPLE_TEXT = "Jane Doe\nExperienced backend engineer.\n\nSKILLS\nPython, PostgreSQL\n"


def _build_pdf_bytes(text_pages: list[str]) -> bytes:
    writer = PdfWriter()
    for _ in text_pages:
        writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _build_docx_bytes(paragraphs: list[str]) -> bytes:
    document = Document()
    for para in paragraphs:
        document.add_paragraph(para)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def test_txt_parses_successfully():
    result = parse_resume_bytes(SAMPLE_TEXT.encode("utf-8"), "resume.txt")

    assert result.success is True
    assert result.file_type == "txt"
    assert "Jane Doe" in result.extracted_text
    assert result.character_count == len(result.extracted_text)
    assert result.error is None


def test_docx_parses_successfully():
    data = _build_docx_bytes(["Jane Doe", "Experienced backend engineer with production systems experience."])

    result = parse_resume_bytes(data, "resume.docx")

    assert result.success is True
    assert result.file_type == "docx"
    assert "Jane Doe" in result.extracted_text


def test_empty_file_is_rejected():
    result = parse_resume_bytes(b"", "resume.txt")

    assert result.success is False
    assert result.error == "empty file"


def test_unsupported_file_type_is_rejected():
    result = parse_resume_bytes(b"whatever", "resume.xyz")

    assert result.success is False
    assert "unsupported file type" in result.error


def test_corrupt_docx_is_reported_not_silently_accepted():
    result = parse_resume_bytes(b"this is not a real docx file", "resume.docx")

    assert result.success is False
    assert "corrupt" in result.error.lower()


def test_corrupt_pdf_is_reported_not_silently_accepted():
    result = parse_resume_bytes(b"%PDF-1.4 not a real pdf body", "resume.pdf")

    assert result.success is False
    assert "corrupt" in result.error.lower()


def test_scanned_pdf_with_no_extractable_text_is_a_controlled_failure():
    # A structurally valid PDF with blank pages has no extractable text --
    # this simulates a scanned/image-only PDF without needing OCR fixtures.
    data = _build_pdf_bytes(["", ""])

    result = parse_resume_bytes(data, "resume.pdf")

    assert result.success is False
    assert "no extractable text" in result.error.lower()


def test_very_short_resume_produces_a_warning_but_still_succeeds():
    result = parse_resume_bytes(b"Jane Doe", "resume.txt")

    assert result.success is True
    assert any("unusually short" in w for w in result.warnings)


def test_unexpectedly_huge_input_is_truncated_with_a_warning():
    huge_text = ("Experienced engineer with many skills. " * 2000).encode("utf-8")

    result = parse_resume_bytes(huge_text, "resume.txt")

    assert result.success is True
    assert any("unusually large" in w for w in result.warnings)
    assert len(result.extracted_text) <= 20_000


def test_whitespace_only_txt_is_treated_as_no_extractable_text():
    result = parse_resume_bytes(b"   \n\n   \t  ", "resume.txt")

    assert result.success is False
    assert "no extractable text" in result.error.lower()
