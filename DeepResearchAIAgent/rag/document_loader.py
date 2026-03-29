from pathlib import Path

from rich.console import Console
from rich.progress import track

from tools.document_processor import process_pdf, scan_documents_folder
from rag.vector_store import vector_store

console = Console()


# Maps folder name or filename keywords to sector
SECTOR_HINTS = {
    "it": "IT",
    "tech": "IT",
    "infosys": "IT",
    "tcs": "IT",
    "wipro": "IT",
    "hcl": "IT",
    "pharma": "Pharma",
    "sun": "Pharma",
    "cipla": "Pharma",
    "reddy": "Pharma",
    "biocon": "Pharma",
    "divi": "Pharma",
}


def _detect_sector(path: Path) -> str:
    """Guess sector from file/folder name keywords."""
    name = path.stem.lower()
    for keyword, sector in SECTOR_HINTS.items():
        if keyword in name:
            return sector
    # Check parent folder too
    parent = path.parent.name.lower()
    for keyword, sector in SECTOR_HINTS.items():
        if keyword in parent:
            return sector
    return "general"


def _detect_doc_type(path: Path) -> str:
    """Guess document type from filename."""
    name = path.stem.lower()
    if any(k in name for k in ["annual", "ar", "report"]):
        return "annual_report"
    if any(k in name for k in ["investor", "presentation", "ppt"]):
        return "investor_presentation"
    if any(k in name for k in ["quarter", "q1", "q2", "q3", "q4"]):
        return "quarterly_report"
    return "financial_document"


def ingest_pdf(
    path: str | Path,
    sector: str = None,
    company: str = None,
    doc_type: str = None,
    chunk_size: int = 800,
    overlap: int = 100,
) -> int:
    """
    Load, chunk, and store a single PDF into the vector store.

    Args:
        path:       Path to PDF file
        sector:     IT | Pharma | general (auto-detected if None)
        company:    Company name for metadata filtering
        doc_type:   annual_report | investor_presentation | quarterly_report
        chunk_size: Characters per chunk
        overlap:    Overlap between chunks

    Returns:
        Number of chunks ingested
    """
    path = Path(path)
    sector = sector or _detect_sector(path)
    doc_type = doc_type or _detect_doc_type(path)
    company = company or path.stem

    metadata = {
        "sector": sector,
        "company": company,
        "doc_type": doc_type,
        "filename": path.name,
    }

    console.print(f"[dim]Ingesting:[/dim] [cyan]{path.name}[/cyan] "
                  f"[dim]sector={sector} company={company}[/dim]")

    chunks = process_pdf(path, chunk_size=chunk_size, overlap=overlap, metadata=metadata)
    count = vector_store.add_documents(chunks, sector=sector)

    console.print(f"[green]OK[/green] {count} chunks stored in '{sector}' collection")
    return count


def ingest_all(
    folder: str | Path = "data/documents",
    chunk_size: int = 800,
    overlap: int = 100,
) -> dict:
    """
    Walk the documents folder and ingest every PDF found.
    Skips files that are already fully indexed (by chunk count heuristic).

    Returns:
        Summary dict {filename: chunk_count}
    """
    folder = Path(folder)
    pdfs = scan_documents_folder(folder)

    if not pdfs:
        console.print(f"[yellow]No PDFs found in {folder}[/yellow]")
        return {}

    console.print(f"\n[bold cyan]Ingesting {len(pdfs)} PDF(s) from {folder}[/bold cyan]\n")

    summary = {}
    for pdf in track(pdfs, description="Ingesting documents..."):
        try:
            count = ingest_pdf(pdf, chunk_size=chunk_size, overlap=overlap)
            summary[pdf.name] = count
        except Exception as e:
            console.print(f"[red]FAILED {pdf.name}: {e}[/red]")
            summary[pdf.name] = 0

    console.print(f"\n[bold green]Ingestion complete.[/bold green] "
                  f"Total files: {len(summary)}, "
                  f"Total chunks: {sum(summary.values())}")
    return summary


def show_stats() -> None:
    """Print collection stats for all sectors."""
    console.print("\n[bold]Vector Store Stats[/bold]")
    for sector in ["IT", "Pharma", "general"]:
        stats = vector_store.collection_stats(sector)
        console.print(f"  {stats['collection']}: [cyan]{stats['count']}[/cyan] chunks")


if __name__ == "__main__":
    # Run directly to ingest: python -m rag.document_loader
    ingest_all()
    show_stats()
