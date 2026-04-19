"""Folder browsing API routes."""
import os
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List


router = APIRouter()


class FolderInfo(BaseModel):
    """Folder information."""
    name: str
    path: str
    is_dir: bool = True


class BrowseResponse(BaseModel):
    """Browse response."""
    path: str
    parent: Optional[str]
    folders: List[FolderInfo]


@router.get("/folders/browse")
async def browse_folders(
    path: str = Query(default="/", description="Path to browse")
) -> BrowseResponse:
    """
    Browse filesystem folders.
    
    Returns list of subdirectories for the given path.
    """
    # Expand user home directory
    if path.startswith("~"):
        path = os.path.expanduser(path)
    
    # Handle root path
    if not path or path == "/":
        # On macOS/Linux, show common starting points
        home = Path.home()
        folders = []
        
        # Add home directory
        folders.append(FolderInfo(name="Home", path=str(home)))
        
        # Add common directories if they exist
        common_dirs = [
            home / "Documents",
            home / "Desktop",
            home / "Downloads",
            Path("/Users") if os.name != "nt" else Path("C:/Users"),
            Path("/Volumes") if os.name != "nt" else None,
        ]
        
        for d in common_dirs:
            if d and d.exists() and d.is_dir():
                folders.append(FolderInfo(name=d.name, path=str(d)))
        
        return BrowseResponse(
            path="/",
            parent=None,
            folders=folders
        )
    
    # Resolve the path
    try:
        target = Path(path).resolve()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid path")
    
    if not target.exists():
        raise HTTPException(status_code=404, detail="Path not found")
    
    if not target.is_dir():
        raise HTTPException(status_code=400, detail="Path is not a directory")
    
    # Get subdirectories
    folders = []
    try:
        for item in sorted(target.iterdir()):
            # Skip hidden files/folders
            if item.name.startswith("."):
                continue
            
            # Only include directories
            if item.is_dir():
                try:
                    # Check if we can access it
                    list(item.iterdir())
                    folders.append(FolderInfo(
                        name=item.name,
                        path=str(item)
                    ))
                except PermissionError:
                    # Skip inaccessible directories
                    pass
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied")
    
    # Get parent path
    parent = str(target.parent) if target.parent != target else None
    
    return BrowseResponse(
        path=str(target),
        parent=parent,
        folders=folders
    )


class IndexStartRequest(BaseModel):
    """Request to start indexing."""
    path: str
    file_types: Optional[List[str]] = None
    exclude_patterns: Optional[List[str]] = None


@router.post("/index/start")
async def start_indexing(request: IndexStartRequest) -> dict:
    """
    Start indexing a folder with progress tracking.
    
    Returns a session_id that can be used to track progress via SSE.
    """
    from cairnsearch.indexer import IndexManager
    from cairnsearch.api.routes.progress import (
        create_session, update_session, update_file_progress,
        IndexingStage, FileStatus, get_session, pause_session
    )
    import threading
    
    path = Path(request.path).expanduser().resolve()
    
    if not path.exists():
        raise HTTPException(status_code=404, detail="Path not found")
    
    if not path.is_dir():
        raise HTTPException(status_code=400, detail="Path must be a directory")
    
    # Get file types to include
    file_types = request.file_types or [
        'pdf', 'docx', 'doc', 'txt', 'md', 'html', 'htm',
        'xlsx', 'xls', 'csv', 'json', 'png', 'jpg', 'jpeg'
    ]
    
    # Get exclude patterns
    exclude_patterns = request.exclude_patterns or [
        'node_modules', '.git', '__pycache__', '.venv', 'venv', '.DS_Store'
    ]
    
    # First, scan and count files
    files_to_index = []
    for file_path in path.rglob("*"):
        if not file_path.is_file():
            continue
        
        # Check exclude patterns
        path_str = str(file_path)
        skip = False
        for pattern in exclude_patterns:
            if pattern in path_str:
                skip = True
                break
        
        if skip:
            continue
        
        # Check file type
        ext = file_path.suffix.lower().lstrip('.')
        if ext not in file_types:
            continue
        
        files_to_index.append(file_path)
    
    if not files_to_index:
        return {
            "message": "No files found to index",
            "path": str(path),
            "files_queued": 0
        }
    
    # Create progress session
    session_id = create_session(str(path), len(files_to_index))
    
    # Start indexing in background thread
    def index_files():
        index_manager = IndexManager()
        
        successful = 0
        warnings = 0
        failed = 0
        total_chunks = 0
        
        update_session(session_id, status=IndexingStage.EXTRACTING)
        
        for i, file_path in enumerate(files_to_index):
            # Check if cancelled or paused
            session = get_session(session_id)
            if session and session.is_cancelled:
                update_session(session_id, status=IndexingStage.CANCELLED)
                return
            
            # Wait if paused
            while session and session.is_paused:
                import time
                time.sleep(0.5)
                session = get_session(session_id)
                if session and session.is_cancelled:
                    update_session(session_id, status=IndexingStage.CANCELLED)
                    return
            
            filename = file_path.name
            
            # Update current file
            update_session(
                session_id,
                current_file=filename,
                current_stage="extracting"
            )
            
            # Update file progress - started
            update_file_progress(
                session_id,
                str(file_path),
                filename,
                FileStatus.PROCESSING,
                stage="extracting"
            )
            
            import time
            start_time = time.time()
            
            try:
                # Index the file
                success = index_manager.index_file(file_path)
                
                elapsed_ms = (time.time() - start_time) * 1000
                
                if success:
                    successful += 1
                    update_file_progress(
                        session_id,
                        str(file_path),
                        filename,
                        FileStatus.SUCCESS,
                        time_taken_ms=elapsed_ms,
                        chunks_created=1  # Approximate
                    )
                else:
                    failed += 1
                    update_file_progress(
                        session_id,
                        str(file_path),
                        filename,
                        FileStatus.FAILED,
                        error_message="Indexing returned false",
                        time_taken_ms=elapsed_ms
                    )
            
            except Exception as e:
                failed += 1
                elapsed_ms = (time.time() - start_time) * 1000
                update_file_progress(
                    session_id,
                    str(file_path),
                    filename,
                    FileStatus.FAILED,
                    error_message=str(e)[:100],
                    time_taken_ms=elapsed_ms
                )
            
            # Update session progress
            update_session(
                session_id,
                processed_files=i + 1,
                successful_files=successful,
                warning_files=warnings,
                failed_files=failed,
                total_chunks=total_chunks
            )
        
        # Mark complete
        update_session(
            session_id,
            status=IndexingStage.COMPLETE,
            processed_files=len(files_to_index),
            successful_files=successful,
            warning_files=warnings,
            failed_files=failed,
            current_file=None
        )
    
    # Start background thread
    thread = threading.Thread(target=index_files, daemon=True)
    thread.start()
    
    return {
        "message": f"Indexing started for {len(files_to_index)} files",
        "path": str(path),
        "files_queued": len(files_to_index),
        "session_id": session_id
    }


# Folder storage file
def _get_folders_file():
    from cairnsearch.config import get_config
    config = get_config()
    return config.get_data_dir() / "folders.json"


def _load_folders() -> List[dict]:
    """Load saved folders list."""
    import json
    folders_file = _get_folders_file()
    if folders_file.exists():
        try:
            with open(folders_file) as f:
                return json.load(f)
        except:
            return []
    return []


def _save_folders(folders: List[dict]):
    """Save folders list."""
    import json
    folders_file = _get_folders_file()
    folders_file.parent.mkdir(parents=True, exist_ok=True)
    with open(folders_file, 'w') as f:
        json.dump(folders, f)


class FolderAddRequest(BaseModel):
    """Add folder request."""
    path: str


class FolderRemoveRequest(BaseModel):
    """Remove folder request."""
    path: str


@router.get("/folders")
async def list_folders() -> dict:
    """List all indexed folders."""
    folders = _load_folders()
    
    # Count files in each folder
    result = []
    for folder in folders:
        path = folder if isinstance(folder, str) else folder.get('path', '')
        try:
            p = Path(path)
            if p.exists():
                count = sum(1 for _ in p.rglob("*") if _.is_file())
                result.append({"path": path, "count": count})
            else:
                result.append({"path": path, "count": 0, "missing": True})
        except:
            result.append({"path": path, "count": 0})
    
    return {"folders": result}


@router.post("/folders")
async def add_folder(request: FolderAddRequest) -> dict:
    """Add a folder to the index list."""
    path = Path(request.path).expanduser().resolve()
    
    if not path.exists():
        raise HTTPException(status_code=404, detail="Path not found")
    
    if not path.is_dir():
        raise HTTPException(status_code=400, detail="Path must be a directory")
    
    folders = _load_folders()
    path_str = str(path)
    
    # Check if already exists
    existing = [f if isinstance(f, str) else f.get('path') for f in folders]
    if path_str in existing:
        return {"message": "Folder already added", "path": path_str}
    
    folders.append({"path": path_str})
    _save_folders(folders)
    
    return {"message": "Folder added", "path": path_str}


@router.delete("/folders")
async def remove_folder(request: FolderRemoveRequest) -> dict:
    """Remove a folder from the index list."""
    folders = _load_folders()
    path_str = request.path
    
    # Filter out the folder
    new_folders = [
        f for f in folders 
        if (f if isinstance(f, str) else f.get('path')) != path_str
    ]
    
    if len(new_folders) == len(folders):
        raise HTTPException(status_code=404, detail="Folder not found")
    
    _save_folders(new_folders)
    
    return {"message": "Folder removed", "path": path_str}
