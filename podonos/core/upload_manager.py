from __future__ import annotations
import atexit
import datetime
import queue
import threading
from typing import TYPE_CHECKING

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from tqdm import tqdm
from typing import Optional, Any, Dict, Tuple

try:
    from typing import Protocol  # Python 3.8+: available in typing
except Exception:  # pragma: no cover
    from typing_extensions import Protocol  # type: ignore

from podonos.core.base import log
from podonos.common.redaction import redact_secrets
from podonos.service.evaluation_service import EvaluationService
from podonos.common.util import calculate_file_md5_base64
from podonos.common.validator import Rules, validate_args
from podonos.errors.error import UploadBatchError, UploadFailure
from podonos.core.upload_ledger import (
    GROUP_ORDINAL_ATTR,
    UploadLedger,
    build_upload_manifest_hash,
    build_upload_manifest_key,
    stable_manifest_contract,
)

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
    _api_timeout: Tuple[float, float] = (5, 30)
    _upload_timeout: Tuple[float, float] = (10, 300)
    _upload_errors: Optional[list[UploadFailure]] = None
    _upload_errors_lock: Optional[threading.Lock] = None
    _upload_success_lock: Optional[threading.Lock] = None
    _upload_ledger: Optional[UploadLedger] = None

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
        api_timeout: Tuple[float, float] = (5, 30),
        upload_timeout: Tuple[float, float] = (10, 300),
        upload_ledger: Optional[UploadLedger] = None,
    ) -> None:
        self._upload_start = dict()
        self._upload_finish = dict()
        self._upload_errors = []
        self._upload_errors_lock = threading.Lock()
        self._upload_success_lock = threading.Lock()
        self._evaluation_service = evaluation_service
        self._queue = queue.Queue()
        self._total_files = 0
        self._max_workers = max_workers
        self._api_timeout = api_timeout
        self._upload_timeout = upload_timeout
        self._upload_ledger = upload_ledger
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
        log.debug("Uploader daemon is shutting down")
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
            and self._upload_success_lock is not None
        ):
            raise ValueError("Upload Manager is not initialized")

        log.debug(f"Worker is {index} ready")
        while True:
            try:
                item: Tuple[str, "Audio"] = self._queue.get(timeout=0.1)
            except queue.Empty:
                if worker_event.is_set():
                    log.debug(f"Worker {index} is done")
                    return
                continue

            evaluation_id = item[0]
            audio = item[1]

            try:
                log.debug(f"Worker {index} calculating file integrity")
                content_md5, file_size = self._get_or_calculate_integrity(audio)
                self._mark_ledger_md5_ready(
                    evaluation_id, audio, content_md5, file_size
                )
                log.debug(f"Worker {index} integrity calculated: size={file_size}")

                log.debug(f"Worker {index} presigned url request")
                presigned_url = self._evaluation_service.get_presigned_url(
                    evaluation_id,
                    audio.remote_object_name,
                    timeout=self._api_timeout,
                    context={"file_count": 1},
                )
                log.debug(f"Worker {index} presigned url obtained")

                log.debug(f"Worker {index} uploading file")
                upload_start_at = (
                    datetime.datetime.now()
                    .astimezone()
                    .isoformat(timespec="milliseconds")
                )
                self._evaluation_service.upload_evaluation_file(
                    presigned_url,
                    audio.path,
                    timeout=self._upload_timeout,
                    context={"evaluation_id": evaluation_id},
                )
                upload_finish_at = (
                    datetime.datetime.now()
                    .astimezone()
                    .isoformat(timespec="milliseconds")
                )
                log.debug(f"Worker {index} finished uploading {audio.remote_object_name}")

                audio.set_upload_at(upload_start_at, upload_finish_at)
                self._mark_ledger_uploaded(
                    evaluation_id, audio, upload_start_at, upload_finish_at
                )
                with self._upload_success_lock:
                    self._upload_start[audio.remote_object_name] = upload_start_at
                    self._upload_finish[audio.remote_object_name] = upload_finish_at
                    self._total_uploaded += 1
                    log.debug(f"Worker {index} total_uploaded: {self._total_uploaded}")
                    if self._pbar:
                        self._pbar.update(1)
            except Exception as exc:
                self._record_upload_error(evaluation_id, audio, exc)
            finally:
                self._queue.task_done()

            if worker_event.is_set():
                log.debug(f"Worker {index} is done")
                return

    def _get_or_calculate_integrity(self, audio: "Audio") -> tuple[str, int]:
        if audio.content_md5 and audio.file_size and audio.file_size > 0:
            return audio.content_md5, audio.file_size
        content_md5, file_size = calculate_file_md5_base64(audio.path)
        audio.set_integrity_info(content_md5, file_size)
        return content_md5, file_size

    def add_file_to_queue(self, evaluation_id: str, audio: "Audio") -> None:
        if not (
            self._queue is not None
            and self._worker_event is not None
            and self._daemon_thread is not None
            and self._evaluation_service is not None  # type: ignore
            and self._upload_start is not None
            and self._upload_finish is not None
            and self._upload_success_lock is not None
        ):
            raise ValueError("Upload Manager is not initialized")

        log.debug("Added upload queue item")
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

        self._status = False
        if self._pbar:
            self._pbar.close()
        try:
            atexit.unregister(self.wait_and_close)
        except Exception:
            pass
        if self._upload_errors:
            log.error(f"{len(self._upload_errors)} upload(s) failed.")
            raise UploadBatchError(self._upload_errors)
        log.info("All upload work complete.")
        return True

    def _record_upload_error(
        self, evaluation_id: str, audio: "Audio", exc: Exception
    ) -> None:
        if self._upload_errors is None or self._upload_errors_lock is None:
            raise ValueError("Upload Manager is not initialized")

        failure = UploadFailure(
            path=audio.path,
            remote_object_name=audio.remote_object_name,
            error_type=type(exc).__name__,
            error_message=redact_secrets(exc),
        )
        with self._upload_errors_lock:
            self._upload_errors.append(failure)
        log.error(
            f"Failed to upload file ({audio.remote_object_name}): "
            f"{failure.error_type}: {failure.error_message}"
        )
        if self._upload_ledger is not None:
            try:
                self._upload_ledger.mark_upload_failed(
                    evaluation_id,
                    audio.remote_object_name,
                    failure.error_type,
                    failure.error_message,
                )
            except Exception as ledger_exc:
                log.warning(
                    f"Failed to mark upload ledger failure for "
                    f"{audio.remote_object_name}: {redact_secrets(ledger_exc)}"
                )

    def _mark_ledger_md5_ready(
        self, evaluation_id: str, audio: "Audio", content_md5: str, file_size: int
    ) -> None:
        if self._upload_ledger is None:
            return
        # Use the stable group ordinal stamped onto the audio by the evaluator before
        # it was queued, so the persisted manifest key/hash match the evaluator's
        # queue-time key (the random per-run group would diverge and break resume).
        stable_contract = stable_manifest_contract(
            audio.to_create_file_dict(), getattr(audio, GROUP_ORDINAL_ATTR, None)
        )
        manifest_hash = build_upload_manifest_hash(
            stable_contract, content_md5, file_size
        )
        manifest_key = build_upload_manifest_key(
            stable_contract, content_md5, file_size
        )
        try:
            self._upload_ledger.mark_md5_ready(
                evaluation_id,
                audio.remote_object_name,
                content_md5,
                file_size,
                manifest_hash=manifest_hash,
                manifest_key=manifest_key,
            )
        except Exception as exc:
            raise RuntimeError(
                "Failed to update upload ledger md5_ready for "
                f"{audio.remote_object_name}: {redact_secrets(exc)}"
            ) from exc

    def _mark_ledger_uploaded(
        self, evaluation_id: str, audio: "Audio", upload_start_at: str, upload_finish_at: str
    ) -> None:
        if self._upload_ledger is None:
            return
        try:
            self._upload_ledger.mark_uploaded(
                evaluation_id, audio.remote_object_name, upload_start_at, upload_finish_at
            )
        except Exception as exc:
            raise RuntimeError(
                "Failed to update upload ledger uploaded for "
                f"{audio.remote_object_name}: {redact_secrets(exc)}"
            ) from exc

    def _check_if_initialize(self) -> bool:
        return (
            self._queue is not None
            and self._worker_event is not None
            and self._daemon_thread is not None
            and self._evaluation_service is not None  # type: ignore
            and self._upload_start is not None
            and self._upload_finish is not None
            and self._upload_success_lock is not None
        )
