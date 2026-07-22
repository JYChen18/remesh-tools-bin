"""Batch scheduling for the object preparation workflow."""

from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .object import (
    SUPPORTED_INPUT_SUFFIXES,
    ObjectRecipe,
    ObjectResult,
    prepare_object,
)


def _prepare_job(args):
    return prepare_object(*args[0], **args[1])


def prepare_objects(
    input_directory: str | Path,
    output_directory: str | Path,
    *,
    recipe: ObjectRecipe | None = None,
    formats: tuple[str, ...] = ("mjcf", "urdf"),
    jobs: int = 1,
    overwrite: bool = False,
) -> list[ObjectResult]:
    """Prepare every supported mesh immediately inside a directory."""
    input_directory = Path(input_directory).expanduser().resolve()
    output_directory = Path(output_directory).expanduser().resolve()
    if not input_directory.is_dir():
        raise ValueError(f"Input directory does not exist: {input_directory}")
    inputs = sorted(
        path
        for path in input_directory.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_INPUT_SUFFIXES
    )
    if not inputs:
        raise ValueError(f"No supported mesh files found in {input_directory}")
    output_names = Counter(path.stem for path in inputs)
    duplicates = sorted(name for name, count in output_names.items() if count > 1)
    if duplicates:
        raise ValueError(
            "Input meshes would share output directories: " + ", ".join(duplicates)
        )
    if jobs <= 0:
        raise ValueError("jobs must be positive")
    work = [
        (
            (path, output_directory / path.stem),
            {"recipe": recipe, "formats": formats, "overwrite": overwrite},
        )
        for path in inputs
    ]
    if jobs == 1:
        return [_prepare_job(item) for item in work]

    results: dict[Path, ObjectResult] = {}
    failures: list[str] = []
    with ThreadPoolExecutor(max_workers=jobs) as executor:
        futures = {executor.submit(_prepare_job, item): item[0][0] for item in work}
        for future in as_completed(futures):
            source = futures[future]
            try:
                results[source] = future.result()
            except Exception as exc:
                failures.append(f"{source}: {exc}")
    if failures:
        raise RuntimeError("Object preparation failed:\n" + "\n".join(failures))
    return [results[path] for path in inputs]


prepare_folder = prepare_objects
