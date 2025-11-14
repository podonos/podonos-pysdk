import inspect
from functools import wraps
import os
from typing import Callable, Any, Type, Union, TypeVar
import uuid
from datetime import date, datetime

try:
    from typing import ParamSpec  # Python 3.10+
except Exception:  # pragma: no cover
    from typing_extensions import ParamSpec  # type: ignore

from podonos.core.base import log

P = ParamSpec("P")
R = TypeVar("R")
ValidateFunc = Callable[[Any, str], None]


def validate_args(**validators: Union[Type[Any], tuple[Type[Any], ...], Callable[[Any, str], None]]) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """
    Decorator to define validation rules for function arguments.

    Args:
        **validators: Maps argument names to validation rules.
                      Rules can be types (str, int, (float, int)) or
                      functions that take (value, name) and perform validation.

    Returns:
        A decorator that preserves the original function's type signature for IDEs.
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:  # type: ignore[misc]
            # 1. Bind arguments: connect passed arguments (args, kwargs) to function signature
            sig = inspect.signature(func)  # type: ignore[arg-type]
            bound_args = sig.bind(*args, **kwargs)
            bound_args.apply_defaults()

            # 2. Run validation
            for name, rule in validators.items():
                value = bound_args.arguments.get(name)

                # Check if the argument to be tested was actually passed
                if name not in bound_args.arguments:
                    continue  # pass if using default values (can also test default values if needed)

                # A. Type or Not None check (most cases)
                if isinstance(rule, (Type, tuple)):
                    # log.check_notnone raises an exception internally, so we perform None check here instead
                    log.check_notnone(value, f"Argument '{name}' must not be None")  # type: ignore

                    # Type check
                    log.check(isinstance(value, rule), f"Argument '{name}' must be {rule}, got {type(value)}")  # type: ignore

                # B. Custom validation function (complex conditions like length, positive)
                elif callable(rule):
                    # Call rule(value, name) to perform complex validation
                    rule(value, name)

            # 3. Call original function
            return func(*args, **kwargs)

        return wrapper

    return decorator


# -----------------------------
# Centralized Validation Utility
# -----------------------------
class Validator:
    """Centralized reusable validation helpers."""

    # --- Base checks ---
    @staticmethod
    def check_not_none(value: Any, name: str):
        log.check_notnone(value, f"Argument '{name}' must not be None")  # type: ignore

    @staticmethod
    def check_type(value: Any, name: str, expected_type: Union[Type[Any], tuple[Type[Any], ...]]):
        log.check(isinstance(value, expected_type), f"Argument '{name}' must be {expected_type}, got {type(value)}")  # type: ignore

    @staticmethod
    def check_non_empty_str(value: Any, name: str):
        log.check(isinstance(value, str), f"Argument '{name}' must be a string")  # type: ignore
        log.check(len(value.strip()) > 0, f"Argument '{name}' must not be empty")  # type: ignore

    @staticmethod
    def check_positive(value: Any, name: str):
        log.check(value > 0, f"Argument '{name}' must be positive, got {value}")  # type: ignore

    @staticmethod
    def check_non_empty_list(value: Any, name: str):
        log.check(isinstance(value, list), f"Argument '{name}' must be a list")  # type: ignore
        log.check(len(value) > 0, f"Argument '{name}' must be non-empty list")  # type: ignore

    @staticmethod
    def check_uuid(value: Any, name: str):
        try:
            uuid.UUID(str(value))
        except ValueError:
            raise ValueError(f"Argument '{name}' must be a valid UUID")

    @staticmethod
    def check_instance_of(value: Any, name: str, expected_type: Type[Any]) -> None:
        if not isinstance(value, expected_type):
            raise TypeError(f"{name} must be instance of {expected_type.__name__}, got {type(value).__name__}")

    @staticmethod
    def check_date(value: Any, name: str):
        log.check(isinstance(value, date), f"Argument '{name}' must be a date")  # type: ignore

    @staticmethod
    def check_file(value: Any, name: str):
        log.check(isinstance(value, str), f"Argument '{name}' must be a string")  # type: ignore
        log.check(os.path.isfile(value), f"Argument '{name}' doesn't exist")  # type: ignore
        log.check(os.access(value, os.R_OK), f"Argument '{name}' isn't readable")  # type: ignore


class Rules:
    """Reusable high-level validation rules for @validate_args."""

    # -----------------------------
    # Factory for type-based rules
    # -----------------------------
    @staticmethod
    def make_type_rule(expected_type: Union[Type[Any], tuple[Type[Any], ...]]) -> ValidateFunc:
        """Return a validator that ensures non-None and type match."""

        def _check(value: Any, name: str) -> None:
            Validator.check_not_none(value, name)
            Validator.check_type(value, name, expected_type)

        return _check

    @staticmethod
    def make_non_empty_str() -> ValidateFunc:
        """Return a validator for non-empty string."""

        def _check(value: Any, name: str) -> None:
            Validator.check_not_none(value, name)
            Validator.check_non_empty_str(value, name)

        return _check

    @staticmethod
    def make_non_empty_list() -> ValidateFunc:
        """Return a validator for non-empty list."""

        def _check(value: Any, name: str) -> None:
            Validator.check_not_none(value, name)
            Validator.check_non_empty_list(value, name)

        return _check

    @staticmethod
    def make_uuid_rule() -> ValidateFunc:
        """Return a validator for valid UUID string."""

        def _check(value: Any, name: str) -> None:
            Validator.check_not_none(value, name)
            Validator.check_uuid(value, name)

        return _check

    @staticmethod
    def make_instance_of_rule(expected_type: Type[Any]) -> ValidateFunc:
        """Return a validator for instance of type."""

        def _check(value: Any, name: str) -> None:
            Validator.check_not_none(value, name)
            Validator.check_instance_of(value, name, expected_type)

        return _check

    @staticmethod
    def make_positive_rule() -> ValidateFunc:
        """Return a validator for positive number."""

        def _check(value: Any, name: str) -> None:
            Validator.check_not_none(value, name)
            Validator.check_type(value, name, (int, float))
            Validator.check_positive(value, name)

        return _check

    @staticmethod
    def make_file_rule() -> ValidateFunc:
        """Return a validator for file."""

        def _check(value: Any, name: str) -> None:
            Validator.check_not_none(value, name)
            Validator.check_file(value, name)

        return _check

    # -----------------------------
    # Predefined rules (common use)
    # -----------------------------
    str_non_empty: ValidateFunc = make_non_empty_str()
    str_not_none: ValidateFunc = make_type_rule(str)
    int_not_none: ValidateFunc = make_type_rule(int)
    float_not_none: ValidateFunc = make_type_rule(float)
    number_not_none: ValidateFunc = make_type_rule((int, float))
    bool_not_none: ValidateFunc = make_type_rule(bool)
    list_not_none: ValidateFunc = make_type_rule(list)
    list_not_empty: ValidateFunc = make_non_empty_list()
    uuid_not_none: ValidateFunc = make_uuid_rule()
    dict_not_none: ValidateFunc = make_type_rule(dict)
    tuple_not_none: ValidateFunc = make_type_rule(tuple)
    set_not_none: ValidateFunc = make_type_rule(set)
    positive_not_none: ValidateFunc = make_positive_rule()
    date_not_none: ValidateFunc = make_type_rule(date)
    datetime_not_none: ValidateFunc = make_type_rule(datetime)
    file_path_not_none: ValidateFunc = make_file_rule()

    # -----------------------------
    # Instance of (type) variants
    # -----------------------------
    instance_of: Callable[[Type[Any]], ValidateFunc] = make_instance_of_rule

    # -----------------------------
    # Optional (nullable) variants
    # -----------------------------
    @staticmethod
    def optional(expected_type: Union[Type[Any], tuple[Type[Any], ...]]) -> ValidateFunc:
        """Allow None, otherwise enforce type."""

        def _check(value: Any, name: str) -> None:
            if value is not None:
                Validator.check_type(value, name, expected_type)

        return _check

    @staticmethod
    def optional_uuid(value: Any, name: str) -> None:
        if value is not None:
            Validator.check_uuid(value, name)

    @staticmethod
    def optional_instance_of(expected_type: Type[Any]) -> ValidateFunc:
        """Allow None, otherwise enforce instance of type."""

        def _check(value: Any, name: str) -> None:
            if value is not None:
                Validator.check_instance_of(value, name, expected_type)

        return _check

    str_non_empty_or_none: ValidateFunc = optional(str)
    str_not_none_or_none: ValidateFunc = optional(str)
    number_not_none_or_none: ValidateFunc = optional((int, float))
    list_not_none_or_none: ValidateFunc = optional(list)
    uuid_not_none_or_none = optional_uuid
    is_optional_instance_of: Callable[[Type[Any]], ValidateFunc] = optional_instance_of
    datetime_not_none_or_none: ValidateFunc = optional(datetime)
    dict_not_none_or_none: ValidateFunc = optional(dict)
