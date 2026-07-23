"""Common manifest primitives for portable, verifiable asset bundles.

Manifest schemas are explicit and versioned. Artifact paths are POSIX-style,
relative to the bundle root, and must not escape it. JSON fingerprints use a
deterministic UTF-8 encoding with sorted keys, compact separators, and no NaN;
directory fingerprints cover every relative filename and file digest. Callers
finish referenced artifacts before atomically replacing ``asset.json``.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "sim-asset/v1"
OBJECT_SCHEMA_VERSION = "sim-object/v1"
MANIFEST_NAME = "asset.json"

_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


def sha256_file(path: str | os.PathLike[str]) -> str:
    """Return the SHA-256 digest of a file."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_json(value: object) -> str:
    """Return the SHA-256 digest of a canonical JSON encoding."""
    payload = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def sha256_directory(path: str | os.PathLike[str]) -> str:
    """Fingerprint a directory's filenames and file contents."""
    root = Path(path)
    if not root.is_dir():
        raise ValueError(f"Artifact directory does not exist: {root}")
    hashes = {
        artifact.relative_to(root).as_posix(): sha256_file(artifact)
        for artifact in root.rglob("*")
        if artifact.is_file()
    }
    return sha256_json(hashes)


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
    schema = value.get("schema")
    if schema not in (SCHEMA_VERSION, OBJECT_SCHEMA_VERSION):
        raise ValueError(
            f"Unsupported asset manifest schema {schema!r}; expected one of "
            f"{SCHEMA_VERSION!r}, {OBJECT_SCHEMA_VERSION!r}"
        )
    if schema == SCHEMA_VERSION and value.get("kind") != "body-surfaces":
        raise ValueError(f"Unsupported asset manifest kind: {value.get('kind')!r}")
    return value


def write_manifest(path: str | os.PathLike[str], value: dict[str, Any]) -> None:
    """Atomically publish a manifest after all referenced artifacts are ready."""
    path = Path(path)
    if value.get("schema") not in (SCHEMA_VERSION, OBJECT_SCHEMA_VERSION):
        raise ValueError(
            f"Manifest schema must be one of {SCHEMA_VERSION!r}, "
            f"{OBJECT_SCHEMA_VERSION!r}"
        )
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


def verify_sha256_map(root: Path, value: object) -> list[str]:
    """Return validation errors for a manifest path-to-SHA-256 mapping."""
    if not isinstance(value, dict):
        return ["manifest sha256 must be an object"]

    errors: list[str] = []
    for relative_path, expected in value.items():
        if not isinstance(relative_path, str):
            errors.append("manifest sha256 paths must be strings")
            continue
        try:
            path = resolve_artifact(root, relative_path)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if not isinstance(expected, str) or not _SHA256_PATTERN.fullmatch(expected):
            errors.append(f"artifact has an invalid SHA-256 digest: {relative_path}")
            continue
        if not path.is_file():
            errors.append(f"artifact is missing: {relative_path}")
            continue
        if sha256_file(path) != expected:
            errors.append(f"artifact hash does not match: {relative_path}")
    return errors
