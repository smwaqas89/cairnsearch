"""Quarantine manager for failed documents."""
import json
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from cairnsearch.config import get_config
from .models import FailureManifest, ProcessingStatus
from .exceptions import QuarantineError


logger = logging.getLogger(__name__)


class QuarantineManager:
    """Manages quarantine folder for failed documents."""
    
    MANIFEST_FILENAME = "failure_manifest.json"
    
    def __init__(self, quarantine_path: Optional[Path] = None):
        config = get_config()
        self.quarantine_path = quarantine_path or (
            config.get_data_dir() / "quarantine"
        )
        self.quarantine_path.mkdir(parents=True, exist_ok=True)
        
        # Index file for quick lookups
        self._index_path = self.quarantine_path / "index.json"
        self._load_index()
    
    def _load_index(self) -> None:
        """Load quarantine index."""
        if self._index_path.exists():
            try:
                with open(self._index_path, 'r') as f:
                    self._index = json.load(f)
            except:
                self._index = {}
        else:
            self._index = {}
    
    def _save_index(self) -> None:
        """Save quarantine index."""
        with open(self._index_path, 'w') as f:
            json.dump(self._index, f, indent=2)
    
    def _get_quarantine_folder(self, file_path: str) -> Path:
        """Get quarantine folder for a file."""
        import hashlib
        # Use hash to create unique folder name
        path_hash = hashlib.sha256(file_path.encode()).hexdigest()[:16]
        filename = Path(file_path).name
        folder_name = f"{filename}_{path_hash}"
        return self.quarantine_path / folder_name
    
    def quarantine(
        self,
        file_path: str,
        reason: str,
        stage: str,
        error_details: Optional[str] = None,
        stack_trace: Optional[str] = None,
        subprocess_exit_code: Optional[int] = None,
        copy_file: bool = True,
        metadata: Optional[dict] = None,
    ) -> FailureManifest:
        """
        Quarantine a failed document.
        
        Args:
            file_path: Path to the original file
            reason: Reason for quarantine
            stage: Processing stage where failure occurred
            error_details: Detailed error message
            stack_trace: Stack trace if available
            subprocess_exit_code: Exit code if subprocess crashed
            copy_file: Whether to copy the file to quarantine
            metadata: Additional metadata
            
        Returns:
            FailureManifest for the quarantined document
        """
        file_path = str(file_path)
        original_path = Path(file_path)
        
        if not original_path.exists() and copy_file:
            logger.warning(f"Cannot quarantine non-existent file: {file_path}")
            copy_file = False
        
        # Create quarantine folder
        q_folder = self._get_quarantine_folder(file_path)
        q_folder.mkdir(parents=True, exist_ok=True)
        
        # Check if already quarantined
        existing = self.get_manifest(file_path)
        retry_count = existing.retry_count if existing else 0
        
        # Create manifest
        manifest = FailureManifest(
            file_path=file_path,
            filename=original_path.name,
            reason=reason,
            stage=stage,
            timestamp=datetime.now(),
            retry_count=retry_count,
            error_details=error_details,
            stack_trace=stack_trace,
            subprocess_exit_code=subprocess_exit_code,
            recoverable=subprocess_exit_code is None or subprocess_exit_code >= 0,
            metadata=metadata or {},
        )
        
        # Copy file if requested
        if copy_file and original_path.exists():
            dest_path = q_folder / original_path.name
            try:
                shutil.copy2(original_path, dest_path)
                logger.info(f"Copied file to quarantine: {dest_path}")
            except Exception as e:
                logger.warning(f"Failed to copy file to quarantine: {e}")
        
        # Save manifest
        manifest_path = q_folder / self.MANIFEST_FILENAME
        with open(manifest_path, 'w') as f:
            f.write(manifest.to_json())
        
        # Update index
        self._index[file_path] = {
            "quarantine_folder": str(q_folder),
            "timestamp": manifest.timestamp.isoformat(),
            "reason": reason,
            "stage": stage,
            "retry_count": retry_count,
            "recoverable": manifest.recoverable,
        }
        self._save_index()
        
        logger.info(f"Quarantined document: {file_path} (reason: {reason})")
        return manifest
    
    def get_manifest(self, file_path: str) -> Optional[FailureManifest]:
        """Get failure manifest for a quarantined document."""
        file_path = str(file_path)
        
        if file_path not in self._index:
            return None
        
        q_folder = Path(self._index[file_path]["quarantine_folder"])
        manifest_path = q_folder / self.MANIFEST_FILENAME
        
        if not manifest_path.exists():
            return None
        
        try:
            with open(manifest_path, 'r') as f:
                data = json.load(f)
            return FailureManifest.from_dict(data)
        except Exception as e:
            logger.error(f"Failed to load manifest for {file_path}: {e}")
            return None
    
    def is_quarantined(self, file_path: str) -> bool:
        """Check if a file is quarantined."""
        return str(file_path) in self._index
    
    def can_retry(self, file_path: str) -> bool:
        """Check if a quarantined file can be retried."""
        manifest = self.get_manifest(file_path)
        if manifest is None:
            return True
        return manifest.recoverable and manifest.retry_count < manifest.max_retries
    
    def increment_retry(self, file_path: str) -> int:
        """Increment retry count for a quarantined document."""
        manifest = self.get_manifest(file_path)
        if manifest is None:
            return 0
        
        manifest.retry_count += 1
        
        # Update manifest
        q_folder = self._get_quarantine_folder(file_path)
        manifest_path = q_folder / self.MANIFEST_FILENAME
        with open(manifest_path, 'w') as f:
            f.write(manifest.to_json())
        
        # Update index
        self._index[str(file_path)]["retry_count"] = manifest.retry_count
        self._save_index()
        
        return manifest.retry_count
    
    def release(self, file_path: str, delete_copy: bool = True) -> bool:
        """
        Release a document from quarantine.
        
        Args:
            file_path: Path to the original file
            delete_copy: Whether to delete the quarantine copy
            
        Returns:
            True if released successfully
        """
        file_path = str(file_path)
        
        if file_path not in self._index:
            return False
        
        q_folder = Path(self._index[file_path]["quarantine_folder"])
        
        if delete_copy and q_folder.exists():
            try:
                shutil.rmtree(q_folder)
                logger.info(f"Deleted quarantine folder: {q_folder}")
            except Exception as e:
                logger.warning(f"Failed to delete quarantine folder: {e}")
        
        # Remove from index
        del self._index[file_path]
        self._save_index()
        
        logger.info(f"Released from quarantine: {file_path}")
        return True
    
    def skip_permanently(self, file_path: str) -> bool:
        """Mark a document to be permanently skipped."""
        manifest = self.get_manifest(file_path)
        if manifest is None:
            return False
        
        manifest.recoverable = False
        manifest.metadata["permanently_skipped"] = True
        manifest.metadata["skipped_at"] = datetime.now().isoformat()
        
        # Update manifest
        q_folder = self._get_quarantine_folder(file_path)
        manifest_path = q_folder / self.MANIFEST_FILENAME
        with open(manifest_path, 'w') as f:
            f.write(manifest.to_json())
        
        # Update index
        self._index[str(file_path)]["recoverable"] = False
        self._save_index()
        
        logger.info(f"Marked as permanently skipped: {file_path}")
        return True
    
    def list_quarantined(
        self,
        recoverable_only: bool = False,
        stage: Optional[str] = None,
        limit: int = 100,
    ) -> List[FailureManifest]:
        """List quarantined documents."""
        results = []
        
        for file_path, info in self._index.items():
            if recoverable_only and not info.get("recoverable", True):
                continue
            if stage and info.get("stage") != stage:
                continue
            
            manifest = self.get_manifest(file_path)
            if manifest:
                results.append(manifest)
            
            if len(results) >= limit:
                break
        
        return results
    
    def get_stats(self) -> dict:
        """Get quarantine statistics."""
        total = len(self._index)
        recoverable = sum(1 for info in self._index.values() if info.get("recoverable", True))
        
        by_stage = {}
        by_reason = {}
        
        for info in self._index.values():
            stage = info.get("stage", "unknown")
            by_stage[stage] = by_stage.get(stage, 0) + 1
            
            reason = info.get("reason", "unknown")[:50]  # Truncate long reasons
            by_reason[reason] = by_reason.get(reason, 0) + 1
        
        return {
            "total": total,
            "recoverable": recoverable,
            "permanently_skipped": total - recoverable,
            "by_stage": by_stage,
            "by_reason": by_reason,
        }
    
    def cleanup_old(self, days: int = 30) -> int:
        """Remove quarantine entries older than specified days."""
        from datetime import timedelta
        
        cutoff = datetime.now() - timedelta(days=days)
        removed = 0
        
        for file_path, info in list(self._index.items()):
            try:
                timestamp = datetime.fromisoformat(info["timestamp"])
                if timestamp < cutoff:
                    self.release(file_path, delete_copy=True)
                    removed += 1
            except:
                pass
        
        logger.info(f"Cleaned up {removed} old quarantine entries")
        return removed
