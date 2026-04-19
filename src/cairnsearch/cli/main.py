"""Command-line interface for cairnsearch."""
import sys
from pathlib import Path
from typing import Optional
import logging

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from cairnsearch.config import Config, set_config
from cairnsearch.db import Database, init_db
from cairnsearch.indexer import IndexManager
from cairnsearch.search import SearchEngine
from cairnsearch.extractors import get_registry


app = typer.Typer(
    name="cairnsearch",
    help="Local document search engine",
    no_args_is_help=True,
)
console = Console()


def setup_logging(verbose: bool = False):
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
    page: int = typer.Option(1, "--page", "-p", help="Page number"),
    size: int = typer.Option(20, "--size", "-s", help="Results per page"),
    config_path: Optional[Path] = typer.Option(None, "--config", "-c", help="Config file path"),
):
    """
    Search indexed documents.
    
    Query syntax:
    
    - Keywords: contract texas
    
    - Phrases: "state of texas"
    
    - Boolean: contract AND texas, contract NOT amendment
    
    - Field: filename:report, type:pdf, author:smith
    
    - Dates: after:2022-01-01, before:2023-12-31, year:2023
    """
    if config_path:
        set_config(Config.load(config_path))
    
    engine = SearchEngine()
    result = engine.search(query, page=page, page_size=size)
    
    if result.total == 0:
        console.print("[yellow]No results found.[/yellow]")
        return
    
    console.print(f"\n[bold]Found {result.total} results[/bold] (page {result.page}, {result.took_ms}ms)\n")
    
    for r in result.results:
        # Result header
        console.print(f"[bold blue]{r.filename}[/bold blue]  [dim]{r.file_type.upper()}[/dim]  [green]Score: {r.score:.2f}[/green]")
        console.print(f"  [dim]{r.file_path}[/dim]")
        
        if r.doc_title:
            console.print(f"  [italic]Title: {r.doc_title}[/italic]")
        if r.doc_author:
            console.print(f"  [italic]Author: {r.doc_author}[/italic]")
        if r.doc_created:
            console.print(f"  [italic]Date: {r.doc_created}[/italic]")
        
        # Snippets
        for snippet in r.snippets:
            # Convert HTML marks to Rich markup
            highlighted = snippet.replace("<mark>", "[bold yellow]").replace("</mark>", "[/bold yellow]")
            console.print(f"  {highlighted}")
        
        console.print()


@app.command()
def status(
    config_path: Optional[Path] = typer.Option(None, "--config", "-c", help="Config file path"),
):
    """Show indexing status."""
    if config_path:
        set_config(Config.load(config_path))
    
    index_manager = IndexManager()
    stats = index_manager.get_stats()
    
    table = Table(title="Index Status")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("Indexed Documents", str(stats["indexed_count"]))
    table.add_row("Pending", str(stats["pending"]))
    table.add_row("Failed", str(stats["failed"]))
    
    console.print(table)
    
    if stats["by_type"]:
        type_table = Table(title="Documents by Type")
        type_table.add_column("Type", style="cyan")
        type_table.add_column("Count", style="green")
        
        for file_type, count in sorted(stats["by_type"].items()):
            type_table.add_row(file_type, str(count))
        
        console.print(type_table)


@app.command()
def reindex(
    path: Optional[Path] = typer.Argument(None, help="File or folder to reindex (default: all)"),
    config_path: Optional[Path] = typer.Option(None, "--config", "-c", help="Config file path"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """Reindex documents."""
    setup_logging(verbose)
    
    if config_path:
        set_config(Config.load(config_path))
    
    index_manager = IndexManager()
    
    if path:
        path = path.expanduser().resolve()
        if not path.exists():
            console.print(f"[red]Path not found: {path}[/red]")
            raise typer.Exit(1)
        
        if path.is_file():
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                progress.add_task(f"Indexing {path.name}...", total=None)
                success = index_manager.index_file(path)
            
            if success:
                console.print(f"[green]✓ Indexed: {path}[/green]")
            else:
                console.print(f"[red]✗ Failed: {path}[/red]")
        else:
            # Index all files in folder
            files = list(path.rglob("*"))
            files = [f for f in files if f.is_file() and get_registry().can_extract(f)]
            
            success_count = 0
            fail_count = 0
            
            with Progress(console=console) as progress:
                task = progress.add_task("Indexing...", total=len(files))
                
                for file_path in files:
                    if index_manager.index_file(file_path):
                        success_count += 1
                    else:
                        fail_count += 1
                    progress.advance(task)
            
            console.print(f"\n[green]✓ Indexed: {success_count}[/green]  [red]✗ Failed: {fail_count}[/red]")
    else:
        # Reindex all watched folders
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task("Reindexing all watched folders...", total=None)
            success, failed = index_manager.reindex_all()
        
        console.print(f"\n[green]✓ Indexed: {success}[/green]  [red]✗ Failed: {failed}[/red]")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host to bind"),
    port: int = typer.Option(8080, "--port", "-p", help="Port to bind"),
    config_path: Optional[Path] = typer.Option(None, "--config", "-c", help="Config file path"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose/debug logging"),
):
    """Start the web server."""
    import os
    
    # Setup logging based on verbose flag or LOG_LEVEL env var
    log_level = os.getenv("LOG_LEVEL", "DEBUG" if verbose else "INFO")
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    
    if config_path:
        set_config(Config.load(config_path))
    
    import uvicorn
    
    console.print(f"\n[bold]Starting cairnsearch server at http://{host}:{port}[/bold]\n")
    console.print(f"Log level: {log_level}")
    console.print("API docs: http://{host}:{port}/docs")
    console.print("Press Ctrl+C to stop\n")
    
    uvicorn.run(
        "cairnsearch.api.app:app",
        host=host,
        port=port,
        reload=reload,
        log_level=log_level.lower(),
    )


@app.command()
def watch(
    start: bool = typer.Option(True, "--start/--stop", help="Start or stop watcher"),
    config_path: Optional[Path] = typer.Option(None, "--config", "-c", help="Config file path"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """Start folder watcher (runs until interrupted)."""
    setup_logging(verbose)
    
    if config_path:
        set_config(Config.load(config_path))
    
    from cairnsearch.config import get_config
    from cairnsearch.queue import WorkerPool
    from cairnsearch.watcher import FolderWatcher
    
    config = get_config()
    
    console.print("[bold]Starting cairnsearch watcher...[/bold]\n")
    console.print("Watching folders:")
    for folder in config.get_watch_folders():
        console.print(f"  • {folder}")
    console.print("\nPress Ctrl+C to stop\n")
    
    # Initialize worker pool
    worker_pool = WorkerPool(num_workers=config.indexer.workers)
    worker_pool.start()
    
    # Initialize watcher
    watcher = FolderWatcher(
        on_created=lambda p: worker_pool.submit(p, "index"),
        on_modified=lambda p: worker_pool.submit(p, "reindex"),
        on_deleted=lambda p: worker_pool.submit(p, "delete", priority=100),
    )
    watcher.start()
    
    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopping watcher...[/yellow]")
    finally:
        watcher.stop()
        worker_pool.stop()
        console.print("[green]Stopped.[/green]")


@app.command()
def config(
    show: bool = typer.Option(True, "--show", help="Show current config"),
    config_path: Optional[Path] = typer.Option(None, "--config", "-c", help="Config file path"),
):
    """Show or edit configuration."""
    if config_path:
        set_config(Config.load(config_path))
    
    from cairnsearch.config import get_config
    cfg = get_config()
    
    console.print(Panel.fit("[bold]cairnsearch Configuration[/bold]"))
    console.print(f"\nData directory: {cfg.get_data_dir()}")
    console.print(f"Database: {cfg.get_db_path()}")
    console.print(f"\nWatch folders:")
    for folder in cfg.get_watch_folders():
        exists = "✓" if folder.exists() else "✗"
        console.print(f"  [{exists}] {folder}")
    console.print(f"\nIndexer workers: {cfg.indexer.workers}")
    console.print(f"OCR enabled: {cfg.ocr.enabled}")
    console.print(f"OCR language: {cfg.ocr.language}")
    console.print(f"\nSupported file types:")
    for ext in get_registry().supported_extensions():
        console.print(f"  {ext}")


@app.command()
def init(
    config_path: Optional[Path] = typer.Option(None, "--config", "-c", help="Config file path"),
):
    """Initialize the database and configuration."""
    if config_path:
        set_config(Config.load(config_path))
    
    from cairnsearch.config import get_config
    cfg = get_config()
    
    # Create data directory
    data_dir = cfg.get_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize database
    init_db(cfg.get_db_path())
    
    console.print(f"[green]✓ Created data directory: {data_dir}[/green]")
    console.print(f"[green]✓ Initialized database: {cfg.get_db_path()}[/green]")
    
    # Check config file
    config_file = Path.home() / ".config" / "cairnsearch" / "config.toml"
    if not config_file.exists():
        console.print(f"\n[yellow]Note: No config file found at {config_file}[/yellow]")
        console.print("Copy config.example.toml to customize settings.")


@app.command()
def ask(
    question: str = typer.Argument(..., help="Question to ask about your documents"),
    file: Optional[Path] = typer.Option(None, "--file", "-f", help="Limit to specific file"),
    top_k: int = typer.Option(5, "--top-k", "-k", help="Number of chunks to retrieve"),
    config_path: Optional[Path] = typer.Option(None, "--config", "-c", help="Config file path"),
):
    """
    Ask a question about your documents using RAG.
    
    This retrieves relevant document chunks and uses an LLM to generate an answer.
    
    Requires either:
    - Ollama running locally (ollama serve)
    - ANTHROPIC_API_KEY or OPENAI_API_KEY environment variable
    """
    if config_path:
        set_config(Config.load(config_path))
    
    from cairnsearch.rag import RAGEngine
    
    engine = RAGEngine()
    
    # Check LLM availability
    if not engine.llm.is_available:
        console.print("[red]Error: No LLM available.[/red]")
        console.print("\nTo use RAG, you need one of:")
        console.print("  1. Ollama running: [cyan]ollama serve[/cyan]")
        console.print("  2. Set [cyan]ANTHROPIC_API_KEY[/cyan] environment variable")
        console.print("  3. Set [cyan]OPENAI_API_KEY[/cyan] environment variable")
        raise typer.Exit(1)
    
    file_path = str(file.resolve()) if file else None
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task("Thinking...", total=None)
        response = engine.ask(question, top_k=top_k, file_path_filter=file_path)
    
    # Display answer
    console.print(Panel(
        response.answer,
        title="[bold]Answer[/bold]",
        border_style="green",
    ))
    
    # Display sources
    if response.sources:
        console.print("\n[bold]Sources:[/bold]")
        for i, source in enumerate(response.sources[:5], 1):
            console.print(f"  {i}. [blue]{source.filename}[/blue] (score: {source.score:.2f})")
            console.print(f"     [dim]{source.content[:100]}...[/dim]")
    
    console.print(f"\n[dim]Took {response.took_ms}ms[/dim]")


@app.command()
def rag_index(
    config_path: Optional[Path] = typer.Option(None, "--config", "-c", help="Config file path"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """
    Index all documents for RAG (chunking + embeddings).
    
    This creates vector embeddings for semantic search.
    Run this after initial indexing or when you want to enable RAG features.
    """
    setup_logging(verbose)
    
    if config_path:
        set_config(Config.load(config_path))
    
    from cairnsearch.rag import RAGEngine
    from cairnsearch.db import Database
    
    db = Database()
    engine = RAGEngine()
    
    # Get all indexed documents
    with db.connection() as conn:
        docs = conn.execute(
            "SELECT id, file_path, filename, content FROM documents WHERE content IS NOT NULL"
        ).fetchall()
    
    console.print(f"[bold]Indexing {len(docs)} documents for RAG...[/bold]\n")
    
    total_chunks = 0
    with Progress(console=console) as progress:
        task = progress.add_task("Indexing...", total=len(docs))
        
        for doc in docs:
            doc_id, file_path, filename, content = doc
            chunks = engine.index_document(doc_id, file_path, filename, content)
            total_chunks += chunks
            progress.advance(task)
    
    console.print(f"\n[green]✓ Indexed {total_chunks} chunks from {len(docs)} documents[/green]")
    
    # Show stats
    stats = engine.get_stats()
    console.print(f"\nVector store: {stats['vector_store']['total_chunks']} chunks")


@app.command()
def rag_status(
    config_path: Optional[Path] = typer.Option(None, "--config", "-c", help="Config file path"),
):
    """Show RAG system status."""
    if config_path:
        set_config(Config.load(config_path))
    
    from cairnsearch.rag import RAGEngine, get_rag_config
    from cairnsearch.rag.embeddings import get_embedder
    
    config = get_rag_config()
    engine = RAGEngine()
    stats = engine.get_stats()
    
    console.print(Panel.fit("[bold]RAG Status[/bold]"))
    
    # LLM Status
    llm_status = "[green]✓ Available[/green]" if engine.llm.is_available else "[red]✗ Not available[/red]"
    console.print(f"\nLLM Provider: {config.llm_provider.value} {llm_status}")
    if config.llm_provider.value == "ollama":
        console.print(f"  Model: {config.ollama_model}")
        console.print(f"  URL: {config.ollama_base_url}")
    
    # Embeddings with test
    emb_available = False
    emb_error = None
    try:
        embedder = get_embedder()
        test_result = embedder.embed("test")
        if test_result and len(test_result) > 0:
            emb_available = True
    except Exception as e:
        emb_error = str(e)
    
    emb_status = "[green]✓ Available[/green]" if emb_available else "[red]✗ Not available[/red]"
    console.print(f"\nEmbeddings: {config.embedding_provider.value} {emb_status}")
    console.print(f"  Model: {config.embedding_model}")
    if emb_error:
        console.print(f"  [red]Error: {emb_error}[/red]")
    
    # Vector store
    vs = stats["vector_store"]
    console.print(f"\nVector Store:")
    console.print(f"  Chunks: {vs['total_chunks']}")
    console.print(f"  Documents: {vs['total_documents']}")
    
    # Settings
    console.print(f"\nSettings:")
    console.print(f"  Chunk size: {config.chunk_size} tokens")
    console.print(f"  Top-K: {config.top_k}")
    console.print(f"  Hybrid search: {config.hybrid_search}")


@app.command()
def debug(
    doc_id: Optional[int] = typer.Option(None, "--doc", "-d", help="Document ID to inspect"),
    file: Optional[Path] = typer.Option(None, "--file", "-f", help="File path to inspect"),
    show_text: bool = typer.Option(False, "--text", "-t", help="Show full extracted text"),
    show_chunks: bool = typer.Option(False, "--chunks", help="Show RAG chunks"),
):
    """
    Debug extraction and RAG data for a document.
    
    Examples:
    
        cairnsearch debug --doc 1
        
        cairnsearch debug --file ~/Documents/report.pdf --text
        
        cairnsearch debug --doc 1 --chunks
    """
    from cairnsearch.db import Database
    
    db = Database()
    
    # Find document
    if doc_id:
        with db.connection() as conn:
            row = conn.execute(
                "SELECT id, file_path, filename, file_type, content, page_count, extraction_method "
                "FROM documents WHERE id = ?", (doc_id,)
            ).fetchone()
    elif file:
        file_path = str(file.expanduser().resolve())
        with db.connection() as conn:
            row = conn.execute(
                "SELECT id, file_path, filename, file_type, content, page_count, extraction_method "
                "FROM documents WHERE file_path = ?", (file_path,)
            ).fetchone()
    else:
        console.print("[red]Please provide --doc or --file[/red]")
        raise typer.Exit(1)
    
    if not row:
        console.print("[red]Document not found in index[/red]")
        raise typer.Exit(1)
    
    doc_id, file_path, filename, file_type, content, page_count, extraction_method = row
    
    console.print(Panel.fit(f"[bold]Document Debug: {filename}[/bold]"))
    
    # Basic info table
    table = Table(title="Document Metadata")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("ID", str(doc_id))
    table.add_row("Path", file_path)
    table.add_row("Type", file_type.upper() if file_type else "N/A")
    table.add_row("Pages", str(page_count) if page_count else "N/A")
    table.add_row("Extraction Method", extraction_method or "direct")
    table.add_row("Content Length", f"{len(content):,} chars" if content else "0")
    table.add_row("Word Count", f"{len(content.split()):,}" if content else "0")
    
    console.print(table)
    
    # Text preview
    if content:
        preview_len = 2000 if show_text else 500
        preview = content[:preview_len]
        if len(content) > preview_len:
            preview += f"\n\n... ({len(content) - preview_len:,} more characters)"
        
        console.print("\n[bold]Extracted Text:[/bold]")
        console.print(Panel(preview, border_style="dim"))
    
    # RAG chunks
    if show_chunks:
        try:
            from cairnsearch.rag import VectorStore
            vs = VectorStore()
            
            import sqlite3
            conn = sqlite3.connect(vs.db_path)
            chunks = conn.execute(
                "SELECT chunk_id, chunk_index, content FROM chunks WHERE doc_id = ? ORDER BY chunk_index",
                (doc_id,)
            ).fetchall()
            conn.close()
            
            console.print(f"\n[bold]RAG Chunks: {len(chunks)}[/bold]")
            
            for chunk_id, chunk_index, chunk_content in chunks[:10]:
                console.print(f"\n[cyan]Chunk {chunk_index}:[/cyan]")
                preview = chunk_content[:300] + "..." if len(chunk_content) > 300 else chunk_content
                console.print(Panel(preview, border_style="dim"))
            
            if len(chunks) > 10:
                console.print(f"\n[dim]... and {len(chunks) - 10} more chunks[/dim]")
                
        except Exception as e:
            console.print(f"[yellow]Could not load chunks: {e}[/yellow]")


@app.command()
def list_docs(
    limit: int = typer.Option(20, "--limit", "-n", help="Number of documents to show"),
):
    """List indexed documents with their IDs."""
    from cairnsearch.db import Database
    
    db = Database()
    
    with db.connection() as conn:
        rows = conn.execute(
            "SELECT id, filename, file_type, page_count, LENGTH(content) as content_len, extraction_method "
            "FROM documents ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    
    if not rows:
        console.print("[yellow]No documents indexed[/yellow]")
        return
    
    table = Table(title=f"Indexed Documents (showing {len(rows)})")
    table.add_column("ID", style="dim")
    table.add_column("Filename", style="cyan")
    table.add_column("Type", style="green")
    table.add_column("Pages")
    table.add_column("Content")
    table.add_column("Method")
    
    for row in rows:
        doc_id, filename, file_type, page_count, content_len, method = row
        table.add_row(
            str(doc_id),
            filename[:40] + "..." if len(filename) > 40 else filename,
            (file_type or "").upper(),
            str(page_count) if page_count else "-",
            f"{content_len:,}" if content_len else "-",
            method or "direct"
        )
    
    console.print(table)


if __name__ == "__main__":
    app()
