"""Versioned manifests shared by prepared simulation assets."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "sim-asset/v1"
MANIFEST_NAME = "asset.json"


def sha256_file(path: str | os.PathLike[str]) -> str:
    """Return the SHA-256 digest of a file."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative_artifact_path(root: Path, path: Path) -> str:
    """Return a portable manifest path and reject paths outside the asset root."""
    try:
        relative = path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"Artifact is outside asset root {root}: {path}") from exc
    return relative.as_posix()


def resolve_artifact(root: Path, value: str) -> Path:
    """Resolve a manifest-relative artifact path without allowing traversal."""
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(
            f"Manifest artifact path must be relative and contained: {value!r}"
        )
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"Manifest artifact path escapes its root: {value!r}") from exc
    return path


def load_manifest(path_or_directory: str | os.PathLike[str]) -> dict[str, Any]:
    """Load and minimally validate an asset manifest."""
    path = Path(path_or_directory)
    if path.is_dir():
        path = path / MANIFEST_NAME
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Asset manifest does not exist: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read asset manifest {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Asset manifest must contain a JSON object: {path}")
    if value.get("schema") != SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported asset manifest schema {value.get('schema')!r}; expected {SCHEMA_VERSION!r}"
        )
    if value.get("kind") not in ("object", "body-surfaces"):
        raise ValueError(f"Unsupported asset manifest kind: {value.get('kind')!r}")
    return value


def write_manifest(path: str | os.PathLike[str], value: dict[str, Any]) -> None:
    """Atomically publish a manifest after all referenced artifacts are ready."""
    path = Path(path)
    if value.get("schema") != SCHEMA_VERSION:
        raise ValueError(f"Manifest schema must be {SCHEMA_VERSION!r}")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, indent=2, sort_keys=True) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as destination:
            destination.write(payload)
            destination.flush()
            os.fsync(destination.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def verify_file_records(root: Path, records: Iterable[object]) -> list[str]:
    """Return validation errors for manifest records containing path and sha256."""
    errors: list[str] = []
    for record in records:
        if not isinstance(record, dict):
            errors.append("artifact record must be an object")
            continue
        value = record.get("path")
        if not isinstance(value, str):
            errors.append("artifact record is missing a string path")
            continue
        try:
            path = resolve_artifact(root, value)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if not path.is_file():
            errors.append(f"artifact is missing: {value}")
            continue
        expected = record.get("sha256")
        if expected is not None and expected != sha256_file(path):
            errors.append(f"artifact hash does not match: {value}")
    return errors
