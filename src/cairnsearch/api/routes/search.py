"""Search API routes."""
from fastapi import APIRouter, Query
from pydantic import BaseModel
from pathlib import Path
import os

from cairnsearch.search import SearchEngine
from cairnsearch.db import SearchResponse


router = APIRouter()


class SearchRequest(BaseModel):
    """Search request body."""
    query: str
    page: int = 1
    page_size: int = 20


@router.get("/search")
async def search(
    q: str = Query(..., description="Search query"),
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Results per page"),
    type: str = Query(None, description="Filter by file type"),
) -> dict:
    """
    Search indexed documents.
    
    Query syntax:
    - Keywords: `contract texas`
    - Phrases: `"state of texas"`
    - Boolean: `contract AND texas`, `contract OR agreement`, `contract NOT amendment`
    - Field search: `filename:report`, `content:summary`
    - File type: `type:pdf`
    - Author: `author:smith`
    - Date filters: `after:2022-01-01`, `before:2023-12-31`, `year:2023`
    
    Example: `filename:contract "state of texas" after:2022-01-01 type:pdf`
    """
    # Add type filter to query if specified
    query = q
    if type:
        query = f"{q} type:{type}"
    
    engine = SearchEngine()
    result = engine.search(query, page=page, page_size=size)
    
    # Enhance results with file metadata
    enhanced_results = []
    for r in result.results:
        # Get file stats if available
        file_size = None
        modified_date = None
        try:
            path = Path(r.file_path)
            if path.exists():
                stat = path.stat()
                file_size = stat.st_size
                modified_date = stat.st_mtime
        except:
            pass
        
        enhanced_results.append({
            "id": r.id,
            "file_path": r.file_path,
            "filename": r.filename,
            "file_type": r.file_type,
            "score": r.score,
            "snippets": r.snippets,
            "doc_title": r.doc_title,
            "doc_author": r.doc_author,
            "doc_created": r.doc_created,
            "page_count": r.page_count,
            "size_bytes": file_size,
            "modified_date": modified_date,
        })
    
    return {
        "query": result.query,
        "total": result.total,
        "page": result.page,
        "page_size": result.page_size,
        "took_ms": result.took_ms,
        "results": enhanced_results,
    }


@router.get("/suggest")
async def suggest(
    q: str = Query(..., min_length=1, description="Search prefix"),
    limit: int = Query(10, ge=1, le=50, description="Max suggestions"),
) -> dict:
    """Get search suggestions based on prefix."""
    engine = SearchEngine()
    suggestions = engine.suggest(q, limit=limit)
    return {"suggestions": suggestions}
