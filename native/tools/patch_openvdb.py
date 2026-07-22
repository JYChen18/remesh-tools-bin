"""Patch OpenVDB 8 build files and legacy headers for modern toolchains."""

from __future__ import annotations

import argparse
from pathlib import Path


def _replace_exact(
    path: Path,
    old: str,
    new: str,
    *,
    expected_count: int,
) -> None:
    text = path.read_text(encoding="utf-8")
    old_count = text.count(old)

    if old_count == expected_count:
        path.write_text(text.replace(old, new), encoding="utf-8")
        return
    if old_count == 0 and text.count(new) == expected_count:
        return

    raise RuntimeError(
        f"Expected {expected_count} occurrence(s) of {old!r} in {path}, "
        f"found {old_count}"
    )


def patch_legacy_headers(openvdb_dir: Path) -> None:
    _replace_exact(
        openvdb_dir / "tree" / "NodeManager.h",
        "OpT::template eval",
        "OpT::eval",
        expected_count=3,
    )
    _replace_exact(
        openvdb_dir / "tools" / "PointIndexGrid.h",
        "BaseLeaf::merge<Policy>(rhs);",
        "BaseLeaf::template merge<Policy>(rhs);",
        expected_count=1,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("cmake_lists", type=Path)
    args = parser.parse_args()

    path = args.cmake_lists
    text = path.read_text(encoding="utf-8")
    boost_needle = "find_package(Boost ${MINIMUM_BOOST_VERSION} REQUIRED COMPONENTS iostreams system)"
    boost_replacement = "\n".join(
        [
            "if(POLICY CMP0167)",
            "  cmake_policy(SET CMP0167 NEW)",
            "endif()",
            "find_package(Boost ${MINIMUM_BOOST_VERSION} REQUIRED COMPONENTS iostreams system)",
        ]
    )
    needle = "find_package(TBB ${MINIMUM_TBB_VERSION} REQUIRED COMPONENTS tbb)"
    replacement = "\n".join(
        [
            "if(NOT TARGET TBB::tbb)",
            "  find_package(TBB ${MINIMUM_TBB_VERSION} REQUIRED COMPONENTS tbb)",
            "endif()",
        ]
    )
    if boost_replacement not in text:
        if boost_needle not in text:
            raise RuntimeError(
                f"Could not find the OpenVDB Boost find_package line in {path}"
            )
        text = text.replace(boost_needle, boost_replacement)
    if replacement in text:
        path.write_text(text, encoding="utf-8")
    else:
        if needle not in text:
            raise RuntimeError(
                f"Could not find the OpenVDB TBB find_package line in {path}"
            )
        path.write_text(text.replace(needle, replacement), encoding="utf-8")

    patch_legacy_headers(path.parent)


if __name__ == "__main__":
    main()
