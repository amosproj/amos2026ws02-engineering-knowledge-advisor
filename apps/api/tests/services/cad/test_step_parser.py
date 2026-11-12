import logging
import math
from pathlib import Path

import pytest
from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec
from OCP.IFSelect import IFSelect_RetDone, IFSelect_ReturnStatus
from OCP.Interface import Interface_Static
from OCP.Standard import Standard_Failure
from OCP.STEPControl import STEPControl_Controller
from OCP.TDF import TDF_Label
from OCP.TDocStd import TDocStd_Document
from OCP.TopLoc import TopLoc_Location
from OCP.XCAFDoc import XCAFDoc_DocumentTool
from step_documents import DocumentBuilder, box, compound, point, set_name

from services.cad.errors import StepImportError
from services.cad.model import BoundingBox, CadDefinition, CadModel, CadOccurrence
from services.cad.step_parser import StepParser, document_walker, parser
from services.cad.xde import label_entry


@pytest.fixture
def builder() -> DocumentBuilder:
    return DocumentBuilder()


def parse_step(builder: DocumentBuilder, tmp_path: Path) -> CadModel:
    return StepParser().parse(builder.write_step(tmp_path / "model.step"))


def parse(builder: DocumentBuilder) -> CadModel:
    return StepParser().parse_document(builder.finish(), "model.step")


def by_name(model: CadModel, name: str) -> list[CadOccurrence]:
    return [occ for occ in model.occurrences if occ.name == name]


def children_of(model: CadModel, occurrence: CadOccurrence) -> list[CadOccurrence]:
    return [occ for occ in model.occurrences if occ.parent_id == occurrence.id]


def logged_warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        record.getMessage()
        for record in caplog.records
        if record.levelno == logging.WARNING
    ]


def definition_of(model: CadModel, occurrence: CadOccurrence) -> CadDefinition:
    return model.definitions[occurrence.definition_id]


def assert_box(
    box: BoundingBox | None,
    low: tuple[float, float, float],
    high: tuple[float, float, float],
) -> None:
    assert box is not None
    assert box.min == pytest.approx(low, abs=1e-6)
    assert box.max == pytest.approx(high, abs=1e-6)


def test_repeated_part_keeps_one_occurrence_per_placement(
    builder: DocumentBuilder, tmp_path: Path
):
    frame: TDF_Label = builder.assembly("Frame")
    screw: TDF_Label = builder.part("Screw", box())
    builder.add(frame, screw)
    builder.add(frame, screw, translation=(100, 0, 0))

    model: CadModel = parse_step(builder, tmp_path)

    screws: list[CadOccurrence] = by_name(model, "Screw")
    assert len(screws) == 2
    assert screws[0].id != screws[1].id
    assert screws[0].definition_id == screws[1].definition_id
    assert {screw.parent_id for screw in screws} == {model.roots[0].id}
    assert_box(model.bounding_box, (0, 0, 0), (0.11, 0.01, 0.01))


def test_reused_subassembly_has_one_occurrence_per_path(builder: DocumentBuilder):
    machine: TDF_Label = builder.assembly("Machine")
    module: TDF_Label = builder.assembly("Module")
    builder.add(module, builder.part("Screw", box()), translation=(10, 0, 0))
    builder.add(machine, module)
    builder.add(machine, module, translation=(0, 200, 0), rotation_z_degrees=90)

    model: CadModel = parse(builder)

    assert len(model.occurrences) == 5
    assert len({occ.id for occ in model.occurrences}) == 5
    second_module: CadOccurrence = by_name(model, "Module")[1]
    (screw_in_second,) = children_of(model, second_module)
    assert screw_in_second.id.startswith(f"{second_module.id}/")


def test_definition_box_is_in_its_own_coordinates(builder: DocumentBuilder):
    machine: TDF_Label = builder.assembly("Machine")
    module: TDF_Label = builder.assembly("Module")
    builder.add(module, builder.part("Screw", box()), translation=(10, 0, 0))
    builder.add(machine, module)
    builder.add(machine, module, translation=(0, 200, 0), rotation_z_degrees=90)

    model: CadModel = parse(builder)

    screws: list[CadOccurrence] = by_name(model, "Screw")
    assert_box(
        definition_of(model, screws[1]).bounding_box, (0, 0, 0), (0.01, 0.01, 0.01)
    )
    module_occurrence: CadOccurrence = by_name(model, "Module")[1]
    assert_box(
        definition_of(model, module_occurrence).bounding_box,
        (0.01, 0, 0),
        (0.02, 0.01, 0.01),
    )
    (root,) = model.roots
    assert_box(
        definition_of(model, root).bounding_box, (-0.01, 0, 0), (0.02, 0.22, 0.01)
    )
    assert model.bounding_box == definition_of(model, root).bounding_box


def test_definition_box_ignores_dropped_parts(builder: DocumentBuilder):
    machine: TDF_Label = builder.assembly("Machine")
    builder.add(machine, builder.part("Plate", box()), translation=(10, 0, 0))
    builder.add(machine, builder.part("Origin", point()), translation=(-500, 0, 0))

    model: CadModel = parse(builder)

    (root,) = model.roots
    assert_box(
        definition_of(model, root).bounding_box, (0.01, 0, 0), (0.02, 0.01, 0.01)
    )


def test_multiple_roots_and_duplicate_names_stay_distinct(builder: DocumentBuilder):
    builder.part("Bracket", box(10))
    builder.part("Bracket", box(20))

    model: CadModel = parse(builder)

    assert len(model.roots) == 2
    assert len({occ.definition_id for occ in model.roots}) == 2
    assert [occ.name for occ in model.roots] == ["Bracket", "Bracket"]


def test_multi_solid_part_is_kept_whole(builder: DocumentBuilder):
    builder.part("Weldment", compound(box(10), box(10, origin=(20, 0, 0))))

    model: CadModel = parse(builder)

    (weldment,) = model.occurrences
    assert_box(
        definition_of(model, weldment).bounding_box, (0, 0, 0), (0.03, 0.01, 0.01)
    )


def test_shape_type_placeholders_are_merged_into_their_part(
    builder: DocumentBuilder, caplog: pytest.LogCaptureFixture
):
    # Inventor export: a part holding its body and its origin point
    housing: TDF_Label = builder.assembly("Housing")
    builder.add(housing, builder.part("COMPOUND", compound(box())))
    builder.add(housing, builder.part("COMPOUND", point()))

    model: CadModel = parse(builder)

    (occurrence,) = model.occurrences
    assert occurrence.name == "Housing"
    assert_box(
        definition_of(model, occurrence).bounding_box, (0, 0, 0), (0.01, 0.01, 0.01)
    )
    assert logged_warnings(caplog) == []


def test_parts_without_faces_are_dropped_with_warning(
    builder: DocumentBuilder, caplog: pytest.LogCaptureFixture
):
    machine: TDF_Label = builder.assembly("Machine")
    builder.add(machine, builder.part("Plate", box()))
    builder.add(machine, builder.part("Origin", point()))

    model: CadModel = parse(builder)

    assert [occ.name for occ in model.occurrences] == ["Machine", "Plate"]
    assert logged_warnings(caplog) == ["model.step: dropped part without faces: Origin"]


def test_missing_names_fall_back_to_unnamed(builder: DocumentBuilder):
    builder.part(None, box())

    model: CadModel = parse(builder)

    assert model.occurrences[0].name == "Unnamed"


def test_missing_file_raises(tmp_path: Path):
    with pytest.raises(StepImportError, match="not found"):
        StepParser().parse(tmp_path / "missing.step")


def test_invalid_file_raises(tmp_path: Path):
    path: Path = tmp_path / "invalid.step"
    path.write_text("not a step file")
    with pytest.raises(StepImportError):
        StepParser().parse(path)


@pytest.mark.parametrize("nested", [False, True])
def test_only_invisible_geometry_raises(builder: DocumentBuilder, nested: bool):
    origin: TDF_Label = builder.part("Origin", point())
    if nested:
        builder.add(builder.assembly("Empty assembly"), origin)
    with pytest.raises(StepImportError, match="No visible shapes"):
        parse(builder)


def test_empty_document_raises(builder: DocumentBuilder):
    with pytest.raises(StepImportError, match="No visible shapes"):
        StepParser().parse_document(builder.document, "empty.step")


def test_unreadable_file_raises_import_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    path: Path = tmp_path / "unreadable.step"
    path.touch()

    def denied(*args: object, **kwargs: object) -> None:
        raise PermissionError("read denied")

    monkeypatch.setattr(Path, "open", denied)
    with pytest.raises(StepImportError, match="Could not read") as caught:
        StepParser().parse(path)
    assert isinstance(caught.value.__cause__, PermissionError)


@pytest.mark.parametrize("failure", [False, True])
def test_transfer_failure_raises_import_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: bool
):
    class Reader:
        def SetNameMode(self, enabled: bool) -> None:
            pass

        def SetColorMode(self, enabled: bool) -> None:
            pass

        def ReadFile(self, path: str) -> IFSelect_ReturnStatus:
            return IFSelect_RetDone

        def Transfer(self, document: TDocStd_Document) -> bool:
            if failure:
                raise Standard_Failure("transfer failed")
            return False

    path: Path = tmp_path / "failed.step"
    path.touch()
    monkeypatch.setattr(parser, "STEPCAFControl_Reader", Reader)
    with pytest.raises(StepImportError, match="Could not transfer"):
        StepParser().parse(path)


@pytest.mark.parametrize("with_visible_root", [False, True])
def test_rootless_cycle_is_rejected(builder: DocumentBuilder, with_visible_root: bool):
    first: TDF_Label = builder.assembly("First")
    second: TDF_Label = builder.assembly("Second")
    builder.add(first, second)
    builder.add(second, first)
    if with_visible_root:
        builder.part("Visible", box())
    # do not ask Open CASCADE to update a cyclic assembly's geometry
    with pytest.raises(StepImportError, match="Cyclic assembly reference"):
        StepParser().parse_document(builder.document, "cycle.step")


@pytest.mark.parametrize(
    ("product", "instance", "expected", "stored_instance"),
    [
        ("Product", "Placement", "Product", "Placement"),
        (None, "Placement", "Placement", None),
        (None, "NAUO123", "Unnamed", None),
        (None, "=>[0:1:2]", "Unnamed", None),
        ("Product", "NAUO123", "Product", None),
    ],
)
def test_product_and_instance_name_precedence(
    builder: DocumentBuilder,
    product: str | None,
    instance: str,
    expected: str,
    stored_instance: str | None,
):
    assembly: TDF_Label = builder.assembly("Assembly")
    set_name(builder.add(assembly, builder.part(product, box())), instance)

    model: CadModel = parse(builder)

    occurrence: CadOccurrence = children_of(model, model.roots[0])[0]
    assert occurrence.name == expected
    assert occurrence.instance_name == stored_instance


def test_dropped_parts_are_logged_once_per_definition(
    builder: DocumentBuilder, caplog: pytest.LogCaptureFixture
):
    assembly: TDF_Label = builder.assembly("Assembly")
    invisible: TDF_Label = builder.part("Origin", point())
    visible: TDF_Label = builder.part("Plate", box())
    for translation in [(0, 0, 0), (100, 0, 0)]:
        builder.add(assembly, invisible, translation)
        builder.add(assembly, visible, translation)

    model: CadModel = parse(builder)

    assert len(model.occurrences) == 3
    assert len(logged_warnings(caplog)) == 1


def test_mixed_named_components_are_not_normalized(builder: DocumentBuilder):
    assembly: TDF_Label = builder.assembly("Assembly")
    builder.add(assembly, builder.part("SOLID", box()))
    builder.add(assembly, builder.part("Named", box(20)))

    model: CadModel = parse(builder)

    assert [occ.name for occ in model.occurrences] == ["Assembly", "SOLID", "Named"]


def test_explicit_document_unit_applies_to_translations_and_boxes(
    builder: DocumentBuilder,
):
    assembly: TDF_Label = builder.assembly("Assembly")
    builder.add(assembly, builder.part("Part", box()), (20, 0, 0))
    document: TDocStd_Document = builder.finish()
    XCAFDoc_DocumentTool.SetLengthUnit_s(document, 0.01)

    model: CadModel = StepParser().parse_document(document, "centimeters.step")

    part: CadOccurrence = children_of(model, model.roots[0])[0]
    assert_box(definition_of(model, part).bounding_box, (0, 0, 0), (0.1, 0.1, 0.1))
    assert_box(model.bounding_box, (0.2, 0, 0), (0.3, 0.1, 0.1))
    assert model.document is document


def test_codepage_is_restored_after_failure():
    STEPControl_Controller.Init_s()
    previous: str = Interface_Static.CVal_s("read.step.codepage")
    with pytest.raises(RuntimeError), parser.step_codepage("CP1252"):
        assert Interface_Static.CVal_s("read.step.codepage") == "CP1252"
        raise RuntimeError("failed")
    assert Interface_Static.CVal_s("read.step.codepage") == previous


def test_utf8_detection_handles_chunk_boundaries_and_truncated_sequences(
    tmp_path: Path,
):
    path: Path = tmp_path / "encoding.step"
    path.write_bytes(b"a" * (parser.READ_CHUNK_SIZE - 1) + "é".encode())
    assert parser.is_utf8(path)
    path.write_bytes(b"incomplete \xc3")
    assert not parser.is_utf8(path)


def test_unresolved_component_warns_and_keeps_valid_siblings(
    builder: DocumentBuilder,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    assembly: TDF_Label = builder.assembly("Assembly")
    builder.add(assembly, builder.part("Visible", box()))
    unresolved: TDF_Label = builder.add(assembly, builder.part("Missing", box(20)))
    unresolved_entry: str = label_entry(unresolved)
    resolve = document_walker.DocumentWalker._resolve

    def resolve_with_missing(
        self: document_walker.DocumentWalker, label: TDF_Label
    ) -> TDF_Label | None:
        return None if label_entry(label) == unresolved_entry else resolve(self, label)

    monkeypatch.setattr(
        document_walker.DocumentWalker, "_resolve", resolve_with_missing
    )
    model: CadModel = parse(builder)

    assert [occ.name for occ in model.occurrences] == ["Assembly", "Visible"]
    (warning,) = logged_warnings(caplog)
    assert warning.endswith(f": {model.roots[0].id}/{unresolved_entry}")
    assert model.bounding_box == definition_of(model, model.occurrences[1]).bounding_box


def test_unicode_product_name_survives_step_round_trip(
    builder: DocumentBuilder, tmp_path: Path
):
    builder.part("Pièce 日本", box())
    model: CadModel = parse_step(builder, tmp_path)
    assert model.occurrences[0].name == "Pièce 日本"


def test_located_root_places_the_model_box(builder: DocumentBuilder):
    transform = gp_Trsf()
    transform.SetTranslation(gp_Vec(100, 200, 300))
    builder.part("Located", box().Moved(TopLoc_Location(transform)))

    model: CadModel = parse(builder)

    (root,) = model.roots
    assert_box(model.bounding_box, (0.1, 0.2, 0.3), (0.11, 0.21, 0.31))
    assert_box(definition_of(model, root).bounding_box, (0, 0, 0), (0.01, 0.01, 0.01))


def test_model_box_unites_placed_roots_and_skips_dropped_ones(builder: DocumentBuilder):
    rotation = gp_Trsf()
    rotation.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), math.pi / 2)
    builder.part("Rotated", box().Moved(TopLoc_Location(rotation)))
    translation = gp_Trsf()
    translation.SetTranslation(gp_Vec(100, 0, 0))
    builder.part("Shifted", box().Moved(TopLoc_Location(translation)))
    builder.part("Origin", point().Moved(TopLoc_Location(translation.Inverted())))

    model: CadModel = parse(builder)

    assert [occ.name for occ in model.roots] == ["Rotated", "Shifted"]
    assert_box(model.bounding_box, (-0.01, 0, 0), (0.11, 0.01, 0.01))
