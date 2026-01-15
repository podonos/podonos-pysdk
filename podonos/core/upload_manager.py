from __future__ import annotations
import atexit
import datetime
import queue
import threading
import time
from typing import TYPE_CHECKING

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from tqdm import tqdm
from typing import Optional, Any, Dict, Tuple

try:
    from typing import Protocol  # Python 3.8+: available in typing
except Exception:  # pragma: no cover
    from typing_extensions import Protocol  # type: ignore

from podonos.core.base import *
from podonos.service.evaluation_service import EvaluationService
from podonos.common.util import calculate_file_md5_base64
from podonos.common.validator import Rules, validate_args

if TYPE_CHECKING:
    from podonos.core.file import Audio


class UploadManager:
    """Concurrent file upload manager.
    Internally creates multiple threads, and manages the uploading status.
    """

    class UploadQueue(Protocol):
        def put(
            self,
            item: Tuple[str, "Audio"],
            block: bool = True,
            timeout: Optional[float] = None,
        ) -> None: ...
        def get(
            self, block: bool = True, timeout: Optional[float] = None
        ) -> Tuple[str, "Audio"]: ...
        def empty(self) -> bool: ...
        def task_done(self) -> None: ...
        def join(self) -> None: ...

    # File path queue
    # TODO: use a file queue.
    _queue: Optional[UploadQueue] = None
    # Total number of files added to the uploading queue.
    _total_files: int = 0
    _total_uploaded: int = 0

    _pbar: Optional[Any] = None
    # Event to all the uploader threads
    _worker_event: Optional[Event] = None
    # Master daemon thread. Alive until the manager closes.
    _daemon_thread: Optional[threading.Thread] = None
    # Evaluation service
    _evaluation_service: EvaluationService
    # Manager status. True if the manager is ready.
    _status: bool = False
    # Maximum number of uploader worker threads
    _max_workers: int = 1
    #
    _upload_start: Optional[Dict[str, str]] = None
    _upload_finish: Optional[Dict[str, str]] = None

    def get_upload_time(self) -> Tuple[Dict[str, str], Dict[str, str]]:
        if not self._upload_start or not self._upload_finish:
            raise ValueError("Upload Fail")

        return self._upload_start, self._upload_finish

    @validate_args(
        evaluation_service=Rules.instance_of(EvaluationService),
        max_workers=Rules.positive_not_none,
    )
    def __init__(
        self,
        evaluation_service: EvaluationService,
        max_workers: int,
    ) -> None:
        self._upload_start = dict()
        self._upload_finish = dict()
        self._evaluation_service = evaluation_service
        self._queue = queue.Queue()
        self._total_files = 0
        self._max_workers = max_workers
        self._worker_event = Event()
        self._daemon_thread = threading.Thread(
            target=self._uploader_daemon, daemon=True
        )
        self._daemon_thread.start()
        self._status = True

        atexit.register(self.wait_and_close)

    def _uploader_daemon(self) -> None:
        log.debug(f"Uploader daemon is running with {self._max_workers} workers")
        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            for index in range(self._max_workers):
                executor.submit(self._upload_worker, index, self._worker_event)  # type: ignore
        log.debug(f"Uploader daemon is shutting down")
        executor.shutdown(wait=True)

    @validate_args(index=Rules.int_not_none, worker_event=Rules.instance_of(Event))
    def _upload_worker(self, index: int, worker_event: Event) -> None:
        if not (
            self._queue is not None
            and self._worker_event is not None
            and self._daemon_thread is not None
            and self._evaluation_service is not None  # type: ignore
            and self._upload_start is not None
            and self._upload_finish is not None
        ):
            raise ValueError("Upload Manager is not initialized")

        log.debug(f"Worker is {index} ready")
        while True:
            if not self._queue.empty():
                item: Tuple[str, "Audio"] = self._queue.get()
                evaluation_id = item[0]
                audio = item[1]

                log.debug(f"Worker {index} calculating MD5 for {audio.path}")
                content_md5, file_size = calculate_file_md5_base64(audio.path)
                audio.set_integrity_info(content_md5, file_size)
                log.debug(f"Worker {index} MD5: {content_md5}, size: {file_size}")

                log.debug(f"Worker {index} presigned url request")
                presigned_url = self._evaluation_service.get_presigned_url(
                    evaluation_id,
                    audio.remote_object_name,
                )
                log.debug(f"Worker {index} presigned url obtained")

                log.debug(f"Worker {index} uploading {audio.path}")
                upload_start_at = (
                    datetime.datetime.now()
                    .astimezone()
                    .isoformat(timespec="milliseconds")
                )
                self._evaluation_service.upload_evaluation_file(
                    presigned_url, audio.path
                )
                upload_finish_at = (
                    datetime.datetime.now()
                    .astimezone()
                    .isoformat(timespec="milliseconds")
                )
                log.debug(
                    f"Worker {index} finished uploading {audio.remote_object_name}"
                )

                audio.set_upload_at(upload_start_at, upload_finish_at)
                self._upload_start[audio.remote_object_name] = upload_start_at
                self._upload_finish[audio.remote_object_name] = upload_finish_at
                self._queue.task_done()
                self._total_uploaded += 1
                log.debug(f"Worker {index} total_uploaded: {self._total_uploaded}")
                if self._pbar:
                    self._pbar.update(1)

            time.sleep(0.1)
            if worker_event.is_set():
                log.debug(f"Worker {index} is done")
                return

    def add_file_to_queue(self, evaluation_id: str, audio: "Audio") -> None:
        if not (
            self._queue is not None
            and self._worker_event is not None
            and self._daemon_thread is not None
            and self._evaluation_service is not None  # type: ignore
            and self._upload_start is not None
            and self._upload_finish is not None
        ):
            raise ValueError("Upload Manager is not initialized")

        log.debug(f"Added: {audio.path}")
        self._queue.put((evaluation_id, audio))
        self._total_files += 1

    def wait_and_close(self) -> bool:
        if not self._status:
            return False

        if not (
            self._queue is not None
            and self._worker_event is not None
            and self._daemon_thread is not None
        ):
            raise ValueError("Upload Manager is not initialized")
        log.debug(f"total_files: {self._total_files}")
        self._pbar = tqdm(total=self._total_files, dynamic_ncols=True)
        self._pbar.update(self._total_uploaded)

        # Block until all tasks are done.
        log.debug("Queue join")
        self._queue.join()

        # Signal all the workers to exit.
        log.debug("Set exit event to workers")
        self._worker_event.set()
        # Shutdown the executor.
        log.debug("Shutdown uploader daemon")
        self._daemon_thread.join()

        self._pbar.close()
        log.info("All upload work complete.")
        self._status = False
        return True

    def _check_if_initialize(self) -> bool:
        return (
            self._queue is not None
            and self._worker_event is not None
            and self._daemon_thread is not None
            and self._evaluation_service is not None  # type: ignore
            and self._upload_start is not None
            and self._upload_finish is not None
        )
