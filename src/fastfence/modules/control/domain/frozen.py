from collections.abc import Mapping
from types import MappingProxyType
from typing import Annotated, Any

from pydantic import AfterValidator, ConfigDict, PlainSerializer

from fastfence.shared.models import StrictModel


class FrozenControlModel(StrictModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, validate_default=True
    )


def freeze_mapping[Value](value: Mapping[str, Value]) -> Mapping[str, Value]:
    return MappingProxyType(dict(value))


def serialize_mapping(value: Mapping[str, StrictModel]) -> dict[str, Any]:
    return {key: item.model_dump(mode="json") for key, item in value.items()}


def serialize_roles(value: tuple[str, ...]) -> list[str]:
    return list(value)


type FrozenMap[Value] = Annotated[
    Mapping[str, Value],
    AfterValidator(freeze_mapping),
    PlainSerializer(serialize_mapping, return_type=dict[str, Any]),
]
type Roles = Annotated[
    tuple[str, ...], PlainSerializer(serialize_roles, return_type=list[str])
]
