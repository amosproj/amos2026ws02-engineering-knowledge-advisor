from services import Json


def build_dimensions_node(width: float, height: float, depth: float) -> dict[str, Json]:
    return {
        "@type": "og:Dimensions",
        "width": width,
        "height": height,
        "depth": depth,
    }


def build_assembly_group_node(
    identifier: str,
    name: str,
    path: str,
    dimensions: tuple[float | int, float | int, float | int] | None,
    parent_id: str | None,
    is_root: bool,
) -> dict[str, Json]:
    node: dict[str, Json] = {
        "@type": "og:AssemblyGroup",
        "identifier": identifier,
        "name": name,
    }
    props: dict[str, Json] = {"path": path}
    if dimensions is not None:
        props["dimensions"] = build_dimensions_node(*dimensions)
    node["properties"] = props
    if is_root:
        node["rootOf"] = parent_id
    elif parent_id is not None:
        node["partOf"] = parent_id
    return node
