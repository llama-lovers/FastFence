"""Bounded semantic-suite YAML rejects aliases, duplicate keys and deep nesting."""

from typing import Any

import yaml
from yaml.events import AliasEvent


class SuiteLoader(yaml.SafeLoader):
    def __init__(self, stream: bytes) -> None:
        super().__init__(stream)
        self.depth = 0

    def compose_node(self, parent: Any, index: Any) -> Any:
        if self.check_event(AliasEvent) or self.depth >= 32:
            raise ValueError("Unsupported suite YAML structure")
        self.depth += 1
        try:
            return super().compose_node(parent, index)
        finally:
            self.depth -= 1

    def construct_mapping(self, node: Any, deep: bool = False) -> dict:
        keys = [self.construct_object(key, deep=deep) for key, _ in node.value]
        if any(not isinstance(key, str) for key in keys):
            raise ValueError("Suite keys must be strings")
        if len(set(keys)) != len(keys):
            raise ValueError("Duplicate suite field")
        return super().construct_mapping(node, deep=deep)


def load_suite_yaml(content: bytes) -> Any:
    return yaml.load(content, Loader=SuiteLoader)
