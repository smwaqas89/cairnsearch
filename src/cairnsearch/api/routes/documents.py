"""Documents API routes."""
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
import subprocess
import platform
import logging

from cairnsearch.search import SearchEngine


router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/documents/{doc_id}")
async def get_document(doc_id: int) -> dict:
    """Get document details and content."""
    engine = SearchEngine()
    doc = engine.get_document(doc_id)
    
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    return doc


@router.get("/documents/{doc_id}/file")
async def download_file(doc_id: int):
    """Download original file."""
    engine = SearchEngine()
    doc = engine.get_document(doc_id)
    
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    file_path = Path(doc["file_path"])
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")
    
    return FileResponse(
        path=file_path,
        filename=doc["filename"],
        media_type="application/octet-stream",
    )


@router.post("/documents/{doc_id}/open")
async def open_file(doc_id: int) -> dict:
    """Open file with system default application."""
    engine = SearchEngine()
    doc = engine.get_document(doc_id)
    
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    file_path = Path(doc["file_path"])
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")
    
    try:
        system = platform.system()
        if system == 'Darwin':  # macOS
            subprocess.Popen(['open', str(file_path)])
        elif system == 'Windows':
            subprocess.Popen(['start', '', str(file_path)], shell=True)
        else:  # Linux
            subprocess.Popen(['xdg-open', str(file_path)])
        
        return {"message": f"Opened {doc['filename']}", "file_path": str(file_path)}
    except Exception as e:
        logger.error(f"Failed to open file: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to open file: {str(e)}")


@router.post("/documents/open-path")
async def open_file_by_path(file_path: str = Query(..., description="Path to the file to open")) -> dict:
    """Open file by path with system default application."""
    path = Path(file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")
    
    try:
        system = platform.system()
        if system == 'Darwin':  # macOS
            subprocess.Popen(['open', str(path)])
        elif system == 'Windows':
            subprocess.Popen(['start', '', str(path)], shell=True)
        else:  # Linux
            subprocess.Popen(['xdg-open', str(path)])
        
        return {"message": f"Opened {path.name}", "file_path": str(path)}
    except Exception as e:
        logger.error(f"Failed to open file: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to open file: {str(e)}")


@router.get("/documents/open")
async def open_file_by_path_get(path: str = Query(..., description="Path to the file to open")) -> dict:
    """Open file by path with system default application (GET version)."""
    file_path = Path(path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found on disk: {path}")
    
    try:
        system = platform.system()
        if system == 'Darwin':  # macOS
            subprocess.Popen(['open', str(file_path)])
        elif system == 'Windows':
            subprocess.Popen(['start', '', str(file_path)], shell=True)
        else:  # Linux
            subprocess.Popen(['xdg-open', str(file_path)])
        
        return {"message": f"Opened {file_path.name}", "file_path": str(file_path)}
    except Exception as e:
        logger.error(f"Failed to open file: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to open file: {str(e)}")
