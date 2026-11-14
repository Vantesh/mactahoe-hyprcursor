#!/usr/bin/env python3
"""Validate the generated Hyprcursor themes against upstream sources.

This intentionally checks only the things that would make a release wrong:
source integrity, preserved hotspots/sizes/frames/delays, aliases, the
compiled theme structure, and the upstream revision recorded in the build.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UPSTREAM = ROOT / "upstream" / "MacTahoe-icon-theme"
CURSOR_SRC = UPSTREAM / "cursors" / "src"
DIST = ROOT / "dist"
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
UPSTREAM_URL = "https://github.com/vinceliuice/MacTahoe-icon-theme"

VARIANTS = {
    "MacTahoe-hyprcursor": "svg",
    "MacTahoe-dark-hyprcursor": "svg-dark",
}

errors: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)


def svg_viewbox(path: Path) -> tuple[float, float, float, float]:
    root = ET.parse(path).getroot()
    viewbox = root.get("viewBox")
    if viewbox:
        values = [float(value) for value in re.split(r"[\s,]+", viewbox.strip())]
        if len(values) == 4 and values[2] > 0 and values[3] > 0:
            return values[0], values[1], values[2], values[3]

    def dimension(name: str) -> float | None:
        value = root.get(name)
        if not value:
            return None
        match = re.match(r"\s*([0-9]*\.?[0-9]+)", value)
        return float(match.group(1)) if match else None

    width, height = dimension("width"), dimension("height")
    if width and height:
        return 0.0, 0.0, width, height
    raise ValueError("no usable dimensions")


def parse_hl(text: str) -> dict[str, list[str]]:
    parsed: dict[str, list[str]] = {}
    for line_number, line in enumerate(text.splitlines(), 1):
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        if "=" not in line:
            raise ValueError(f"invalid hyprlang line {line_number}: {line!r}")
        key, value = line.split("=", 1)
        parsed.setdefault(key.strip(), []).append(value.strip())
    return parsed


def parse_define_size(value: str) -> tuple[float, str, int | None]:
    parts = [part.strip() for part in value.split(",")]
    if len(parts) not in (2, 3):
        raise ValueError(f"invalid define_size: {value!r}")
    size = float(parts[0])
    filename = parts[1]
    delay = int(parts[2]) if len(parts) == 3 else None
    return size, filename, delay


def source_metadata() -> tuple[dict[str, list[dict]], dict[str, str], str]:
    scalable = CURSOR_SRC / "scalable"
    if not scalable.is_dir():
        errors.append(f"missing upstream scalable directory: {scalable}")
        return {}, {}, ""

    base: dict[str, list[dict]] = {}
    all_scalable_dirs: set[str] = set()
    for cursor_dir in sorted(scalable.iterdir()):
        if not cursor_dir.is_dir():
            continue
        name = cursor_dir.name
        all_scalable_dirs.add(name)
        metadata_path = cursor_dir / "metadata.json"
        if not metadata_path.exists():
            errors.append(f"missing metadata: {metadata_path}")
            continue
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as error:
            errors.append(f"cannot parse {metadata_path}: {error}")
            continue

        if not metadata:
            errors.append(f"empty metadata: {metadata_path}")
            continue

        for frame in metadata:
            missing = {
                key
                for key in ("filename", "hotspot_x", "hotspot_y", "nominal_size")
                if key not in frame
            }
            if missing:
                errors.append(f"{name}: missing metadata keys {sorted(missing)}")
                continue
            if float(frame["nominal_size"]) <= 0:
                errors.append(f"{name}: invalid nominal size")
            if not str(frame["filename"]).endswith(".svg"):
                errors.append(f"{name}: non-SVG frame {frame['filename']}")

        delays = [frame.get("delay") for frame in metadata]
        if any(delay is not None for delay in delays):
            if any(delay is None or int(delay) <= 0 for delay in delays):
                errors.append(f"{name}: incomplete or invalid animation delays")
        elif len(metadata) > 1:
            errors.append(f"{name}: animated cursor has no delays")

        if f"{name}.svg" in {frame["filename"] for frame in metadata}:
            base[name] = metadata

    aliases = source_aliases(set(base), all_scalable_dirs)

    cursor_svg_file = CURSOR_SRC / "cursorSVG"
    if cursor_svg_file.exists():
        named = {
            line.strip()
            for line in cursor_svg_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
        for missing in sorted(named - set(base)):
            errors.append(f"cursorSVG entry has no base cursor: {missing}")

    revision = subprocess.run(
        ["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    return base, aliases, revision


def source_aliases(base_names: set[str], all_scalable_dirs: set[str]) -> dict[str, str]:
    cursor_list = CURSOR_SRC / "cursorList"
    aliases: dict[str, str] = {}

    for line_number, line in enumerate(cursor_list.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 2:
            errors.append(f"cursorList line {line_number} is invalid: {line!r}")
            continue
        alias, target = parts
        if alias in base_names:
            continue
        if alias in aliases:
            errors.append(f"duplicate cursorList alias: {alias}")
        aliases[alias] = target

    resolved: dict[str, str] = {}
    for alias in aliases:
        seen: list[str] = []
        current = alias
        while current not in base_names:
            if current not in aliases:
                errors.append(f"alias {alias} points to unknown cursor {current}")
                break
            if current in seen:
                errors.append(f"alias cycle: {' -> '.join([*seen, current])}")
                break
            seen.append(current)
            current = aliases[current]
        else:
            resolved[alias] = current

    for missing in sorted((all_scalable_dirs - base_names) - set(resolved)):
        errors.append(f"upstream alias is not covered by cursorList: {missing}")

    return resolved


def expected_geometry(
    name: str, metadata: list[dict], variant_dir: Path
) -> tuple[float, float, float] | None:
    hotspots: list[tuple[float, float]] = []
    nominal_ratios: list[float] = []
    for frame in metadata:
        svg_path = variant_dir / frame["filename"]
        try:
            min_x, min_y, width, height = svg_viewbox(svg_path)
        except (ET.ParseError, OSError, ValueError) as error:
            errors.append(f"{name}: cannot parse {svg_path}: {error}")
            return None
        if abs(width - height) > 1e-9:
            errors.append(f"{name}: non-square SVG {svg_path}")
        hotspots.append(
            (
                (float(frame["hotspot_x"]) - min_x) / width,
                (float(frame["hotspot_y"]) - min_y) / height,
            )
        )
        nominal_ratios.append(float(frame["nominal_size"]) / width)

    first = hotspots[0]
    for hotspot in hotspots[1:]:
        if abs(hotspot[0] - first[0]) > 1e-9 or abs(hotspot[1] - first[1]) > 1e-9:
            errors.append(f"{name}: animated frames have different hotspots")
    if not (0.0 <= first[0] <= 1.0 and 0.0 <= first[1] <= 1.0):
        errors.append(f"{name}: hotspot is outside 0..1: {first}")

    nominal_ratio = nominal_ratios[0]
    for ratio in nominal_ratios[1:]:
        if abs(ratio - nominal_ratio) > 1e-9:
            errors.append(f"{name}: animated frames have different nominal sizes")
    if not (0.1 <= nominal_ratio <= 2.0):
        errors.append(f"{name}: nominal size ratio outside 0.1..2.0: {nominal_ratio}")

    return first[0], first[1], nominal_ratio


def validate_sources(base: dict[str, list[dict]], aliases: dict[str, str]) -> None:
    for variant in set(VARIANTS.values()):
        variant_dir = CURSOR_SRC / variant
        if not variant_dir.is_dir():
            errors.append(f"missing artwork directory: {variant_dir}")
            continue
        for svg_path in sorted(variant_dir.glob("*.svg")):
            try:
                svg_viewbox(svg_path)
            except (ET.ParseError, OSError, ValueError) as error:
                errors.append(f"cannot parse SVG {svg_path}: {error}")

    for name, metadata in sorted(base.items()):
        for variant in set(VARIANTS.values()):
            variant_dir = CURSOR_SRC / variant
            for frame in metadata:
                svg_path = variant_dir / frame["filename"]
                check(svg_path.is_file(), f"{name}: missing {variant} artwork {svg_path.name}")
            if variant_dir.is_dir():
                expected_geometry(name, metadata, variant_dir)

    for alias, target in sorted(aliases.items()):
        check(target in base, f"alias {alias} resolves to missing cursor {target}")


def read_manifest(path: Path) -> dict[str, list[str]]:
    return parse_hl(path.read_text(encoding="utf-8"))


def validate_theme(
    theme_name: str,
    variant: str,
    base: dict[str, list[dict]],
    aliases: dict[str, str],
    revision: str,
) -> None:
    theme_dir = DIST / theme_name
    if not theme_dir.is_dir():
        errors.append(f"missing generated theme: {theme_dir}")
        return

    manifest_path = theme_dir / "manifest.hl"
    if not manifest_path.is_file():
        errors.append(f"{theme_name}: missing manifest.hl")
    else:
        try:
            manifest = read_manifest(manifest_path)
            check(manifest.get("name") == [theme_name], f"{theme_name}: wrong manifest name")
            check(
                manifest.get("cursors_directory") == ["hyprcursors"],
                f"{theme_name}: wrong cursors_directory",
            )
            check(manifest.get("version") == [VERSION], f"{theme_name}: wrong manifest version")
        except (OSError, ValueError) as error:
            errors.append(f"{theme_name}: invalid manifest.hl: {error}")

    build_info_path = theme_dir / "build-info.json"
    if not build_info_path.is_file():
        errors.append(f"{theme_name}: missing build-info.json")
    else:
        try:
            info = json.loads(build_info_path.read_text(encoding="utf-8"))
            check(
                info.get("upstream_revision") == revision,
                f"{theme_name}: build-info upstream revision mismatch",
            )
            check(
                info.get("upstream_repository") == UPSTREAM_URL,
                f"{theme_name}: build-info upstream repository mismatch",
            )
            check(
                info.get("project_version") == VERSION,
                f"{theme_name}: build-info project version mismatch",
            )
        except (json.JSONDecodeError, OSError) as error:
            errors.append(f"{theme_name}: invalid build-info.json: {error}")

    for filename in ("COPYING", "NOTICE"):
        packaged = theme_dir / filename
        if not packaged.is_file():
            errors.append(f"{theme_name}: missing {filename}")
        else:
            check(
                packaged.read_bytes() == (ROOT / filename).read_bytes(),
                f"{theme_name}: packaged {filename} differs from repository copy",
            )

    cursors_dir = theme_dir / "hyprcursors"
    if not cursors_dir.is_dir():
        errors.append(f"{theme_name}: missing hyprcursors directory")
        return

    actual_shapes = {path.stem for path in cursors_dir.glob("*.hlc")}
    check(actual_shapes == set(base), f"{theme_name}: compiled shapes do not match source")

    aliases_by_target: dict[str, list[str]] = {name: [] for name in base}
    for alias, target in aliases.items():
        aliases_by_target[target].append(alias)
    for target in aliases_by_target:
        aliases_by_target[target].sort()

    seen_overrides: dict[str, str] = {}
    variant_dir = CURSOR_SRC / variant

    for name, metadata in sorted(base.items()):
        hlc_path = cursors_dir / f"{name}.hlc"
        if not hlc_path.is_file():
            errors.append(f"{theme_name}: missing compiled shape {name}.hlc")
            continue
        try:
            with zipfile.ZipFile(hlc_path) as archive:
                names = set(archive.namelist())
                expected_files = {"meta.hl"} | {frame["filename"] for frame in metadata}
                check(
                    names == expected_files,
                    f"{theme_name}/{name}: unexpected files in .hlc: {sorted(names)}",
                )
                meta = parse_hl(archive.read("meta.hl").decode("utf-8"))
                for frame in metadata:
                    zipped = archive.read(frame["filename"])
                    source = (variant_dir / frame["filename"]).read_bytes()
                    check(
                        zipped == source,
                        f"{theme_name}/{name}: artwork bytes changed for {frame['filename']}",
                    )
        except (zipfile.BadZipFile, KeyError, OSError, ValueError) as error:
            errors.append(f"{theme_name}/{name}: invalid .hlc: {error}")
            continue

        check(meta.get("resize_algorithm") == ["none"], f"{theme_name}/{name}: resize_algorithm")

        expected_geom = expected_geometry(name, metadata, variant_dir)
        has_geometry = all(meta.get(key) for key in ("nominal_size", "hotspot_x", "hotspot_y"))
        if expected_geom and has_geometry:
            expected_hot = expected_geom[:2]
            try:
                actual_hot = (
                    float(meta["hotspot_x"][0]),
                    float(meta["hotspot_y"][0]),
                )
                check(
                    abs(actual_hot[0] - expected_hot[0]) <= 1e-12
                    and abs(actual_hot[1] - expected_hot[1]) <= 1e-12,
                    f"{theme_name}/{name}: hotspot not preserved",
                )
                check(
                    abs(float(meta["nominal_size"][0]) - expected_geom[2]) <= 1e-12,
                    f"{theme_name}/{name}: nominal size not preserved",
                )
            except (ValueError, IndexError) as error:
                errors.append(f"{theme_name}/{name}: invalid geometry: {error}")
        else:
            errors.append(f"{theme_name}/{name}: missing geometry values")

        actual_sizes: list[tuple[float, str, int | None]] = []
        for value in meta.get("define_size", []):
            try:
                actual_sizes.append(parse_define_size(value))
            except ValueError as error:
                errors.append(f"{theme_name}/{name}: {error}")
        expected_sizes = [
            (
                float(frame["nominal_size"]),
                frame["filename"],
                int(frame["delay"]) if "delay" in frame else None,
            )
            for frame in metadata
        ]
        check(
            actual_sizes == expected_sizes,
            f"{theme_name}/{name}: frames, sizes, or delays not preserved",
        )

        actual_overrides = meta.get("define_override", [])
        check(
            actual_overrides == aliases_by_target[name],
            f"{theme_name}/{name}: alias overrides not preserved",
        )
        for alias in actual_overrides:
            if alias in seen_overrides:
                errors.append(f"{theme_name}: alias {alias} is defined more than once")
            seen_overrides[alias] = name

    for alias, target in sorted(aliases.items()):
        check(
            seen_overrides.get(alias) == target,
            f"{theme_name}: alias {alias} does not resolve to {target}",
        )
    check(
        set(seen_overrides) == set(aliases),
        f"{theme_name}: compiled aliases do not match cursorList",
    )


def main() -> int:
    base, aliases, revision = source_metadata()
    if not errors:
        validate_sources(base, aliases)
        for theme_name, variant in VARIANTS.items():
            validate_theme(theme_name, variant, base, aliases, revision)

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(f"\nValidation failed with {len(errors)} error(s).", file=sys.stderr)
        return 1

    print(
        f"Validation passed: {len(base)} base cursors, {len(aliases)} aliases, 2 compiled themes."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
