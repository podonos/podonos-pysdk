import datetime
import logging
import os
import queue
import threading
import time

from threading import Event
from concurrent.futures import ThreadPoolExecutor


class UploadManager:
    """Concurrent file upload manager.
    Internally creates multiple threads, and manages the uploading status.
    """
    # Maximum number of uploader worker thread
    _max_workers: int
    # File path queue
    # TODO: use a file queue.
    _queue = None
    # Event to all the uploader threads
    _worker_event = None
    # Master daemon thread. Alive until the manager closes.
    _daemon_thread = None
    # Manager status. True if the manager is ready.
    _status: bool

    def __init__(self, max_workers:int) -> None:
        self._max_workers = max_workers

        self._queue = queue.Queue()
        self._worker_event = Event()
        self._daemon_thread = threading.Thread(target=self._uploader_daemon, daemon=True)
        self._daemon_thread.start()

    def _uploader_daemon(self) -> None:
        print(f'Uploader daemon is running')
        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            for index in range(self._max_workers):
                future = executor.submit(self._upload_worker, index, event)
        print(f'Uploader daemon shuts down')
        executor.shutdown(wait=True)

    def _upload_worker(self, index, worker_event) -> None:
        print(f'Worker is {index} ready')
        while True:
            if not self._queue.empty():
                item = self._queue.get()
                rand_upload_time = 5 + random.randrange(1, 10)
                print(f'Working on {item}, takes {rand_upload_time}')
                time.sleep(rand_upload_time)
                print(f'Finished {item}')
                self._queue.task_done()
            time.sleep(0.1)
            if self._worker_event.is_set():
                print(f'Worker is {index} done')
                return

    def add_file_to_queue(self, path:str) -> None:
        print(f'Added: {item}')
        self._queue.put(item)

    def wait_and_close(self) -> None:
        # Block until all tasks are done.
        print('Queue join')
        self._queue.join()

        # Signal all the workers to exit.
        print('Set event')
        self._worker_event.set()
        # Cancel the task, just in case it is not yet running
        # future.cancel()
        # Shutdown the executor.
        print('Shutdown uploader daemon')
        self._daemon_thread.join()

        print('All work completed')
