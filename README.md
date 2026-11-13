# MacTahoe Hyprcursor

A minimal, automatically updated conversion of the
[MacTahoe cursor theme](https://github.com/vinceliuice/MacTahoe-icon-theme)
to the native [Hyprcursor](https://github.com/hyprwm/hyprcursor) format.

The theme uses the original SVG artwork, preserves the upstream hotspots,
nominal sizes, animation frames/delays, and alias mappings. Shadows are
disabled. The build and release process is fully automated; generated files
are never committed.

## Variants

- `MacTahoe-hyprcursor` — light
- `MacTahoe-dark-hyprcursor` — dark

## Upstream and license

This project is a derivative conversion, not an official upstream project.
The cursor artwork and source metadata come from
[vinceliuice/MacTahoe-icon-theme](https://github.com/vinceliuice/MacTahoe-icon-theme)
by Vince Liuice, licensed under GPL-3.0. See [COPYING](COPYING) for the full
license text.

The upstream repository is included as a Git submodule at
`upstream/MacTahoe-icon-theme`. It tracks `main`; the build fetches the latest
upstream revision. Upstream files are never modified.

## Dependencies

- Git
- Python 3.10+ (standard library only)
- `hyprcursor-util`

On Arch Linux, `hyprcursor-util` is provided by the `hyprcursor` package. On
distributions that package it separately, install `hyprcursor-util`.

## Clone and build

```bash
git clone --recurse-submodules https://github.com/Vantesh/mactahoe-hyprcursor.git
cd mactahoe-hyprcursor
```

If you already cloned without submodules:

```bash
git submodule update --init --recursive
```

Build and update upstream:

```bash
python3 scripts/build.py
```

This fetches the latest upstream `main`, regenerates both themes in `dist/`,
validates them, compiles them with `hyprcursor-util`, and creates:

```text
dist/MacTahoe-hyprcursor/
dist/MacTahoe-dark-hyprcursor/
dist/MacTahoe-hyprcursor.tar.gz
dist/MacTahoe-dark-hyprcursor.tar.gz
dist/build-info.json
```

To build the upstream revision that is already checked out, without fetching:

```bash
python3 scripts/build.py --no-fetch
```

Builds are deterministic: archive file order, timestamps, permissions, and
paths are normalized, and repeated builds from the same source produce
identical archives.

## Automatic updates and releases

The `update` GitHub Actions workflow runs daily at 04:17 UTC and can also be
started manually from the repository's **Actions → Update and release → Run
workflow** page. A manual run performs the same update check and build; if the
current upstream revision has already been published, it exits successfully
without creating a duplicate release.

The workflow:

1. Fetches upstream `main`.
2. Derives the release tag `v<project-version>-<upstream-short-sha>`.
3. Skips the build if that tag already exists.
4. Builds and validates both themes.
5. Compiles both themes with `hyprcursor-util`.
6. Rebuilds once and verifies the archives are byte-identical.
7. Publishes both archives only if all previous steps succeeded.

The upstream commit is recorded in the release tag/notes and in the
`build-info.json` file inside each theme and each release archive.

Download release archives from the repository's **Releases** page.

## Install

The themes are installed per-user; no `sudo` is required.

```bash
mkdir -p ~/.local/share/icons
tar -xzf MacTahoe-hyprcursor.tar.gz -C ~/.local/share/icons
```

For the dark variant, extract `MacTahoe-dark-hyprcursor.tar.gz` instead, or
install both.

## Hyprland configuration

Add to `~/.config/hypr/hyprland.conf`:

```ini
env = HYPRCURSOR_THEME,MacTahoe-hyprcursor
env = HYPRCURSOR_SIZE,24
```

Use `MacTahoe-dark-hyprcursor` for the dark variant. Restart Hyprland after
changing cursor environment variables.

## XCursor fallback

The release archives contain compiled Hyprcursor themes only. Applications
that use XCursor instead of Hyprcursor can use the XCursor themes shipped in
the upstream submodule:

```bash
mkdir -p ~/.local/share/icons
cp -r upstream/MacTahoe-icon-theme/cursors/dist      ~/.local/share/icons/MacTahoe-cursors
cp -r upstream/MacTahoe-icon-theme/cursors/dist-dark ~/.local/share/icons/MacTahoe-dark-cursors
```

Then configure the matching fallback:

```ini
env = XCURSOR_THEME,MacTahoe-cursors
env = XCURSOR_SIZE,24
```

Use `MacTahoe-dark-cursors` for the dark variant.
