import atexit
import datetime
import logging
import queue
import threading
import time

from threading import Event
from concurrent.futures import ThreadPoolExecutor
from typing import Optional
from podonos.core.api import APIClient

# For logging
logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)


class UploadManager:
    """Concurrent file upload manager.
    Internally creates multiple threads, and manages the uploading status.
    """

    # Maximum number of uploader worker threads
    _max_workers: int
    # File path queue
    # TODO: use a file queue.
    _queue: Optional[queue.Queue] = None
    # Event to all the uploader threads
    _worker_event: Optional[Event] = None
    # Master daemon thread. Alive until the manager closes.
    _daemon_thread: Optional[threading.Thread] = None
    # API client for
    _api_client: Optional[APIClient] = None
    # Manager status. True if the manager is ready.
    _status: bool = False

    _upload_start: Optional[dict] = None
    _upload_finish: Optional[dict] = None

    def get_upload_time(self):
        if not self._upload_start or not self._upload_finish:
            raise ValueError("Upload Fail")

        return self._upload_start, self._upload_finish

    def __init__(self, api_client: APIClient, max_workers: int) -> None:
        self._max_workers = max_workers

        self._upload_start = dict()
        self._upload_finish = dict()
        self._api_client = api_client
        self._queue = queue.Queue()
        self._worker_event = Event()
        self._daemon_thread = threading.Thread(target=self._uploader_daemon, daemon=True)
        self._daemon_thread.start()
        self._status = True
        atexit.register(self.wait_and_close)

    def _uploader_daemon(self) -> None:
        log.debug(f"Uploader daemon is running")
        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            for index in range(self._max_workers):
                future = executor.submit(self._upload_worker, index, self._worker_event)
        log.debug(f"Uploader daemon is shutting down")
        executor.shutdown(wait=True)

    def _upload_worker(self, index, worker_event) -> None:
        if not (
            self._queue is not None
            and self._worker_event is not None
            and self._daemon_thread is not None
            and self._api_client is not None
            and self._upload_start is not None
            and self._upload_finish is not None
        ):
            raise ValueError("Upload Manager is not initialized")

        log.debug(f"Worker is {index} ready")
        while True:
            if not self._queue.empty():
                item = self._queue.get()
                presigned_url = item[0]
                remote_object_name = item[1]
                path = item[2]

                log.debug(f"Worker {index} uploading {path}")
                # Timestamp in ISO 8601.
                upload_start_at = datetime.datetime.now().astimezone().isoformat(timespec="milliseconds")
                self._api_client.put_file_presigned_url(presigned_url, path)
                upload_finish_at = datetime.datetime.now().astimezone().isoformat(timespec="milliseconds")
                log.debug(f"Worker {index} finished uploading {item}")

                self._upload_start[remote_object_name] = upload_start_at
                self._upload_finish[remote_object_name] = upload_finish_at
                self._queue.task_done()
            time.sleep(0.1)
            if worker_event.is_set():
                log.debug(f"Worker {index} is done")
                return

    def add_file_to_queue(self, presigned_url: str, remote_object_name: str, path: str) -> None:
        if not (
            self._queue is not None
            and self._worker_event is not None
            and self._daemon_thread is not None
            and self._api_client is not None
            and self._upload_start is not None
            and self._upload_finish is not None
        ):
            raise ValueError("Upload Manager is not initialized")

        log.debug(f"Added: {path}")
        self._queue.put((presigned_url, remote_object_name, path))

    def wait_and_close(self) -> bool:
        if not self._status:
            return False

        if not (self._queue is not None and self._worker_event is not None and self._daemon_thread is not None):
            raise ValueError("Upload Manager is not initialized")

        # Block until all tasks are done.
        log.debug("Queue join")
        self._queue.join()

        # Signal all the workers to exit.
        log.debug("Set exit event to workers")
        self._worker_event.set()
        # Shutdown the executor.
        log.debug("Shutdown uploader daemon")
        self._daemon_thread.join()

        log.info("All upload work complete.")
        self._status = False
        return True

    def _check_if_initialize(self) -> bool:
        return (
            self._queue is not None
            and self._worker_event is not None
            and self._daemon_thread is not None
            and self._api_client is not None
            and self._upload_start is not None
            and self._upload_finish is not None
        )
