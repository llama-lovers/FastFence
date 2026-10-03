"""Explicit trusted startup Python extensions; never sourced from policy data."""

import inspect
import re
from functools import lru_cache
from pathlib import Path
from types import ModuleType

from detect_secrets.plugins.base import BasePlugin, RegexBasedDetector

ERROR = "Custom secret detector configuration is invalid; check trusted plugin files"


@lru_cache(maxsize=16)
def load_plugin_classes(
    paths: tuple[Path, ...], max_file_bytes: int
) -> tuple[type[BasePlugin], ...]:
    """Cache startup source loading; operators restart after changing a file."""
    try:
        if len(paths) > 8 or len(set(paths)) != len(paths):
            raise ValueError(ERROR)
        classes: list[type[BasePlugin]] = []
        for index, path in enumerate(paths):
            if path.suffix != ".py" or not path.is_file():
                raise ValueError(ERROR)
            with path.open("rb") as source:
                content = source.read(max_file_bytes + 1)
            if len(content) > max_file_bytes:
                raise ValueError(ERROR)
            module = ModuleType(f"fastfence_trusted_secret_plugin_{index}")
            exec(
                compile(content, "<trusted-secret-plugin>", "exec"),
                module.__dict__,
            )
            local = [
                value
                for value in vars(module).values()
                if inspect.isclass(value)
                and issubclass(value, BasePlugin)
                and value is not BasePlugin
                and value.__module__ == module.__name__
            ]
            if not local or len(classes) + len(local) > 32:
                raise ValueError(ERROR)
            classes.extend(local)
        return tuple(classes)
    except (Exception, SystemExit):
        raise ValueError(ERROR) from None


def custom_plugins(
    paths: tuple[Path, ...], max_file_bytes: int, reserved_names: set[str]
) -> tuple[BasePlugin, ...]:
    try:
        plugins = []
        names = set(reserved_names)
        for cls in load_plugin_classes(paths, max_file_bytes):
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,79}", cls.__name__):
                raise ValueError(ERROR)
            if cls.__name__ in names:
                raise ValueError(ERROR)
            names.add(cls.__name__)
            plugin = cls()
            if not callable(plugin.analyze_string):
                raise ValueError(ERROR)
            if isinstance(plugin, RegexBasedDetector):
                if not isinstance(plugin.denylist, tuple | list):
                    raise ValueError(ERROR)
                if not 1 <= len(plugin.denylist) <= 32:
                    raise ValueError(ERROR)
                if any(
                    not isinstance(pattern, re.Pattern)
                    or not isinstance(pattern.pattern, str)
                    or len(pattern.pattern) > 8192
                    or pattern.search("") is not None
                    for pattern in plugin.denylist
                ):
                    raise ValueError(ERROR)
            plugins.append(plugin)
        return tuple(plugins)
    except (Exception, SystemExit):
        raise ValueError(ERROR) from None
