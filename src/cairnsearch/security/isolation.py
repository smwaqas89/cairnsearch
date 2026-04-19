"""Project and user isolation for multi-tenant security."""
import hashlib
import os
from pathlib import Path
from typing import Optional, List, Set
import logging


logger = logging.getLogger(__name__)


class ProjectIsolation:
    """
    Manages project/user isolation for security.
    
    Features:
    - Separate data directories per project
    - Access control validation
    - Path traversal protection
    """
    
    def __init__(self, base_path: Optional[Path] = None):
        from cairnsearch.config import get_config
        config = get_config()
        self.base_path = base_path or config.get_data_dir()
        self.base_path = self.base_path.resolve()
        self._allowed_projects: Set[str] = set()
    
    def get_project_path(self, project_id: str) -> Path:
        """Get isolated path for a project."""
        # Sanitize project ID
        safe_id = self._sanitize_id(project_id)
        project_path = self.base_path / "projects" / safe_id
        
        # Ensure path is within base
        project_path = project_path.resolve()
        if not str(project_path).startswith(str(self.base_path)):
            raise SecurityError(f"Path traversal detected: {project_id}")
        
        # Create if needed
        project_path.mkdir(parents=True, exist_ok=True)
        
        return project_path
    
    def get_user_path(self, user_id: str, project_id: Optional[str] = None) -> Path:
        """Get isolated path for a user within optional project."""
        safe_user = self._sanitize_id(user_id)
        
        if project_id:
            base = self.get_project_path(project_id)
        else:
            base = self.base_path / "users"
        
        user_path = base / safe_user
        user_path = user_path.resolve()
        
        # Validate path
        if not str(user_path).startswith(str(self.base_path)):
            raise SecurityError(f"Path traversal detected: {user_id}")
        
        user_path.mkdir(parents=True, exist_ok=True)
        return user_path
    
    def validate_path_access(
        self,
        path: Path,
        project_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> bool:
        """Validate that a path is accessible within project/user scope."""
        path = Path(path).resolve()
        
        # Must be within base path
        if not str(path).startswith(str(self.base_path)):
            return False
        
        # Check project scope
        if project_id:
            project_path = self.get_project_path(project_id)
            if not str(path).startswith(str(project_path)):
                return False
        
        # Check user scope
        if user_id:
            user_path = self.get_user_path(user_id, project_id)
            if not str(path).startswith(str(user_path)):
                return False
        
        return True
    
    def _sanitize_id(self, id_value: str) -> str:
        """Sanitize an ID for safe filesystem use."""
        # Remove dangerous characters
        safe = "".join(c for c in id_value if c.isalnum() or c in "-_.")
        
        # Limit length
        if len(safe) > 64:
            # Use hash for long IDs
            safe = hashlib.sha256(id_value.encode()).hexdigest()[:32]
        
        # Ensure non-empty
        if not safe:
            safe = hashlib.sha256(id_value.encode()).hexdigest()[:16]
        
        return safe
    
    def list_projects(self) -> List[str]:
        """List all project IDs."""
        projects_dir = self.base_path / "projects"
        if not projects_dir.exists():
            return []
        
        return [d.name for d in projects_dir.iterdir() if d.is_dir()]
    
    def delete_project(self, project_id: str) -> bool:
        """Delete a project and all its data."""
        import shutil
        
        project_path = self.get_project_path(project_id)
        
        if project_path.exists():
            shutil.rmtree(project_path)
            logger.info(f"Deleted project: {project_id}")
            return True
        
        return False
    
    def get_project_size(self, project_id: str) -> int:
        """Get total size of project data in bytes."""
        project_path = self.get_project_path(project_id)
        
        total = 0
        for path in project_path.rglob("*"):
            if path.is_file():
                total += path.stat().st_size
        
        return total


class SecurityError(Exception):
    """Security-related error."""
    pass
