"""Safe publication helpers for generated asset directories."""

from __future__ import annotations

import os
import shutil
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


def ensure_safe_output(input_path: Path, output_directory: Path) -> None:
    """Reject output directories that contain required input or the current cwd."""
    current_directory = Path.cwd().resolve()
    if (
        input_path == output_directory
        or output_directory in input_path.parents
        or current_directory == output_directory
        or output_directory in current_directory.parents
    ):
        raise ValueError(
            "Output directory must not contain the input or current working directory: "
            f"{output_directory}"
        )


def ensure_output_available(output_directory: Path, *, overwrite: bool) -> None:
    """Validate that an output directory may be replaced."""
    if not output_directory.exists():
        return
    if not output_directory.is_dir():
        raise FileExistsError(f"Output path is not a directory: {output_directory}")
    if any(output_directory.iterdir()) and not overwrite:
        raise FileExistsError(
            f"Output directory is not empty: {output_directory}; "
            "pass overwrite=True to replace it"
        )


def create_staging_directory(output_directory: Path) -> Path:
    """Create a sibling staging directory on the destination filesystem."""
    output_directory.parent.mkdir(parents=True, exist_ok=True)
    return Path(
        tempfile.mkdtemp(
            prefix=f".{output_directory.name}.staging-",
            dir=output_directory.parent,
        )
    )


def publish_directory(
    staging_directory: Path,
    output_directory: Path,
    *,
    overwrite: bool,
) -> None:
    """Publish a complete staged directory, rolling back a failed replacement."""
    ensure_output_available(output_directory, overwrite=overwrite)
    if not output_directory.exists():
        os.replace(staging_directory, output_directory)
        return

    backup_directory = output_directory.with_name(
        f".{output_directory.name}.backup-{uuid.uuid4().hex}"
    )
    os.replace(output_directory, backup_directory)
    try:
        os.replace(staging_directory, output_directory)
    except BaseException:
        os.replace(backup_directory, output_directory)
        raise

    shutil.rmtree(backup_directory)


@contextmanager
def staged_directory(
    output_directory: Path,
    *,
    overwrite: bool,
) -> Iterator[Path]:
    """Yield a staging directory, then publish it or clean it up."""
    ensure_output_available(output_directory, overwrite=overwrite)
    staging_directory = create_staging_directory(output_directory)
    try:
        yield staging_directory
        publish_directory(
            staging_directory,
            output_directory,
            overwrite=overwrite,
        )
    finally:
        if staging_directory.exists():
            shutil.rmtree(staging_directory)
