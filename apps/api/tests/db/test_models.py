from types import NoneType, UnionType
from typing import Annotated, TypeAliasType, get_args, get_origin

import pytest
from sqlalchemy import Column, inspect

from db import (
    CommonColumn,
    FactColumn,
    FactModel,
    FactNodeColumn,
    FactNodeModel,
    HypernodeColumn,
    HypernodeModel,
    LinkColumn,
    LinkModel,
    ModelBase,
    RecordColumn,
    RecordModel,
    TableName,
    UploadColumn,
    UploadModel,
    VectorColumn,
    VectorModel,
)

COLUMN_NAMES: dict[type[ModelBase], set[str]] = {
    RecordModel: {CommonColumn.ID, *RecordColumn},
    LinkModel: {CommonColumn.RECORD_ID, CommonColumn.POSITION, *LinkColumn},
    UploadModel: set(UploadColumn),
    VectorModel: {CommonColumn.ID, *VectorColumn},
    HypernodeModel: {CommonColumn.ID, CommonColumn.VALUE, *HypernodeColumn},
    FactModel: {
        CommonColumn.ID,
        CommonColumn.RECORD_ID,
        CommonColumn.ANCHOR_ID,
        CommonColumn.LANE,
        *FactColumn,
    },
    FactNodeModel: {
        CommonColumn.LANE,
        CommonColumn.NODE_ID,
        CommonColumn.POSITION,
        *FactNodeColumn,
    },
}
MODELS: list[type[ModelBase]] = list(COLUMN_NAMES)


def get_columns(model: type[ModelBase]) -> dict[str, Column]:
    return {
        attr.key: attr.columns[0]
        for attr in inspect(model).column_attrs
        if isinstance(attr.columns[0], Column)
    }


def get_mapped_type(model: type[ModelBase], attr_name: str) -> tuple[type, bool]:
    """Returns the type in ``Mapped[...]`` of ``attr_name`` (without ``None``) and whether it allows ``None``."""
    annotation = get_args(model.__annotations__[attr_name])[0]
    if isinstance(annotation, TypeAliasType):
        annotation = annotation.__value__
    if get_origin(annotation) is Annotated:
        annotation = get_args(annotation)[0]
    members = (
        get_args(annotation) if isinstance(annotation, UnionType) else (annotation,)
    )
    (mapped_type,) = [member for member in members if member is not NoneType]
    return get_origin(mapped_type) or mapped_type, NoneType in members


def test_every_table_has_a_model():
    assert {model.get_table().name for model in MODELS} == set(TableName)
    assert set(ModelBase.metadata.tables) == set(TableName)


@pytest.mark.parametrize("model", MODELS, ids=lambda model: model.__name__)
def test_model_columns_are_the_enum_members(model: type[ModelBase]):
    assert {col.name for col in model.get_table().columns} == COLUMN_NAMES[model]


@pytest.mark.parametrize("model", MODELS, ids=lambda model: model.__name__)
def test_attributes_are_named_like_their_columns(model: type[ModelBase]):
    for attr_name, col in get_columns(model).items():
        assert attr_name == col.name


@pytest.mark.parametrize("model", MODELS, ids=lambda model: model.__name__)
def test_mapped_types_match_the_column_types(model: type[ModelBase]):
    for attr_name, col in get_columns(model).items():
        mapped_type, optional = get_mapped_type(model, attr_name)
        # JSONB and vector columns with python type ``object``
        assert issubclass(mapped_type, col.type.python_type), attr_name
        assert optional == col.nullable, attr_name
