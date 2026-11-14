#!/usr/bin/env python3
"""Build Hyprcursor themes from the upstream MacTahoe cursor sources.

The upstream repository is a submodule that tracks `main`. By default this
script fetches the newest upstream revision before building. Pass --no-fetch
to build the revision that is currently checked out in the submodule.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UPSTREAM = ROOT / "upstream" / "MacTahoe-icon-theme"
CURSOR_SRC = UPSTREAM / "cursors" / "src"
DIST = ROOT / "dist"
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
UPSTREAM_URL = "https://github.com/vinceliuice/MacTahoe-icon-theme"

# 2000-01-01 00:00:00 UTC. hyprcursor-util copies source mtimes into .hlc
# zips, so fixed mtimes keep repeated builds byte-for-byte identical.
FIXED_MTIME = 946684800

VARIANTS = {
    "MacTahoe-hyprcursor": ("svg", "light"),
    "MacTahoe-dark-hyprcursor": ("svg-dark", "dark"),
}


class BuildError(Exception):
    pass


def run(command: list[str]) -> None:
    print("+ " + " ".join(command), flush=True)
    # .hlc zips store local-time DOS timestamps; pin the zone so output is
    # identical on every machine.
    subprocess.run(command, check=True, env={**os.environ, "TZ": "UTC"})


def update_upstream(fetch: bool) -> str:
    if not (UPSTREAM / ".git").exists():
        run(
            [
                "git",
                "-C",
                str(ROOT),
                "submodule",
                "update",
                "--init",
                "--recursive",
                "--",
                "upstream/MacTahoe-icon-theme",
            ]
        )

    if fetch:
        run(["git", "-C", str(UPSTREAM), "fetch", "--quiet", "origin", "main"])
        run(["git", "-C", str(UPSTREAM), "checkout", "--quiet", "--detach", "FETCH_HEAD"])

    if not CURSOR_SRC.is_dir():
        raise BuildError(f"upstream cursor sources not found: {CURSOR_SRC}")

    return subprocess.run(
        ["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def svg_viewbox(path: Path) -> tuple[float, float, float, float]:
    """Return the SVG viewBox (min_x, min_y, width, height)."""
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as error:
        raise BuildError(f"cannot parse SVG {path}: {error}") from error

    viewbox = root.get("viewBox")
    if viewbox:
        try:
            values = [float(value) for value in re.split(r"[\s,]+", viewbox.strip())]
        except ValueError as error:
            raise BuildError(f"invalid viewBox in {path}: {viewbox}") from error
        if len(values) == 4 and values[2] > 0 and values[3] > 0:
            return values[0], values[1], values[2], values[3]

    # A few upstream SVGs omit width/height, but all currently have a viewBox.
    # Keep this fallback so a future omission fails with a useful message only
    # if the artwork truly has no usable dimensions.
    def dimension(name: str) -> float | None:
        value = root.get(name)
        if not value:
            return None
        match = re.match(r"\s*([0-9]*\.?[0-9]+)", value)
        return float(match.group(1)) if match else None

    width, height = dimension("width"), dimension("height")
    if width and height:
        return 0.0, 0.0, width, height

    raise BuildError(f"SVG has no usable dimensions: {path}")


def cursor_geometry(metadata: list[dict], variant_dir: Path) -> tuple[float, float, float]:
    """Convert upstream cursor geometry to Hyprcursor's coordinate system.

    Upstream stores hotspots in SVG canvas pixels and a separate nominal size.
    Hyprcursor stores the hotspot as a fraction of the rendered image and a
    nominal scale relative to the requested cursor size. Normalizing the
    hotspot by the canvas size and the nominal size by the canvas size keeps
    the original nominal-size semantics and physical hotspot position.
    """
    hotspots: list[tuple[float, float]] = []
    nominal_ratios: list[float] = []
    for frame in metadata:
        svg_path = variant_dir / frame["filename"]
        min_x, min_y, width, height = svg_viewbox(svg_path)
        if abs(width - height) > 1e-9:
            raise BuildError(f"cursor image is not square: {svg_path}")
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
            raise BuildError(
                "animated frames use different hotspot coordinates: "
                f"{', '.join(frame['filename'] for frame in metadata)}"
            )

    if not (0.0 <= first[0] <= 1.0 and 0.0 <= first[1] <= 1.0):
        raise BuildError(f"hotspot outside the image after conversion: {first}")

    nominal_ratio = nominal_ratios[0]
    for ratio in nominal_ratios[1:]:
        if abs(ratio - nominal_ratio) > 1e-9:
            raise BuildError(
                "animated frames use different nominal sizes: "
                f"{', '.join(frame['filename'] for frame in metadata)}"
            )
    if not (0.1 <= nominal_ratio <= 2.0):
        raise BuildError(
            f"nominal size ratio {nominal_ratio} is outside Hyprcursor's 0.1..2.0 range"
        )

    return first[0], first[1], nominal_ratio


def validate_metadata(name: str, metadata: list[dict]) -> None:
    if not metadata:
        raise BuildError(f"empty metadata for cursor {name}")

    for frame in metadata:
        for key in ("filename", "hotspot_x", "hotspot_y", "nominal_size"):
            if key not in frame:
                raise BuildError(f"cursor {name} metadata is missing {key}")
        if float(frame["nominal_size"]) <= 0:
            raise BuildError(f"cursor {name} has invalid nominal size")
        if not frame["filename"].endswith(".svg"):
            raise BuildError(f"cursor {name} has a non-SVG frame: {frame['filename']}")

    delays = [frame.get("delay") for frame in metadata]
    if any(delay is not None for delay in delays):
        if any(delay is None or int(delay) <= 0 for delay in delays):
            raise BuildError(f"cursor {name} has incomplete or invalid animation delays")
    elif len(metadata) > 1:
        raise BuildError(f"animated cursor {name} has no delays")


def load_source() -> tuple[dict[str, list[dict]], dict[str, str]]:
    scalable = CURSOR_SRC / "scalable"
    if not scalable.is_dir():
        raise BuildError(f"upstream scalable metadata not found: {scalable}")

    base: dict[str, list[dict]] = {}
    all_scalable_dirs: set[str] = set()

    for cursor_dir in sorted(scalable.iterdir()):
        if not cursor_dir.is_dir():
            continue
        name = cursor_dir.name
        all_scalable_dirs.add(name)
        metadata_path = cursor_dir / "metadata.json"
        if not metadata_path.exists():
            raise BuildError(f"missing metadata: {metadata_path}")
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as error:
            raise BuildError(f"cannot read {metadata_path}: {error}") from error
        validate_metadata(name, metadata)
        if f"{name}.svg" in {frame["filename"] for frame in metadata}:
            base[name] = metadata

    if not base:
        raise BuildError("no base cursors found in upstream scalable directory")

    aliases = load_aliases(set(base), all_scalable_dirs)

    cursor_svg_file = CURSOR_SRC / "cursorSVG"
    if cursor_svg_file.exists():
        names = cursor_svg_file.read_text(encoding="utf-8").splitlines()
        named = {line.strip() for line in names if line.strip()}
        missing = sorted(named - set(base))
        if missing:
            raise BuildError(f"cursorSVG entries have no base cursor: {', '.join(missing)}")

    return base, aliases


def load_aliases(base_names: set[str], all_scalable_dirs: set[str]) -> dict[str, str]:
    cursor_list = CURSOR_SRC / "cursorList"
    aliases: dict[str, str] = {}
    skipped: list[str] = []

    for line_number, line in enumerate(cursor_list.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 2:
            raise BuildError(f"invalid cursorList line {line_number}: {line!r}")
        alias, target = parts
        if alias in base_names:
            # Upstream's build only creates an alias when the name does not
            # already exist. Real artwork wins over a cursorList mapping.
            skipped.append(alias)
            continue
        if alias in aliases:
            raise BuildError(f"duplicate cursorList alias: {alias}")
        aliases[alias] = target

    resolved: dict[str, str] = {}
    for alias in aliases:
        seen: list[str] = []
        current = alias
        while current not in base_names:
            if current not in aliases:
                raise BuildError(f"alias {alias} points to unknown cursor {current}")
            if current in seen:
                raise BuildError(f"alias cycle: {' -> '.join([*seen, current])}")
            seen.append(current)
            current = aliases[current]
        resolved[alias] = current

    unmapped = sorted((all_scalable_dirs - base_names) - set(resolved))
    if unmapped:
        raise BuildError(
            "upstream cursor aliases are not covered by cursorList: " + ", ".join(unmapped)
        )

    if skipped:
        print("Aliases ignored because real artwork exists: " + ", ".join(skipped))

    return resolved


def format_integer(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else repr(float(value))


def write_meta(
    path: Path,
    metadata: list[dict],
    hotspot: tuple[float, float],
    nominal_ratio: float,
    overrides: list[str],
) -> None:
    lines = [
        "resize_algorithm = none",
        f"nominal_size = {nominal_ratio!r}",
        f"hotspot_x = {hotspot[0]!r}",
        f"hotspot_y = {hotspot[1]!r}",
    ]
    lines.extend(f"define_override = {alias}" for alias in overrides)
    for frame in metadata:
        line = f"define_size = {format_integer(frame['nominal_size'])}, {frame['filename']}"
        if "delay" in frame:
            line += f", {format_integer(frame['delay'])}"
        lines.append(line)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def set_fixed_mtimes(root: Path) -> None:
    for path in sorted(root.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        os.utime(path, (FIXED_MTIME, FIXED_MTIME))
    os.utime(root, (FIXED_MTIME, FIXED_MTIME))


def write_theme(
    theme_name: str,
    variant_dir: Path,
    base: dict[str, list[dict]],
    aliases: dict[str, str],
) -> Path:
    _, variant_label = VARIANTS[theme_name]
    work_theme = DIST / "work" / theme_name
    (work_theme / "hyprcursors").mkdir(parents=True)

    manifest = (
        f"name = {theme_name}\n"
        f"description = MacTahoe cursor theme ({variant_label}) for Hyprcursor\n"
        f"version = {VERSION}\n"
        "cursors_directory = hyprcursors\n"
    )
    (work_theme / "manifest.hl").write_text(manifest, encoding="utf-8")

    aliases_by_target: dict[str, list[str]] = {name: [] for name in base}
    for alias, target in aliases.items():
        aliases_by_target[target].append(alias)
    for target in aliases_by_target:
        aliases_by_target[target].sort()

    for name in sorted(base):
        metadata = base[name]
        cursor_dir = work_theme / "hyprcursors" / name
        cursor_dir.mkdir()
        for frame in metadata:
            shutil.copyfile(variant_dir / frame["filename"], cursor_dir / frame["filename"])
        hotspot_x, hotspot_y, nominal_ratio = cursor_geometry(metadata, variant_dir)
        write_meta(
            cursor_dir / "meta.hl",
            metadata,
            (hotspot_x, hotspot_y),
            nominal_ratio,
            aliases_by_target[name],
        )

    set_fixed_mtimes(work_theme)
    return work_theme


def compile_theme(work_theme: Path, theme_name: str) -> Path:
    compile_dir = DIST / "_compile"
    if compile_dir.exists():
        shutil.rmtree(compile_dir)
    compile_dir.mkdir()
    run(["hyprcursor-util", "--create", str(work_theme), "--output", str(compile_dir)])

    produced = compile_dir / f"theme_{theme_name}"
    if not produced.is_dir():
        raise BuildError(f"hyprcursor-util did not produce the expected directory: {produced}")

    target = DIST / theme_name
    if target.exists():
        shutil.rmtree(target)
    produced.rename(target)
    return target


def build_info() -> dict:
    revision = subprocess.run(
        ["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return {
        "project": "MacTahoe Hyprcursor",
        "project_version": VERSION,
        "upstream_repository": UPSTREAM_URL,
        "upstream_revision": revision,
        "variants": sorted(VARIANTS),
    }


def write_build_info(theme_dir: Path, info: dict) -> None:
    path = theme_dir / "build-info.json"
    path.write_text(json.dumps(info, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.utime(path, (FIXED_MTIME, FIXED_MTIME))


def copy_distribution_files(theme_dir: Path) -> None:
    for filename in ("COPYING", "NOTICE"):
        target = theme_dir / filename
        shutil.copyfile(ROOT / filename, target)
        os.utime(target, (FIXED_MTIME, FIXED_MTIME))


def create_archive(theme_name: str) -> Path:
    source = DIST / theme_name
    archive = DIST / f"{theme_name}.tar.gz"
    entries = [
        source,
        *sorted(source.rglob("*"), key=lambda item: item.relative_to(DIST).as_posix()),
    ]

    with (
        archive.open("wb") as raw,
        gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=9, mtime=0, filename="") as gz,
        tarfile.open(fileobj=gz, mode="w", format=tarfile.PAX_FORMAT) as tar,
    ):
        for path in entries:
            info = tar.gettarinfo(str(path), path.relative_to(DIST).as_posix())
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            info.mtime = 0
            info.mode = 0o755 if path.is_dir() else 0o644
            if path.is_dir():
                tar.addfile(info)
            else:
                with path.open("rb") as handle:
                    tar.addfile(info, handle)

    return archive


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-fetch",
        action="store_true",
        help="build the upstream revision already checked out instead of fetching main",
    )
    args = parser.parse_args()

    revision = update_upstream(fetch=not args.no_fetch)
    print(f"Upstream revision: {revision}")

    base, aliases = load_source()
    print(f"Source cursors: {len(base)} base, {len(aliases)} aliases")

    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir()

    compiled: dict[str, Path] = {}
    for theme_name, (variant, _) in VARIANTS.items():
        print(f"\n=== {theme_name}")
        work_theme = write_theme(theme_name, CURSOR_SRC / variant, base, aliases)
        compiled[theme_name] = compile_theme(work_theme, theme_name)

    info = build_info()
    if info["upstream_revision"] != revision:
        raise BuildError("upstream revision changed while building")
    for theme_dir in compiled.values():
        write_build_info(theme_dir, info)
        copy_distribution_files(theme_dir)
    write_build_info(DIST, info)

    run([sys.executable, str(ROOT / "scripts" / "validate.py")])

    shutil.rmtree(DIST / "work")
    shutil.rmtree(DIST / "_compile")

    for theme_name in VARIANTS:
        archive = create_archive(theme_name)
        print(f"Archive: {archive.relative_to(ROOT)}")

    (DIST / "build-info.json").write_text(
        json.dumps(info, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("\nBuild complete.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BuildError, subprocess.CalledProcessError) as error:
        print(f"\nERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from None
