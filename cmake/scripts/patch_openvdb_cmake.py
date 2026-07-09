from __future__ import annotations

import argparse
from pathlib import Path


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
            raise RuntimeError(f"Could not find the OpenVDB Boost find_package line in {path}")
        text = text.replace(boost_needle, boost_replacement)
    if replacement in text:
        path.write_text(text, encoding="utf-8")
        return
    if needle not in text:
        raise RuntimeError(f"Could not find the OpenVDB TBB find_package line in {path}")
    path.write_text(text.replace(needle, replacement), encoding="utf-8")


if __name__ == "__main__":
    main()
