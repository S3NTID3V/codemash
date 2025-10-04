import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from queue import Queue

class RepoChangeHandler(FileSystemEventHandler):
    """
    Handles file system events from watchdog and puts them into a thread-safe queue.
    This prevents direct access to Streamlit's session state from a background thread.
    """
    def __init__(self, event_queue: Queue):
        """
        Initializes the handler with a queue for communication.

        Args:
            event_queue: A thread-safe queue to pass event data to the main thread.
        """
        super().__init__()
        self.event_queue = event_queue

    def on_any_event(self, event):
        """
        Catches all file system events and puts a dictionary of event data onto the queue.

        Args:
            event: The file system event object from watchdog.
        """
        event_data = {
            "event_type": event.event_type,
            "src_path": event.src_path,
            "is_directory": event.is_directory,
            "timestamp": time.time()
        }
        self.event_queue.put(event_data)


def start_monitoring(path: str, event_queue: Queue) -> Observer:
    """
    Starts the repository monitoring in a background thread.

    Args:
        path: The absolute path to the directory to monitor.
        event_queue: The queue to which file system events will be sent.

    Returns:
        The watchdog observer instance, which can be used to stop the monitoring.
    """
    event_handler = RepoChangeHandler(event_queue)
    observer = Observer()
    observer.schedule(event_handler, path, recursive=True)
    observer.start()
    return observer

def stop_monitoring(observer: Observer):
    """
    Stops the repository monitoring thread gracefully.

    Args:
        observer: The observer instance to stop.
    """
    if observer and observer.is_alive():
        observer.stop()
        observer.join() # Wait for the thread to terminate