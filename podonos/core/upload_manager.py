import datetime
import logging
import os
import queue
import threading
import time

from threading import Event
from concurrent.futures import ThreadPoolExecutor

from podonos.core.api import APIClient

# Delete this
import random

# For logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


class UploadManager:
    """Concurrent file upload manager.
    Internally creates multiple threads, and manages the uploading status.
    """
    # Maximum number of uploader worker thread
    _max_workers: int
    # File path queue
    # TODO: use a file queue.
    _queue: queue.Queue = None
    # Event to all the uploader threads
    _worker_event: Event = None
    # Master daemon thread. Alive until the manager closes.
    _daemon_thread: threading.Thread = None
    # API client for
    _api_client: APIClient = None
    # Manager status. True if the manager is ready.
    _status: bool

    _upload_start: dict = None
    _upload_finish: dict = None

    def get_upload_time(self):
        return self._upload_start, self._upload_finish

    def __init__(self, max_workers:int) -> None:
        self._max_workers = max_workers

        self._upload_start = {}
        self._upload_finish = {}

        self._queue = queue.Queue()
        self._worker_event = Event()
        self._daemon_thread = threading.Thread(target=self._uploader_daemon, daemon=True)
        self._daemon_thread.start()


    def _uploader_daemon(self) -> None:
        logging.debug(f'Uploader daemon is running')
        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            for index in range(self._max_workers):
                future = executor.submit(self._upload_worker, index, self._worker_event)
        logging.debug(f'Uploader daemon is shutting down')
        executor.shutdown(wait=True)

    def _upload_worker(self, index, worker_event) -> None:
        logging.debug(f'Worker is {index} ready')
        while True:
            if not self._queue.empty():
                item = self._queue.get()
                rand_upload_time = 5 + random.randrange(1, 10)
                print(f'Working on {item}, takes {rand_upload_time}')
                upload_start_at = datetime.datetime.now().astimezone().isoformat(timespec='milliseconds')
                time.sleep(rand_upload_time)
                upload_finish_at = datetime.datetime.now().astimezone().isoformat(timespec='milliseconds')
                logging.debug(f'Finished {item}')
                self._upload_start[item] = upload_start_at
                self._upload_finish[item] = upload_finish_at
                self._queue.task_done()
            time.sleep(0.1)
            if worker_event.is_set():
                logging.debug(f'Worker is {index} done')
                return

    def add_file_to_queue(self, path: str) -> None:
        logging.debug(f'Added: {path}')
        self._queue.put(path)

    def wait_and_close(self) -> None:
        # Block until all tasks are done.
        logging.debug('Queue join')
        self._queue.join()

        # Signal all the workers to exit.
        logging.debug('Set exit event to workers')
        self._worker_event.set()
        # Shutdown the executor.
        logging.debug('Shutdown uploader daemon')
        self._daemon_thread.join()

        logging.debug('All upload work completed')
