"""Build a Streamlit input form from a tool's Pydantic input model.

One model field -> one widget, so a new tool needs no UI code:

    bool                -> checkbox
    Literal["a", "b"]   -> select box
    int, float          -> number input (with ge/le limits if declared)
    str                 -> text input, or a text area if the field declares
                           json_schema_extra={"multiline": True}
    X | None            -> the widget for X; an empty text box means None
"""

import types
import typing
from dataclasses import dataclass
from typing import Any, Literal, Union

from pydantic import BaseModel
from pydantic.fields import FieldInfo


@dataclass(frozen=True)
class WidgetSpec:
    """What widget to draw for one field (kept separate from Streamlit for testing)."""

    name: str
    kind: Literal["checkbox", "select", "int", "float", "text", "textarea"]
    label: str
    help: str | None
    default: Any
    optional: bool
    choices: tuple[Any, ...] = ()
    min_value: float | None = None
    max_value: float | None = None


def _unwrap(annotation: Any) -> tuple[Any, bool]:
    """Strip Annotated[...] and `| None`; return (inner type, optional)."""
    optional = False
    while True:
        origin = typing.get_origin(annotation)
        if origin is typing.Annotated:
            annotation = typing.get_args(annotation)[0]
        elif origin in (Union, types.UnionType):
            args = [a for a in typing.get_args(annotation) if a is not type(None)]
            optional = optional or len(args) < len(typing.get_args(annotation))
            if len(args) != 1:
                raise TypeError(f"unsupported union type for UI: {annotation}")
            annotation = args[0]
        else:
            return annotation, optional


def _bounds(field: FieldInfo) -> tuple[float | None, float | None]:
    low = high = None
    for meta in field.metadata:
        low = getattr(meta, "ge", low)
        high = getattr(meta, "le", high)
    return low, high


def widget_spec(name: str, field: FieldInfo) -> WidgetSpec:
    inner, optional = _unwrap(field.annotation)
    extra = field.json_schema_extra if isinstance(field.json_schema_extra, dict) else {}
    label = str(extra.get("label") or name.replace("_", " ").capitalize())
    default = None if field.is_required() else field.default
    common = dict(name=name, label=label, help=field.description, default=default,
                  optional=optional)  # fmt: skip

    if typing.get_origin(inner) is Literal:
        return WidgetSpec(kind="select", choices=typing.get_args(inner), **common)
    if inner is bool:
        return WidgetSpec(kind="checkbox", **common)
    if inner in (int, float):
        low, high = _bounds(field)
        return WidgetSpec(
            kind="int" if inner is int else "float", min_value=low, max_value=high, **common
        )
    if inner is str:
        return WidgetSpec(kind="textarea" if extra.get("multiline") else "text", **common)
    raise TypeError(f"unsupported field type for UI: {field.annotation}")


def widget_specs(model: type[BaseModel]) -> list[WidgetSpec]:
    return [widget_spec(n, f) for n, f in model.model_fields.items()]


def draw(spec: WidgetSpec, key: str) -> Any:
    """Draw one widget and return its value (call inside a Streamlit form)."""
    import streamlit as st

    if spec.kind == "checkbox":
        return st.checkbox(spec.label, value=bool(spec.default), help=spec.help, key=key)
    if spec.kind == "select":
        index = spec.choices.index(spec.default) if spec.default in spec.choices else 0
        return st.selectbox(spec.label, spec.choices, index=index, help=spec.help, key=key)
    if spec.kind in ("int", "float"):
        cast = int if spec.kind == "int" else float
        return st.number_input(
            spec.label,
            value=cast(spec.default) if spec.default is not None else None,
            min_value=cast(spec.min_value) if spec.min_value is not None else None,
            max_value=cast(spec.max_value) if spec.max_value is not None else None,
            help=spec.help,
            key=key,
        )
    widget = st.text_area if spec.kind == "textarea" else st.text_input
    text = widget(spec.label, value=spec.default or "", help=spec.help, key=key)
    return None if (spec.optional and not text.strip()) else text
