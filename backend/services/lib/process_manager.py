import subprocess
import threading
import queue
import time
import os
from typing import Optional, Tuple, Dict, Any
from dataclasses import dataclass
from .LAV_logger import logger
from .startup_progress import startup_progress

@dataclass
class ServerProcess:
    """Data class to hold server process information"""
    process: subprocess.Popen
    log_queue: queue.Queue
    ready_event: threading.Event
    port: int
    name: str

class ProcessManager:
    def __init__(self):
        self.processes: Dict[str, ServerProcess] = {}

    def _read_output(self, pipe, prefix: str, log_queue: queue.Queue, ready_event: threading.Event, ready_message: str):
        """Read output from a process pipe and handle logging"""
        try:
            for line in pipe:
                log_line = f"{prefix}: {line.strip()}"
                log_queue.put(log_line)
                logger.info(log_line)
                
                # Check for server ready message
                if ready_message in line:
                    ready_event.set()
        except Exception as e:
            logger.error(f"Error reading {prefix} output: {e}")

    def start_server_process(
        self,
        name: str,
        python_path: str,
        script_path: str,
        port: int,
        ready_message: str = "Uvicorn running on",
        timeout: int = 30,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None
    ) -> Tuple[bool, str]:
        """
        Start a Python server process using a python.exe.
        
        Args:
            name: Name of the server process
            python_path: Path to the virtual environment directory
            script_path: Path to the python script to run
            port: Port the server will run on
            ready_message: Message that indicates the server is ready
            timeout: Maximum time to wait for server to be ready (seconds)
            cwd: Working directory for the process
            env: Additional environment variables
            
        Returns:
            Tuple[bool, str]: (success, message)
        """
        start_time = time.time()
        startup_progress.show_step(f"Starting {name} Server")

        try:
            if not os.path.exists(python_path):
                msg = f"{name} server startup failed - virtual environment not found"
                startup_progress.complete_step(f"{msg} in {time.time() - start_time:.2f}s")
                return False, msg
                
            if not os.path.exists(script_path):
                msg = f"{name} server startup failed - server script not found"
                startup_progress.complete_step(f"{msg} in {time.time() - start_time:.2f}s")
                return False, msg

            # Create process tracking objects
            log_queue = queue.Queue()
            ready_event = threading.Event()
            ready_event.clear()
            
            # Start the server process
            process = subprocess.Popen(
                [python_path, script_path],
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True,
                env=env
            )
            
            # Start threads to read stdout and stderr
            threading.Thread(
                target=self._read_output,
                args=(process.stdout, name, log_queue, ready_event, ready_message),
                daemon=True
            ).start()
            
            threading.Thread(
                target=self._read_output,
                args=(process.stderr, f"{name}", log_queue, ready_event, ready_message),
                daemon=True
            ).start()
            
            # Store process information
            self.processes[name] = ServerProcess(
                process=process,
                log_queue=log_queue,
                ready_event=ready_event,
                port=port,
                name=name
            )
            
            # Wait for server to be ready with a timeout
            if ready_event.wait(timeout=timeout):
                msg = f"{name} server started successfully"
                startup_progress.complete_step(f"{msg} in {time.time() - start_time:.2f}s")
                return True, msg
            else:
                # If timeout occurs, stop the server
                self.stop_server(name)
                msg = f"{name} server failed to start within timeout period"
                startup_progress.complete_step(f"{msg} in {time.time() - start_time:.2f}s")
                return False, msg
                
        except Exception as e:
            logger.error(f"Error starting {name} server: {e}")
            msg = f"{name} server startup failed with error: {str(e)}"
            startup_progress.complete_step(f"{msg} in {time.time() - start_time:.2f}s")
            return False, msg

    def stop_server(self, name: str) -> bool:
        """Stop a server process by name"""
        if name in self.processes:
            try:
                self.processes[name].process.terminate()
                del self.processes[name]
                return True
            except Exception as e:
                logger.error(f"Error stopping {name} server: {e}")
        return False

    def stop_all_servers(self):
        """Stop all running server processes"""
        for name in list(self.processes.keys()):
            self.stop_server(name)

    def get_server_logs(self, name: str) -> list:
        """Get all logs from a server's queue"""
        if name in self.processes:
            logs = []
            while not self.processes[name].log_queue.empty():
                logs.append(self.processes[name].log_queue.get())
            return logs
        return []

    def is_server_running(self, name: str) -> bool:
        """Check if a server is running and responding"""
        if name in self.processes:
            return self.processes[name].process.poll() is None
        return False

# Create a global process manager instance
process_manager = ProcessManager() 