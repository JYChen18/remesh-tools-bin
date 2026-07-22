"""URDF output helpers."""

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


def write_object_urdf(path: Path, visual: Path, collisions: list[Path]) -> None:
    """Write a one-link URDF model referencing prepared object meshes."""
    root = ET.Element("robot", {"name": "sim_asset"})
    link = ET.SubElement(root, "link", {"name": "object"})
    visual_node = ET.SubElement(link, "visual")
    visual_geometry = ET.SubElement(visual_node, "geometry")
    ET.SubElement(
        visual_geometry,
        "mesh",
        {"filename": _relative_path(path, visual)},
    )
    for collision in collisions:
        collision_node = ET.SubElement(link, "collision")
        geometry = ET.SubElement(collision_node, "geometry")
        ET.SubElement(
            geometry,
            "mesh",
            {"filename": _relative_path(path, collision)},
        )
    _indent(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(path, encoding="unicode", xml_declaration=False)
    with path.open("a", encoding="utf-8") as destination:
        destination.write("\n")
