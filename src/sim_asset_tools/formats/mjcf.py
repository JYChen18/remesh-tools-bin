"""MJCF output helpers."""

from __future__ import annotations

import os
from pathlib import Path
from xml.etree import ElementTree as ET


def _relative_path(owner: Path, target: Path) -> str:
    return Path(os.path.relpath(target, start=owner.parent)).as_posix()


def _indent(element: ET.Element, level: int = 0) -> None:
    indent = "\n" + "  " * level
    if len(element):
        if not element.text or not element.text.strip():
            element.text = indent + "  "
        for child in element:
            _indent(child, level + 1)
        if not child.tail or not child.tail.strip():
            child.tail = indent
    if level and (not element.tail or not element.tail.strip()):
        element.tail = indent


def write_object_mjcf(path: Path, visual: Path, collisions: list[Path]) -> None:
    """Write a one-body MJCF model referencing prepared object meshes."""
    root = ET.Element("mujoco", {"model": "sim_asset"})
    ET.SubElement(root, "compiler", {"angle": "radian", "meshdir": "."})
    assets = ET.SubElement(root, "asset")
    ET.SubElement(
        assets,
        "mesh",
        {"name": "visual_mesh", "file": _relative_path(path, visual)},
    )
    for index, collision in enumerate(collisions):
        ET.SubElement(
            assets,
            "mesh",
            {
                "name": f"collision_{index:03d}",
                "file": _relative_path(path, collision),
            },
        )
    worldbody = ET.SubElement(root, "worldbody")
    body = ET.SubElement(worldbody, "body", {"name": "object"})
    ET.SubElement(
        body,
        "geom",
        {
            "name": "visual",
            "type": "mesh",
            "mesh": "visual_mesh",
            "density": "0",
            "contype": "0",
            "conaffinity": "0",
        },
    )
    for index in range(len(collisions)):
        ET.SubElement(
            body,
            "geom",
            {
                "name": f"collision_{index:03d}",
                "type": "mesh",
                "mesh": f"collision_{index:03d}",
            },
        )
    _indent(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(path, encoding="unicode", xml_declaration=False)
    with path.open("a", encoding="utf-8") as destination:
        destination.write("\n")
