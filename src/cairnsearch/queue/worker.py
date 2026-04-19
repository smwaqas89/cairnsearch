"""Worker pool for processing indexing jobs."""
import threading
import time
import logging
from typing import Optional, Callable

from cairnsearch.db import Database
from cairnsearch.indexer import IndexManager
from .job_queue import JobQueue


logger = logging.getLogger(__name__)


class Worker(threading.Thread):
    """Worker thread for processing jobs."""

    def __init__(
        self,
        worker_id: int,
        queue: JobQueue,
        index_manager: IndexManager,
        stop_event: threading.Event,
    ):
        super().__init__(daemon=True)
        self.worker_id = worker_id
        self.queue = queue
        self.index_manager = index_manager
        self.stop_event = stop_event
        self.name = f"Worker-{worker_id}"

    def run(self) -> None:
        """Main worker loop."""
        logger.info(f"{self.name} started")
        
        while not self.stop_event.is_set():
            try:
                job = self.queue.dequeue()
                
                if job is None:
                    # No jobs available, wait a bit
                    time.sleep(0.5)
                    continue
                
                logger.debug(f"{self.name} processing job {job.id}: {job.job_type} {job.file_path}")
                
                try:
                    if job.job_type == "index" or job.job_type == "reindex":
                        success = self.index_manager.index_file(job.file_path)
                    elif job.job_type == "delete":
                        success = self.index_manager.delete_file(job.file_path)
                    else:
                        logger.error(f"Unknown job type: {job.job_type}")
                        success = False
                    
                    if success:
                        self.queue.complete(job.id, success=True)
                    else:
                        if job.attempts < job.max_attempts:
                            self.queue.retry(job.id, "Processing failed")
                        else:
                            self.queue.complete(job.id, success=False, error="Max retries exceeded")
                            
                except Exception as e:
                    logger.exception(f"Error processing job {job.id}: {e}")
                    if job.attempts < job.max_attempts:
                        self.queue.retry(job.id, str(e))
                    else:
                        self.queue.complete(job.id, success=False, error=str(e))
                        
            except Exception as e:
                logger.exception(f"{self.name} error: {e}")
                time.sleep(1)
        
        logger.info(f"{self.name} stopped")


class WorkerPool:
    """Pool of worker threads for job processing."""

    def __init__(
        self,
        num_workers: int = 3,
        db: Optional[Database] = None,
    ):
        self.num_workers = num_workers
        self.db = db or Database()
        self.queue = JobQueue(self.db)
        self.index_manager = IndexManager(self.db)
        self.workers: list[Worker] = []
        self.stop_event = threading.Event()
        self._started = False

    def start(self) -> None:
        """Start worker threads."""
        if self._started:
            return
        
        self.stop_event.clear()
        
        for i in range(self.num_workers):
            worker = Worker(i, self.queue, self.index_manager, self.stop_event)
            worker.start()
            self.workers.append(worker)
        
        self._started = True
        logger.info(f"Worker pool started with {self.num_workers} workers")

    def stop(self, timeout: float = 5.0) -> None:
        """Stop worker threads."""
        if not self._started:
            return
        
        logger.info("Stopping worker pool...")
        self.stop_event.set()
        
        for worker in self.workers:
            worker.join(timeout=timeout)
        
        self.workers.clear()
        self._started = False
        logger.info("Worker pool stopped")

    def submit(self, file_path: str, job_type: str = "index", priority: int = 0) -> int:
        """Submit a job to the queue."""
        return self.queue.enqueue(file_path, job_type, priority)

    def get_stats(self) -> dict:
        """Get worker pool and queue statistics."""
        return {
            "workers": self.num_workers,
            "running": self._started,
            "queue": self.queue.get_stats(),
        }

    @property
    def is_running(self) -> bool:
        return self._started
