#!/usr/bin/env python3
"""Read-only validation for Cornhole Biomechanics Lab library manifests."""

from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import UUID


CURRENT_SCHEMA_VERSION = 4


def _field(value: dict[str, Any], snake_case: str, camel_case: str) -> Any:
    """Accept legacy Python keys and the native app's Codable keys."""
    return value[snake_case] if snake_case in value else value.get(camel_case)


def _uuid(value: Any, context: str) -> str:
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError) as error:
        raise ValueError(f"{context} must be a UUID") from error


def _relative_path(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{context} must be a non-empty relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{context} must remain inside the library")
    return value


def validate_project(document: dict[str, Any], source: Path) -> list[str]:
    if not isinstance(document, dict):
        raise ValueError(f"{source}: root must be a JSON object")
    version = int(_field(document, "schema_version", "schemaVersion") or 1)
    if version < 1 or version > CURRENT_SCHEMA_VERSION:
        raise ValueError(f"{source}: unsupported schema_version {version}")
    _uuid(document.get("id"), f"{source}: project id")
    for field in ("athletes", "trials"):
        if not isinstance(document.get(field), list):
            raise ValueError(f"{source}: {field} must be an array")

    athlete_ids: set[str] = set()
    trial_ids: set[str] = set()
    for index, athlete in enumerate(document["athletes"]):
        athlete_id = _uuid(athlete.get("id"), f"{source}: athletes[{index}].id")
        if athlete_id in athlete_ids:
            raise ValueError(f"{source}: duplicate athlete id {athlete_id}")
        athlete_ids.add(athlete_id)

    warnings: list[str] = []
    for index, trial in enumerate(document["trials"]):
        trial_id = _uuid(trial.get("id"), f"{source}: trials[{index}].id")
        if trial_id in trial_ids:
            raise ValueError(f"{source}: duplicate trial id {trial_id}")
        trial_ids.add(trial_id)
        athlete_id = _uuid(_field(trial, "athlete_id", "athleteID"), f"{source}: trials[{index}].athlete_id")
        if athlete_id not in athlete_ids:
            raise ValueError(f"{source}: trial {trial_id} refers to a missing athlete")
        relative = _relative_path(
            _field(trial, "source_video_relative_path", "sourceVideoRelativePath"),
            f"{source}: trials[{index}].source_video_relative_path",
        )
        if not (source.parent / relative).exists():
            warnings.append(f"{source}: trial {trial_id} source video is missing (record retained)")
        analysis = _field(trial, "analysis_relative_path", "analysisRelativePath")
        if analysis is not None:
            _relative_path(analysis, f"{source}: trials[{index}].analysis_relative_path")
        for name in ('preparedVideoRelativePath', 'preparationDirectoryRelativePath'):
            if trial.get(name) is not None:
                _relative_path(trial[name], f'{source}: trials[{index}].{name}')

    reference_sets = _field(document, "reference_sets", "referenceSets") or []
    if not isinstance(reference_sets, list):
        raise ValueError(f"{source}: reference_sets must be an array")
    for index, reference in enumerate(reference_sets):
        _uuid(reference.get("id"), f"{source}: reference_sets[{index}].id")
        for trial_id_value in (_field(reference, "trial_ids", "trialIDs") or []):
            trial_id = _uuid(trial_id_value, f"{source}: reference_sets[{index}].trial_ids")
            if trial_id not in trial_ids:
                raise ValueError(f"{source}: reference set refers to missing trial {trial_id}")
    return warnings


def manifests(root: Path) -> list[Path]:
    ignored = {".git", ".venv", ".build", "dist", "__pycache__", ".pytest_cache"}
    return sorted(
        path for path in root.rglob("project.json")
        if not any(part in ignored for part in path.relative_to(root).parts)
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    found = manifests(args.root.resolve())
    if not found:
        print("No project.json library manifests found; schema scan completed.")
        return 0
    warning_count = 0
    for path in found:
        document = json.loads(path.read_text())
        warnings = validate_project(document, path)
        warning_count += len(warnings)
        print(f"VALID schema={_field(document, 'schema_version', 'schemaVersion') or 1} {path}")
        for warning in warnings:
            print(f"WARNING {warning}")
    print(f"Validated {len(found)} manifest(s); {warning_count} retained missing-file warning(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
