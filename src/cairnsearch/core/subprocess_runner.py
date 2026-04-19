"""Subprocess runner for safe native/C-based processing."""
import json
import logging
import os
import signal
import subprocess
import sys
import tempfile
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Callable, Any, TypeVar
from functools import wraps

from .exceptions import SubprocessCrash, ProcessingError


logger = logging.getLogger(__name__)


@dataclass
class SubprocessResult:
    """Result from subprocess execution."""
    success: bool
    return_value: Any = None
    error: Optional[str] = None
    exit_code: int = 0
    signal: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    execution_time_ms: float = 0


class SubprocessRunner:
    """
    Runs processing in isolated subprocesses to prevent crashes from
    affecting the main process (e.g., SIGSEGV from native PDF libraries).
    """
    
    SIGNAL_NAMES = {
        signal.SIGSEGV: "SIGSEGV (Segmentation fault)",
        signal.SIGABRT: "SIGABRT (Aborted)",
        signal.SIGFPE: "SIGFPE (Floating point exception)",
        signal.SIGILL: "SIGILL (Illegal instruction)",
        signal.SIGBUS: "SIGBUS (Bus error)",
    }
    
    def __init__(
        self,
        timeout: int = 300,  # 5 minutes default
        max_retries: int = 1,
        capture_output: bool = True,
    ):
        self.timeout = timeout
        self.max_retries = max_retries
        self.capture_output = capture_output
    
    def run(
        self,
        func: Callable,
        *args,
        **kwargs,
    ) -> SubprocessResult:
        """
        Run a function in a subprocess.
        
        The function and its arguments must be picklable.
        """
        import time
        import pickle
        
        start_time = time.time()
        
        # Create temp files for input/output
        with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.pkl') as f_in:
            input_path = f_in.name
            pickle.dump({
                'func': func,
                'args': args,
                'kwargs': kwargs,
            }, f_in)
        
        output_path = input_path.replace('.pkl', '_out.pkl')
        
        try:
            # Build subprocess command
            runner_script = self._get_runner_script()
            cmd = [
                sys.executable,
                '-c',
                runner_script,
                input_path,
                output_path,
            ]
            
            # Run subprocess
            result = subprocess.run(
                cmd,
                timeout=self.timeout,
                capture_output=self.capture_output,
                text=True,
            )
            
            execution_time = (time.time() - start_time) * 1000
            
            # Check for signals (negative return code)
            if result.returncode < 0:
                sig = -result.returncode
                sig_name = self.SIGNAL_NAMES.get(sig, f"Signal {sig}")
                logger.error(f"Subprocess crashed with {sig_name}")
                return SubprocessResult(
                    success=False,
                    error=f"Subprocess crashed: {sig_name}",
                    exit_code=result.returncode,
                    signal=sig,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    execution_time_ms=execution_time,
                )
            
            # Check for non-zero exit
            if result.returncode != 0:
                return SubprocessResult(
                    success=False,
                    error=f"Subprocess exited with code {result.returncode}",
                    exit_code=result.returncode,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    execution_time_ms=execution_time,
                )
            
            # Read output
            if os.path.exists(output_path):
                with open(output_path, 'rb') as f_out:
                    output_data = pickle.load(f_out)
                
                if output_data.get('success'):
                    return SubprocessResult(
                        success=True,
                        return_value=output_data.get('result'),
                        exit_code=0,
                        stdout=result.stdout,
                        stderr=result.stderr,
                        execution_time_ms=execution_time,
                    )
                else:
                    return SubprocessResult(
                        success=False,
                        error=output_data.get('error', 'Unknown error'),
                        exit_code=0,
                        stdout=result.stdout,
                        stderr=result.stderr,
                        execution_time_ms=execution_time,
                    )
            else:
                return SubprocessResult(
                    success=False,
                    error="No output from subprocess",
                    exit_code=result.returncode,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    execution_time_ms=execution_time,
                )
                
        except subprocess.TimeoutExpired:
            execution_time = (time.time() - start_time) * 1000
            logger.error(f"Subprocess timed out after {self.timeout}s")
            return SubprocessResult(
                success=False,
                error=f"Subprocess timed out after {self.timeout}s",
                exit_code=-1,
                execution_time_ms=execution_time,
            )
        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            logger.exception(f"Error running subprocess: {e}")
            return SubprocessResult(
                success=False,
                error=str(e),
                exit_code=-1,
                execution_time_ms=execution_time,
            )
        finally:
            # Cleanup temp files
            for path in [input_path, output_path]:
                try:
                    if os.path.exists(path):
                        os.unlink(path)
                except:
                    pass
    
    def run_with_retry(
        self,
        func: Callable,
        *args,
        **kwargs,
    ) -> SubprocessResult:
        """Run with automatic retry on failure."""
        last_result = None
        
        for attempt in range(self.max_retries + 1):
            result = self.run(func, *args, **kwargs)
            
            if result.success:
                return result
            
            last_result = result
            
            # Don't retry on certain errors
            if result.signal in [signal.SIGSEGV, signal.SIGBUS]:
                logger.warning(f"Not retrying after crash: {result.error}")
                break
            
            if attempt < self.max_retries:
                logger.info(f"Retrying subprocess (attempt {attempt + 2}/{self.max_retries + 1})")
        
        return last_result
    
    def _get_runner_script(self) -> str:
        """Get the subprocess runner script."""
        return '''
import sys
import pickle
import traceback

def main():
    input_path = sys.argv[1]
    output_path = sys.argv[2]
    
    try:
        with open(input_path, 'rb') as f:
            data = pickle.load(f)
        
        func = data['func']
        args = data['args']
        kwargs = data['kwargs']
        
        result = func(*args, **kwargs)
        
        with open(output_path, 'wb') as f:
            pickle.dump({'success': True, 'result': result}, f)
            
    except Exception as e:
        with open(output_path, 'wb') as f:
            pickle.dump({
                'success': False, 
                'error': str(e),
                'traceback': traceback.format_exc()
            }, f)
        sys.exit(0)  # Exit cleanly even on error

if __name__ == '__main__':
    main()
'''


T = TypeVar('T')


def run_in_subprocess(
    timeout: int = 300,
    max_retries: int = 1,
    raise_on_failure: bool = True,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator to run a function in a subprocess.
    
    Usage:
        @run_in_subprocess(timeout=60)
        def process_pdf(file_path: str) -> dict:
            # This runs in a subprocess, crashes won't affect main process
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            runner = SubprocessRunner(
                timeout=timeout,
                max_retries=max_retries,
            )
            
            result = runner.run_with_retry(func, *args, **kwargs)
            
            if result.success:
                return result.return_value
            
            if raise_on_failure:
                if result.signal:
                    raise SubprocessCrash(
                        message=result.error or "Subprocess crashed",
                        exit_code=result.exit_code,
                        signal=result.signal,
                        stdout=result.stdout,
                        stderr=result.stderr,
                    )
                else:
                    raise ProcessingError(
                        message=result.error or "Subprocess failed",
                        stage="subprocess",
                        recoverable=True,
                        details=result.stderr,
                    )
            
            return None
        
        return wrapper
    return decorator


def is_crash_signal(exit_code: int) -> bool:
    """Check if exit code indicates a crash signal."""
    if exit_code >= 0:
        return False
    
    sig = -exit_code
    return sig in [
        signal.SIGSEGV,
        signal.SIGABRT,
        signal.SIGFPE,
        signal.SIGILL,
        signal.SIGBUS,
    ]
