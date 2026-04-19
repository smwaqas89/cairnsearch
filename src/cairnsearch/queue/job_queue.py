"""SQLite-backed job queue for async processing."""
from datetime import datetime
from typing import Optional
import logging

from cairnsearch.db import Database, Job


logger = logging.getLogger(__name__)


class JobQueue:
    """SQLite-backed job queue."""

    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()

    def enqueue(self, file_path: str, job_type: str = "index", priority: int = 0) -> int:
        """
        Add job to queue.
        
        Args:
            file_path: Path to file
            job_type: Type of job (index, reindex, delete)
            priority: Job priority (higher = more urgent)
            
        Returns:
            Job ID
        """
        # Set priority based on job type if not specified
        if priority == 0:
            priority = {"delete": 100, "reindex": 50, "index": 0}.get(job_type, 0)
        
        job_id = self.db.execute_write(
            """INSERT INTO job_queue (file_path, job_type, priority)
               VALUES (?, ?, ?)""",
            (file_path, job_type, priority)
        )
        logger.debug(f"Enqueued job {job_id}: {job_type} {file_path}")
        return job_id

    def dequeue(self) -> Optional[Job]:
        """
        Get next job from queue and mark as processing.
        
        Returns:
            Job if available, None otherwise
        """
        with self.db.connection() as conn:
            # Get highest priority pending job
            row = conn.execute("""
                SELECT * FROM job_queue
                WHERE status = 'pending' AND attempts < max_attempts
                ORDER BY priority DESC, created_at ASC
                LIMIT 1
            """).fetchone()
            
            if not row:
                return None
            
            job = Job.from_row(row)
            
            # Mark as processing
            conn.execute("""
                UPDATE job_queue
                SET status = 'processing', started_at = ?, attempts = attempts + 1
                WHERE id = ?
            """, (datetime.now().isoformat(), job.id))
            conn.commit()
            
            return job

    def complete(self, job_id: int, success: bool = True, error: Optional[str] = None) -> None:
        """
        Mark job as completed.
        
        Args:
            job_id: Job ID
            success: Whether job succeeded
            error: Error message if failed
        """
        status = "done" if success else "failed"
        with self.db.connection() as conn:
            conn.execute("""
                UPDATE job_queue
                SET status = ?, completed_at = ?, error_msg = ?
                WHERE id = ?
            """, (status, datetime.now().isoformat(), error, job_id))
            conn.commit()
        logger.debug(f"Job {job_id} completed: {status}")

    def retry(self, job_id: int, error: str) -> None:
        """
        Mark job for retry.
        
        Args:
            job_id: Job ID
            error: Error message
        """
        with self.db.connection() as conn:
            conn.execute("""
                UPDATE job_queue
                SET status = 'pending', error_msg = ?
                WHERE id = ?
            """, (error, job_id))
            conn.commit()
        logger.debug(f"Job {job_id} marked for retry")

    def get_pending_count(self) -> int:
        """Get number of pending jobs."""
        rows = self.db.execute(
            "SELECT COUNT(*) FROM job_queue WHERE status = 'pending'"
        )
        return rows[0][0]

    def get_stats(self) -> dict:
        """Get queue statistics."""
        with self.db.connection() as conn:
            pending = conn.execute(
                "SELECT COUNT(*) FROM job_queue WHERE status = 'pending'"
            ).fetchone()[0]
            processing = conn.execute(
                "SELECT COUNT(*) FROM job_queue WHERE status = 'processing'"
            ).fetchone()[0]
            done = conn.execute(
                "SELECT COUNT(*) FROM job_queue WHERE status = 'done'"
            ).fetchone()[0]
            failed = conn.execute(
                "SELECT COUNT(*) FROM job_queue WHERE status = 'failed'"
            ).fetchone()[0]
        
        return {
            "pending": pending,
            "processing": processing,
            "done": done,
            "failed": failed,
        }

    def clear_completed(self) -> int:
        """Remove completed jobs from queue. Returns count deleted."""
        with self.db.connection() as conn:
            cursor = conn.execute(
                "DELETE FROM job_queue WHERE status IN ('done', 'failed')"
            )
            conn.commit()
            return cursor.rowcount

    def clear_all(self) -> int:
        """Remove all jobs from queue. Returns count deleted."""
        with self.db.connection() as conn:
            cursor = conn.execute("DELETE FROM job_queue")
            conn.commit()
            return cursor.rowcount
