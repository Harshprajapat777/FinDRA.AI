import sys
from pathlib import Path

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).parent))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from config.settings import settings
from database.repository import init_db

console = Console()


def create_output_dirs() -> None:
    """Create required directories if they don't exist."""
    dirs = [
        Path("outputs/reports"),
        Path("data/documents"),
        Path(settings.chroma_db_path),
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)


def print_startup_info() -> None:
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column(style="dim")
    table.add_column(style="cyan")

    table.add_row("LLM",          "Claude (Anthropic)")
    table.add_row("Orchestration","LangGraph")
    table.add_row("Vector DB",    f"ChromaDB @ {settings.chroma_db_path}")
    table.add_row("Database",     settings.database_url)
    table.add_row("Web Search",   "Tavily")
    table.add_row("API Server",   f"http://{settings.host}:{settings.port}")
    table.add_row("Std Depth",    str(settings.standard_research_depth) + " steps")
    table.add_row("Deep Depth",   str(settings.deep_research_depth) + " steps")

    console.print(Panel(table, title="[bold cyan]FinResearchAI[/bold cyan]", border_style="cyan"))


def main() -> None:
    console.print("\n[bold cyan]Starting Financial Deep Research Agent...[/bold cyan]\n")

    # 1. Create output directories
    console.print("[dim]>> Creating output directories...[/dim]")
    create_output_dirs()
    console.print("[green]OK Directories ready[/green]")

    # 2. Initialise database
    console.print("[dim]>> Initialising database...[/dim]")
    init_db()
    console.print("[green]OK Database tables created[/green]")

    # 3. Print config summary
    print_startup_info()

    console.print(
        "\n[bold green]Setup complete.[/bold green] "
        "Run [cyan]uvicorn api.server:app --reload --port 8000[/cyan] to start the API server.\n"
    )



if __name__ == "__main__":
    main()
