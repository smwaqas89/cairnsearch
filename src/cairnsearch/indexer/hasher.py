"""File hashing utilities for change detection."""
import hashlib
from pathlib import Path


def hash_file(file_path: Path, algorithm: str = "sha256", chunk_size: int = 65536) -> str:
    """
    Compute hash of file contents.
    
    Args:
        file_path: Path to file
        algorithm: Hash algorithm (sha256, md5, etc.)
        chunk_size: Bytes to read at a time
        
    Returns:
        Hex digest of file hash
    """
    hasher = hashlib.new(algorithm)
    with open(file_path, "rb") as f:
        while chunk := f.read(chunk_size):
            hasher.update(chunk)
    return hasher.hexdigest()


def file_changed(file_path: Path, stored_hash: str, algorithm: str = "sha256") -> bool:
    """
    Check if file has changed compared to stored hash.
    
    Args:
        file_path: Path to file
        stored_hash: Previously computed hash
        algorithm: Hash algorithm used
        
    Returns:
        True if file has changed (hash differs)
    """
    current_hash = hash_file(file_path, algorithm)
    return current_hash != stored_hash
