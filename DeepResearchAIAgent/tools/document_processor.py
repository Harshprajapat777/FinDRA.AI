import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pdfplumber


@dataclass
class DocumentChunk:
    text: str
    source: str          # file path or URL
    page: int
    chunk_index: int
    metadata: dict       # sector, company, doc_type, etc.


def _clean_pdf_text(text: str) -> str:
    """Remove excessive whitespace and non-printable characters from extracted PDF text."""
    text = re.sub(r"\s*\n\s*\n\s*", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"[^\x20-\x7E\n]", " ", text)
    return text.strip()


def load_pdf(path: str | Path) -> list[dict]:
    """
    Extract text from a PDF, one entry per page.

    Returns:
        List of {text, source, page} dicts ready for chunking.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")

    pages = []
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ""
            text = _clean_pdf_text(text)
            if text:
                pages.append({
                    "text": text,
                    "source": str(path),
                    "page": i,
                })
    return pages


def chunk_text(
    pages: list[dict],
    chunk_size: int = 800,
    overlap: int = 100,
    metadata: Optional[dict] = None,
) -> list[DocumentChunk]:
    """
    Split page texts into overlapping chunks for RAG ingestion.

    Args:
        pages:      Output from load_pdf()
        chunk_size: Target characters per chunk
        overlap:    Characters of overlap between consecutive chunks
        metadata:   Extra fields (sector, company, doc_type) attached to every chunk

    Returns:
        List of DocumentChunk objects
    """
    metadata = metadata or {}
    chunks: list[DocumentChunk] = []
    chunk_index = 0

    for page in pages:
        text = page["text"]
        source = page["source"]
        page_num = page["page"]

        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))

            # Try to break at sentence boundary
            if end < len(text):
                boundary = text.rfind(". ", start, end)
                if boundary != -1 and boundary > start + overlap:
                    end = boundary + 1

            chunk_text_str = text[start:end].strip()
            if chunk_text_str:
                chunks.append(
                    DocumentChunk(
                        text=chunk_text_str,
                        source=source,
                        page=page_num,
                        chunk_index=chunk_index,
                        metadata=metadata,
                    )
                )
                chunk_index += 1

            start = end - overlap if end < len(text) else end

    return chunks


def process_pdf(
    path: str | Path,
    chunk_size: int = 800,
    overlap: int = 100,
    metadata: Optional[dict] = None,
) -> list[DocumentChunk]:
    """
    Convenience wrapper: load PDF and chunk in one call.

    Args:
        path:       Path to PDF file
        chunk_size: Characters per chunk
        overlap:    Overlap between chunks
        metadata:   e.g. {"sector": "IT", "company": "Infosys", "doc_type": "annual_report"}

    Returns:
        List of DocumentChunk objects ready for vector store ingestion
    """
    pages = load_pdf(path)
    return chunk_text(pages, chunk_size=chunk_size, overlap=overlap, metadata=metadata)


def scan_documents_folder(folder: str | Path = "data/documents") -> list[Path]:
    """Return all PDF files found in the documents folder."""
    folder = Path(folder)
    if not folder.exists():
        return []
    return sorted(folder.glob("**/*.pdf"))
