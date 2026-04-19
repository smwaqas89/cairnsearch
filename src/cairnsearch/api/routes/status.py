"""Status API routes."""
from fastapi import APIRouter

from cairnsearch.indexer import IndexManager


router = APIRouter()


@router.get("/status")
async def get_status() -> dict:
    """Get indexing and system status."""
    index_manager = IndexManager()
    index_stats = index_manager.get_stats()
    
    status = {
        "indexed_count": index_stats["indexed_count"],
        "pending": index_stats["pending"],
        "failed": index_stats["failed"],
        "by_type": index_stats["by_type"],
        "chunks": 0,
    }
    
    # Get vector store stats
    try:
        from cairnsearch.rag import VectorStore
        vector_store = VectorStore()
        vs_stats = vector_store.get_stats()
        status["chunks"] = vs_stats.get("total_chunks", 0)
    except:
        pass
    
    # Import here to avoid circular import
    try:
        from cairnsearch.api import app as app_module
        worker_pool = app_module.worker_pool
        if worker_pool:
            worker_stats = worker_pool.get_stats()
            status["workers"] = {
                "count": worker_stats["workers"],
                "running": worker_stats["running"],
                "queue": worker_stats["queue"],
            }
    except:
        pass
    
    return status


@router.get("/health")
async def health() -> dict:
    """Health check endpoint."""
    return {"status": "ok"}
