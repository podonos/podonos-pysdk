import os
import filetype  # type: ignore
import soundfile as sf  # type: ignore
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from podonos.common.enum import EvalType, QuestionFileType
from podonos.common.util import generate_random_group_name, generate_random_name, process_paths_to_posix
from podonos.common.validator import Rules, validate_args
from podonos.core.base import log
from podonos.core.config import EvalConfig


class File:
    _path: str
    _tags: List[str]
    _script: Optional[str]
    _meta_data: Dict[str, Any]

    def __init__(
        self,
        path: str,
        model_tag: str,
        tags: List[str] = [],
        script: Optional[str] = None,
        is_ref: bool = False,
        meta_data: Dict[str, Any] = {},
    ) -> None:
        """
        Args:
            path: Path to the file to evaluate. Required.
            model_tag: String that represents the model or group. Required.
            tags: A list of string for file. Optional.
            script: Script of the input audio in text. Optional.
            is_ref: True if this file is to be a reference for an evaluation type that requires a reference.
                    Optional. Default is False.
            meta_data: Arbitrary key-value meta data. Keys must be strings.
                       Values must be JSON-primitive types (str, int, float, bool, None).
                       Iterable types such as list, tuple, set, dict are not allowed.
        """
        log.check_ne(path, "")  # type: ignore
        log.check_ne(model_tag, "")  # type: ignore

        self._path = self._validate_path(path)
        self._model_tag = self._validate_model_tag(model_tag)
        self._tags = self._set_tags(tags)
        self._script = self._validate_script(script)
        self._is_ref = self._validate_is_ref(is_ref)
        self._meta_data = self._validate_meta_data(meta_data)

    @property
    def path(self) -> str:
        return self._path

    @property
    def model_tag(self) -> str:
        return self._model_tag

    @property
    def tags(self) -> List[str]:
        return self._tags

    @property
    def script(self) -> Optional[str]:
        return self._script

    @property
    def is_ref(self) -> Optional[bool]:
        return self._is_ref

    @property
    def meta_data(self) -> Dict[str, Any]:
        return self._meta_data

    def get_question_type_by_is_ref(self) -> QuestionFileType:
        if self._is_ref:
            return QuestionFileType.REF
        return QuestionFileType.STIMULUS

    @validate_args(path=Rules.str_non_empty)
    def _validate_path(self, path: str) -> str:
        """Validate file path exists and is readable.

        Args:
            path: File path to validate

        Returns:
            Validated path

        Raises:
            FileNotFoundError: If file doesn't exist or isn't readable
        """
        if not os.path.isfile(path):
            raise FileNotFoundError(f"File {path} doesn't exist")

        if not os.access(path, os.R_OK):
            raise FileNotFoundError(f"File {path} isn't readable")

        return path

    @validate_args(model_tag=Rules.str_non_empty)
    def _validate_model_tag(self, model_tag: str) -> str:
        """Validate model_tag is a non-empty string with allowed characters only.

        Args:
            model_tag: Model tag to validate

        Returns:
            Validated model tag

        Raises:
            ValueError: If model_tag is not a string, is empty, or contains invalid characters
        """
        if not isinstance(model_tag, str):  # type: ignore
            raise ValueError(f"model_tag must be a string, got {type(model_tag)}")

        processed_model_tag = model_tag.strip()
        if not processed_model_tag:
            raise ValueError("model_tag cannot be empty")

        # Check for invalid characters (allow Unicode letters, numbers, -, and _)
        import re

        if not re.match(r"^[\w\-]+$", processed_model_tag, re.UNICODE):
            invalid_chars: List[str] = []
            for char in processed_model_tag:
                # Check if character is not a Unicode letter, not a digit, and not - or _
                if not (char.isalpha() or char.isdigit() or char in ["-", "_"]):
                    invalid_chars.append(char)
            if invalid_chars:
                raise ValueError(
                    f"model_tag contains invalid characters: {invalid_chars}. Only letters, numbers, hyphens (-), and underscores (_) are allowed."
                )

        return processed_model_tag

    @validate_args(script=Rules.str_not_none_or_none)
    def _validate_script(self, script: Optional[str]) -> Optional[str]:
        """Validate script is either None or a string.

        Args:
            script: Script to validate

        Returns:
            Validated script

        Raises:
            ValueError: If script is neither None nor a string
        """
        if script is not None and not isinstance(script, str):  # type: ignore
            raise ValueError(f"script must be a string or None, got {type(script)}")
        return script

    @validate_args(is_ref=Rules.bool_not_none)
    def _validate_is_ref(self, is_ref: bool) -> bool:
        """Validate is_ref is a boolean.

        Args:
            is_ref: Boolean flag to validate

        Returns:
            Validated boolean flag

        Raises:
            ValueError: If is_ref is not a boolean
        """
        if not isinstance(is_ref, bool):  # type: ignore
            raise ValueError(f"is_ref must be a boolean, got {type(is_ref)}")
        return is_ref

    @validate_args(tags=Rules.list_not_none)
    def _set_tags(self, tags: List[str]) -> List[str]:
        """
        Set the tags as a list of unique strings for the file.

        Args:
            tags: A list of string for file.

        Returns:
            A list of unique tags

        Raises:
            ValueError: If tags is not a list or contains non-string elements
        """
        if not isinstance(tags, list):  # type: ignore
            raise ValueError(f"tags must be a list, got {type(tags)}")

        unique_tags: List[str] = []
        seen: Set[str] = set()
        for i, tag in enumerate(tags):
            if not isinstance(tag, (str, int, float)):  # type: ignore
                raise ValueError(f"tag at index {i} must be a string, number, or boolean, got {type(tag)}")

            str_tag = str(tag)
            if str_tag not in seen:
                seen.add(str_tag)
                unique_tags.append(str_tag)

        return unique_tags

    @validate_args(meta_data=Rules.dict_not_none)
    def _validate_meta_data(self, meta_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate meta_data payload.
        - Keys must be strings.
        - Values must be JSON-primitive types: str, int, float, bool, None.
        - Disallow iterable/container types: list, tuple, set, dict (including nested).
        """
        allowed_value_types = (str, int, float, bool, type(None))
        validated: Dict[str, Any] = {}
        for k, v in meta_data.items():
            if not isinstance(k, str):  # type: ignore
                raise ValueError(f"meta_data key must be a string, got key type {type(k)}")
            # Disallow common iterable/container types except str
            if isinstance(v, (list, tuple, set, dict)):
                raise ValueError(f"meta_data[{k}] must be a non-iterable JSON-primitive (got {type(v)})")  # type: ignore
            if not isinstance(v, allowed_value_types):
                raise ValueError(f"meta_data[{k}] must be one of (str, int, float, bool, None), got {type(v)}")
            validated[k] = v
        return validated


class FileValidator:
    def __init__(self, eval_config: EvalConfig):
        self._eval_config = eval_config
        self._stimulus_model_tags: Set[str] = set()
        self._stimulus_model_pairs: List[Tuple[str, str]] = list()

    @validate_args(file=Rules.instance_of(File))
    def validate_file(self, file: File) -> File:
        """Validate file based on evaluation type"""
        if self._eval_config.eval_type not in [EvalType.NMOS, EvalType.QMOS, EvalType.P808, EvalType.CUSTOM_SINGLE]:
            raise ValueError(f"Unsupported evaluation type: {self._eval_config.eval_type}")
        return self._validate_file_common(file)

    @validate_args(files=Rules.list_not_none)
    def validate_files(self, files: List[Optional[File]]) -> List[File]:
        """Main method to validate files based on evaluation type"""
        if self._eval_config.eval_type in [EvalType.PREF, EvalType.CUSTOM_DOUBLE, EvalType.SMOS]:
            return self._validate_double_stimuli_files(files)
        elif self._eval_config.eval_type in [EvalType.CMOS, EvalType.DMOS]:
            return self._validate_one_stimulus_and_one_ref_files(files)
        elif self._eval_config.eval_type in [EvalType.CSMOS]:
            return self._validate_two_stimuli_and_one_ref_files(files)
        else:
            raise ValueError(f"Unsupported evaluation type: {self._eval_config.eval_type}")

    @validate_args(files=Rules.list_not_none)
    def _validate_double_stimuli_files(self, files: List[Optional[File]]) -> List[File]:
        """Validate files for stimuli-based evaluations"""
        valid_files = [self._validate_file_common(file) for file in files if file is not None and file.is_ref == False]
        if len(valid_files) != 2:
            raise ValueError("Stimuli evaluations require exactly two files")

        return self._validate_double_stimuli_model_tags(valid_files[0], valid_files[1])

    @validate_args(files=Rules.list_not_none)
    def _validate_one_stimulus_and_one_ref_files(self, files: List[Optional[File]]) -> List[File]:
        """Validate files for reference-stimulus evaluations"""
        valid_files = [self._validate_file_common(file) for file in files if file is not None]
        if len(valid_files) != 2:
            raise ValueError("Reference-stimulus evaluations require exactly two files")

        if valid_files[0].is_ref == valid_files[1].is_ref:
            raise ValueError("One file must be reference, one must be stimulus")

        return valid_files

    @validate_args(files=Rules.list_not_none)
    def _validate_two_stimuli_and_one_ref_files(self, files: List[Optional[File]]) -> List[File]:
        """Validate files for two-stimuli-one-reference evaluations"""
        valid_files = [self._validate_file_common(file) for file in files if file is not None]
        if len(valid_files) != 3:
            raise ValueError("Two-stimuli-one-reference evaluations require exactly three files")

        if valid_files[2].is_ref == False:
            raise ValueError("Reference file must be at the third position in add_files")

        if valid_files[0].is_ref or valid_files[1].is_ref:
            raise ValueError("First and second files must be stimuli in CSMOS")

        stimuli = [file for file in valid_files if file.is_ref == False]
        ref = [file for file in valid_files if file.is_ref == True]

        if len(stimuli) != 2 or len(ref) != 1:
            raise ValueError("Two-stimuli-one-reference evaluations require exactly two stimuli and one reference")

        return self._validate_double_stimuli_model_tags(stimuli[0], stimuli[1]) + ref

    @validate_args(file=Rules.instance_of(File))
    def _validate_file_common(self, file: File) -> File:
        """Common file validation logic"""

        if self._eval_config.eval_use_annotation and file.script is None:
            raise ValueError(
                "Annotation evaluation is enabled (use_annotation=True), " "but no script is provided in File. Please provide a corresponding script."
            )

        if self._eval_config.eval_ai_type and file.script is None:
            raise ValueError(
                "ASR evaluation is enabled (eval_ai_type=ASR), " "but no script is provided in File. Please provide a corresponding script."
            )

        if not file.model_tag or len(file.model_tag.strip()) == 0:
            raise ValueError("model_tag is required")

        return file

    @validate_args(file0=Rules.instance_of(File), file1=Rules.instance_of(File))
    def _validate_double_stimuli_model_tags(
        self,
        file0: File,
        file1: File,
    ) -> List[File]:
        """
        Validate & return the two files sorted by model_tag
        (numeric‑aware, case‑insensitive).  Locale handling is NOT applied.

        WARNING:
            Use only for SMOS, PREF, CSMOS, CUSTOM_DOUBLE, CUSTOM_TRIPLE.
        """
        for f in (file0, file1):
            if not getattr(f, "model_tag", None):
                raise ValueError("model_tag is required")

        # file0_model_tag = file0.model_tag.lower()
        # file1_model_tag = file1.model_tag.lower()
        if file0.model_tag == file1.model_tag:
            raise ValueError("The model tags must differ in `add_files` " "for double (or more) stimuli evaluations")

        if len(self._stimulus_model_tags) == 0:
            self._stimulus_model_tags.add(file0.model_tag)
            self._stimulus_model_tags.add(file1.model_tag)
        else:
            message = f"The number of model tags should be 2 in `add_files` for double (or more) stimuli evaluations"
            if file0.model_tag not in self._stimulus_model_tags:
                raise ValueError(message)
            if file1.model_tag not in self._stimulus_model_tags:
                raise ValueError(message)
        return [file0, file1]

        # TODO: Add this back in when we have a way to track the model tag pairs.
        # requested_model_pair = tuple(sorted([file0_model_tag, file1_model_tag]))
        # for model_pair in self._stimulus_model_pairs:
        #     if model_pair == requested_model_pair:
        #         first_model_tag = model_pair[0]
        #         second_model_tag = model_pair[1]
        #         if first_model_tag != file0_model_tag or second_model_tag != file1_model_tag:
        #             raise ValueError(
        #                 f"Inconsistent model tag pair order. Previously seen pair: "
        #                 f"({first_model_tag}, {second_model_tag}), but received: "
        #                 f"({file0_model_tag}, {file1_model_tag}). "
        #                 f"Please maintain consistent ordering for the same model tag pairs."
        #             )
        #         return [file0, file1]

        # self._stimulus_model_pairs.append((file0_model_tag, file1_model_tag))
        # return [file0, file1]


class AudioMeta:
    _nchannels: int
    _framerate: int
    _duration_in_ms: int

    @validate_args(path=Rules.str_non_empty)
    def __init__(self, path: str) -> None:
        self._nchannels, self._framerate, self._duration_in_ms = self._set_audio_meta(path)
        log.check_ge(self._nchannels, 0)  # type: ignore
        log.check_ge(self._framerate, 0)  # type: ignore
        log.check_ge(self._duration_in_ms, 0)  # type: ignore

    @property
    def nchannels(self) -> int:
        return self._nchannels

    @property
    def framerate(self) -> int:
        return self._framerate

    @property
    def duration_in_ms(self) -> int:
        return self._duration_in_ms

    @validate_args(filepath=Rules.file_path_not_none)
    def _detect_audio_format(self, filepath: str) -> str:
        """Detect actual audio format using filetype library"""
        try:
            kind = filetype.guess(filepath)  # type: ignore
            mime: Optional[str] = kind.mime if kind is not None else None
            extension: Optional[str] = kind.extension if kind is not None else None
            if kind is None or mime is None or extension is None:
                return "unknown"

            # Map MIME types to format names
            mime_to_format: Dict[str, str] = {
                "audio/wav": "wav",
                "audio/wave": "wav",
                "audio/x-wav": "wav",
                "audio/mpeg": "mp3",
                "audio/x-mpeg": "mp3",
                "audio/mp3": "mp3",
                "audio/flac": "flac",
                "audio/x-flac": "flac",
            }

            return mime_to_format.get(mime, extension)

        except Exception as e:
            log.error(f"Failed to detect format for {filepath}: {e}")
            return "unknown"

    @validate_args(path=Rules.file_path_not_none)
    def _set_audio_meta(self, path: str) -> Tuple[int, int, int]:
        """Gets info from an audio file.

        Returns:
            nchannels: Number of channels
            framerate: Number of frames per second. Same as the sampling rate.
            duration_in_ms: Total length of the audio in milliseconds

        Raises:
            FileNotFoundError: if the file is not found.
            wave.Error: if the file doesn't read properly.
            AssertionError: if the file format is not wav.
        """
        # Check if this is wav or mp3.
        suffix = Path(path).suffix
        actual_format = self._detect_audio_format(path)
        support_file_type = ["wav", "mp3", "flac", ".wav", ".mp3", ".flac"]
        assert suffix in support_file_type and actual_format in support_file_type, (
            f"Unsupported file type. Extension: {suffix or 'N/A'}, Actual format: {actual_format or 'unknown'}. "
            f"Supported: wav, mp3, flac. Please convert or re-export the audio so the content and extension match."
        )
        if actual_format in support_file_type:
            return self._get_audio_info(path)
        return 0, 0, 0

    @validate_args(filepath=Rules.str_non_empty)
    def _get_audio_info(self, filepath: str) -> Tuple[int, int, int]:
        """Gets info from a wave file.

        Returns:
            nchannels: Number of channels
            framerate: Number of frames per second. Same as the sampling rate.
            duration_in_ms: Total length of the audio in milliseconds

        Raises:
            FileNotFoundError: if the file is not found.
            wave.Error: if the file doesn't read properly.
        """
        try:
            f = sf.SoundFile(filepath)
            nframes = f.frames
            nchannels = f.channels
            framerate = f.samplerate
            log.check_gt(nframes, 0)  # type: ignore
            log.check_gt(nchannels, 0)  # type: ignore
            log.check_gt(framerate, 0)  # type: ignore

            duration_in_ms = int(nframes * 1000.0 / float(framerate))
            log.check_gt(duration_in_ms, 0)  # type: ignore
            if duration_in_ms < 500:
                log.warning(
                    f"Audio length below 500ms (current {duration_in_ms} ms). "
                    f"Please verify on the web whether this file is evaluable. File: {filepath}"
                )
            return nchannels, framerate, duration_in_ms
        except AttributeError as e:
            log.error(f"Attribute error while getting audio info: {e}")
            return 0, 0, 0
        except Exception as e:
            log.error(f"Error getting audio info: {e}")
            return 0, 0, 0


class Audio(File):
    @validate_args(
        path=Rules.str_non_empty,
        name=Rules.str_non_empty,
        remote_object_name=Rules.str_non_empty,
        script=Rules.str_not_none_or_none,
        tags=Rules.list_not_none,
        model_tag=Rules.str_non_empty,
        is_ref=Rules.bool_not_none,
        meta_data=Rules.dict_not_none,
        group=Rules.str_not_none_or_none,
        type=Rules.instance_of(QuestionFileType),
        order_in_group=Rules.int_not_none,
    )
    def __init__(
        self,
        path: str,
        name: str,
        remote_object_name: str,
        script: Optional[str],
        tags: List[str],
        model_tag: str,
        is_ref: bool,
        group: Optional[str],
        type: QuestionFileType,
        order_in_group: int,
        meta_data: Dict[str, Any] = {},
    ):
        super().__init__(path, model_tag, tags, script, is_ref, meta_data)
        self._name = name
        self._remote_object_name = remote_object_name
        self._group = group
        self._type = type
        self._metadata = AudioMeta(path)
        self._order_in_group = order_in_group
        self._upload_start_at = None
        self._upload_finish_at = None

    @classmethod
    @validate_args(
        file=Rules.instance_of(File),
        creation_timestamp=Rules.str_not_none,
        group=Rules.str_not_none_or_none,
        type=Rules.instance_of(QuestionFileType),
        order_in_group=Rules.int_not_none,
    )
    def from_file(
        cls,
        file: File,
        creation_timestamp: str,
        group: Optional[str],
        type: QuestionFileType,
        order_in_group: int,
    ) -> "Audio":
        """Create Audio instance from File object

        Args:
            file: Source File object
            creation_timestamp: Timestamp for remote path
            group: Optional group identifier
            type: Question file type
            order_in_group: Order in group

        Returns:
            New Audio instance
        """
        remote_object_name = os.path.join(creation_timestamp, generate_random_name())
        original_path, remote_path = process_paths_to_posix(file.path, str(remote_object_name))

        return cls(
            path=file.path,
            name=original_path,
            remote_object_name=remote_path,
            script=file.script,
            tags=file.tags,
            model_tag=file.model_tag,
            is_ref=file.is_ref if file.is_ref else False,
            meta_data=file.meta_data,
            group=group,
            type=type,
            order_in_group=order_in_group,
        )

    @property
    def name(self) -> str:
        return self._name

    @property
    def remote_object_name(self) -> str:
        return self._remote_object_name

    @property
    def group(self) -> Optional[str]:
        return self._group

    @property
    def type(self) -> QuestionFileType:
        return self._type

    @property
    def order_in_group(self) -> int:
        return self._order_in_group

    @validate_args(start_at=Rules.str_not_none, finish_at=Rules.str_not_none)
    def set_upload_at(self, start_at: str, finish_at: str) -> None:
        self._upload_start_at = start_at
        self._upload_finish_at = finish_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self._name,
            "remote_name": self._remote_object_name,
            "nchannels": self._metadata.nchannels,
            "framerate": self._metadata.framerate,
            "duration_in_ms": self._metadata.duration_in_ms,
            "upload_start_at": self._upload_start_at,
            "upload_finish_at": self._upload_finish_at,
            "model_tag": self._model_tag,
            "is_ref": self._is_ref,
            "tag": self._tags,
            "type": self._type,
            "script": self._script,
            "meta_data": self._meta_data,
            "group": self._group,
            "order_in_group": self._order_in_group,
        }

    def to_create_file_dict(self) -> Dict[str, Any]:
        return {
            "original_name": self._path,
            "uploaded_file_name": self._remote_object_name,
            "duration": self._metadata.duration_in_ms,
            "model_tag": self._model_tag,
            "tags": self._tags,
            "type": self._type,
            "script": self._script,
            "meta_data": self._meta_data,
            "group": self._group,
            "order_in_group": self._order_in_group,
        }


@dataclass
class AudioGroup:
    """Represent a group of files for evaluation"""

    group_id: Optional[str]  # None for single stimulus, UUID for double stimuli
    audios: List[Audio]
    created_at: datetime

    @validate_args(group_id=Rules.str_not_none_or_none, audios=Rules.list_not_none, created_at=Rules.datetime_not_none)
    def __init__(self, group_id: Optional[str], audios: List[Audio], created_at: datetime):
        self.group_id = group_id
        self.created_at = created_at
        self.audios = self.set_audios(audios)

    @validate_args(audios=Rules.list_not_none)
    def set_audios(self, audios: List[Audio]):
        """
        Args:
            audios: List of Audio objects

        Raises:
            ValueError: If all audios don't have the same group_id or order_in_group is not unique
        """
        for i, audio in enumerate(audios):
            if audio.group != self.group_id:
                raise ValueError(f"All audios must have the same group_id. Expected {self.group_id}, got {audio.group}.")
            if audio.order_in_group != i:
                raise ValueError(f"Order in group must be unique. Got {audio.order_in_group}.")

        return audios

    def to_dict(self) -> Dict[str, Any]:
        return {
            "group_id": self.group_id,
            "audios": [audio.to_dict() for audio in self.audios],
            "created_at": self.created_at.isoformat(),
        }


class FileTransformer:
    @validate_args(eval_config=Rules.instance_of(EvalConfig))
    def __init__(self, eval_config: EvalConfig):
        self._eval_config = eval_config

    @validate_args(files=Rules.list_not_none)
    def transform_into_audio_group(self, files: List[File]) -> AudioGroup:
        """Transform files into audio group"""
        if len(files) == 0:
            raise ValueError("No files to transform into audio group")

        if self._eval_config.eval_type in [EvalType.NMOS, EvalType.QMOS, EvalType.P808, EvalType.CUSTOM_SINGLE]:
            return self._transform_single_file(files[0])
        elif self._eval_config.eval_type in [EvalType.CMOS, EvalType.DMOS]:
            return self._transform_one_stimulus_and_one_ref_files(files)
        elif self._eval_config.eval_type in [EvalType.PREF, EvalType.SMOS, EvalType.CUSTOM_DOUBLE]:
            return self._transform_double_stimuli_files(files)
        elif self._eval_config.eval_type in [EvalType.CMOS]:
            return self._transform_one_stimulus_and_one_ref_files(files)
        elif self._eval_config.eval_type in [EvalType.CSMOS]:
            return self._transform_two_stimuli_and_one_ref_files(files)
        else:
            raise ValueError(f"Unsupported evaluation type: {self._eval_config.eval_type}")

    @validate_args(file=Rules.instance_of(File))
    def _transform_single_file(self, file: File) -> AudioGroup:
        return AudioGroup(
            group_id=None,
            audios=[self._create_audio(file=file, group=None, type=file.get_question_type_by_is_ref(), order_in_group=0)],
            created_at=datetime.now(),
        )

    @validate_args(files=Rules.list_not_none)
    def _transform_double_stimuli_files(self, files: List[File]) -> AudioGroup:
        group_id = generate_random_group_name()
        return AudioGroup(
            group_id=group_id,
            audios=[
                self._create_audio(file=file, group=group_id, type=file.get_question_type_by_is_ref(), order_in_group=i)
                for i, file in enumerate(files)
            ],
            created_at=datetime.now(),
        )

    @validate_args(files=Rules.list_not_none)
    def _transform_one_stimulus_and_one_ref_files(self, files: List[File]) -> AudioGroup:
        group_id = generate_random_group_name()
        return AudioGroup(
            group_id=group_id,
            audios=[
                self._create_audio(file=file, group=group_id, type=file.get_question_type_by_is_ref(), order_in_group=i)
                for i, file in enumerate(files)
            ],
            created_at=datetime.now(),
        )

    @validate_args(files=Rules.list_not_none)
    def _transform_two_stimuli_and_one_ref_files(self, files: List[File]) -> AudioGroup:
        group_id = generate_random_group_name()
        return AudioGroup(
            group_id=group_id,
            audios=[
                self._create_audio(file=file, group=group_id, type=file.get_question_type_by_is_ref(), order_in_group=i)
                for i, file in enumerate(files)
            ],
            created_at=datetime.now(),
        )

    @validate_args(
        file=Rules.instance_of(File),
        group=Rules.str_not_none_or_none,
        type=Rules.instance_of(QuestionFileType),
        order_in_group=Rules.int_not_none,
    )
    def _create_audio(
        self,
        file: File,
        group: Optional[str],
        type: QuestionFileType,
        order_in_group: int = 0,
    ) -> Audio:
        return Audio.from_file(
            file=file, creation_timestamp=self._eval_config.eval_creation_timestamp, group=group, type=type, order_in_group=order_in_group
        )
