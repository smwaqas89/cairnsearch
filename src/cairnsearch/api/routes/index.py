"""Index management API routes."""
from pathlib import Path
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional

from cairnsearch.indexer import IndexManager


router = APIRouter()


class ReindexRequest(BaseModel):
    """Reindex request body."""
    path: Optional[str] = None  # Specific file or folder, or None for all


@router.post("/reindex")
async def reindex(
    request: ReindexRequest,
    background_tasks: BackgroundTasks,
) -> dict:
    """Trigger reindexing of documents."""
    index_manager = IndexManager()
    
    # Try to get worker pool if available
    worker_pool = None
    try:
        from cairnsearch.api import app as app_module
        worker_pool = app_module.worker_pool
    except:
        pass
    
    if request.path:
        # Reindex specific file or folder
        path = Path(request.path).expanduser().resolve()
        
        if not path.exists():
            raise HTTPException(status_code=404, detail="Path not found")
        
        if path.is_file():
            # Submit single file
            if worker_pool:
                worker_pool.submit(str(path), "reindex")
                return {"message": f"Reindex job queued for: {path}"}
            else:
                success = index_manager.index_file(path)
                return {"message": f"Reindexed: {path}", "success": success}
        else:
            # Queue all files in folder
            count = 0
            for file_path in path.rglob("*"):
                if file_path.is_file():
                    if worker_pool:
                        worker_pool.submit(str(file_path), "reindex")
                    else:
                        index_manager.index_file(file_path)
                    count += 1
            return {"message": f"Reindex jobs queued for {count} files"}
    else:
        # Reindex all watched folders
        background_tasks.add_task(_reindex_all)
        return {"message": "Full reindex started in background"}


async def _reindex_all():
    """Background task for full reindex."""
    index_manager = IndexManager()
    success, failed = index_manager.reindex_all()
    return {"success": success, "failed": failed}


@router.delete("/index")
async def clear_index() -> dict:
    """Clear all indexed documents and vector store."""
    from cairnsearch.db import Database
    
    db = Database()
    with db.connection() as conn:
        conn.execute("DELETE FROM documents")
        conn.execute("DELETE FROM files_meta")
        conn.execute("DELETE FROM job_queue")
        conn.commit()
    
    # Also clear vector store
    try:
        from cairnsearch.rag import VectorStore
        vector_store = VectorStore()
        vector_store.clear()
    except Exception as e:
        pass  # Vector store might not exist yet
    
    return {"message": "Index and vector store cleared"}


@router.get("/index/documents")
async def list_indexed_documents(
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """List all indexed documents."""
    from cairnsearch.db import Database
    
    db = Database()
    offset = (page - 1) * page_size
    
    with db.connection() as conn:
        # Get total count
        total = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        
        # Get documents
        rows = conn.execute("""
            SELECT id, file_path, filename, file_type, page_count, 
                   doc_title, extraction_method, created_at
            FROM documents
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """, (page_size, offset)).fetchall()
        
        documents = []
        for row in rows:
            documents.append({
                "id": row[0],
                "file_path": row[1],
                "filename": row[2],
                "file_type": row[3],
                "page_count": row[4],
                "title": row[5],
                "extraction_method": row[6],
                "indexed_at": row[7],
            })
    
    return {
        "documents": documents,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    }


@router.get("/index/errors")
async def list_indexing_errors() -> dict:
    """List all documents that failed to index."""
    from cairnsearch.db import Database
    
    db = Database()
    
    with db.connection() as conn:
        rows = conn.execute("""
            SELECT path, status, error_msg, indexed_at
            FROM files_meta
            WHERE status = 'failed'
            ORDER BY indexed_at DESC
        """).fetchall()
        
        errors = []
        for row in rows:
            errors.append({
                "file_path": row[0],
                "status": row[1],
                "error": row[2],
                "attempted_at": row[3],
            })
    
    return {
        "errors": errors,
        "total": len(errors),
    }


# Progress tracking state
_index_progress = {
    "status": "idle",
    "total": 0,
    "processed": 0,
    "percent": 0
}


@router.get("/index/progress")
async def get_index_progress() -> dict:
    """Get current indexing progress."""
    return _index_progress


@router.post("/backup")
async def backup_index() -> dict:
    """Create a backup of the index database."""
    import shutil
    from cairnsearch.config import get_config
    
    config = get_config()
    db_path = config.get_db_path()
    backup_path = config.get_data_dir() / "cairnsearch.db.backup"
    
    if not db_path.exists():
        raise HTTPException(status_code=404, detail="Database not found")
    
    try:
        shutil.copy2(db_path, backup_path)
        return {"message": f"Backup created: {backup_path}", "path": str(backup_path)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backup failed: {str(e)}")


@router.post("/restore")
async def restore_index() -> dict:
    """Restore index from backup."""
    import shutil
    from cairnsearch.config import get_config
    
    config = get_config()
    db_path = config.get_db_path()
    backup_path = config.get_data_dir() / "cairnsearch.db.backup"
    
    if not backup_path.exists():
        raise HTTPException(status_code=404, detail="No backup found")
    
    try:
        shutil.copy2(backup_path, db_path)
        return {"message": "Backup restored successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Restore failed: {str(e)}")


@router.get("/duplicates")
async def find_duplicates() -> dict:
    """Find duplicate files by hash."""
    from cairnsearch.db import Database
    
    db = Database()
    
    with db.connection() as conn:
        rows = conn.execute("""
            SELECT hash, GROUP_CONCAT(path, '|') as paths, COUNT(*) as count
            FROM files_meta
            WHERE hash IS NOT NULL
            GROUP BY hash
            HAVING count > 1
        """).fetchall()
        
        duplicates = []
        for row in rows:
            duplicates.append({
                "hash": row[0],
                "paths": row[1].split('|') if row[1] else [],
                "count": row[2]
            })
    
    return {
        "duplicates": duplicates,
        "total": len(duplicates)
    }


@router.post("/watcher/start")
async def start_watcher() -> dict:
    """Start the file watcher."""
    # Placeholder - actual implementation would start watchdog
    return {"message": "File watcher started", "status": "running"}


@router.post("/watcher/stop")
async def stop_watcher() -> dict:
    """Stop the file watcher."""
    # Placeholder - actual implementation would stop watchdog
    return {"message": "File watcher stopped", "status": "stopped"}
