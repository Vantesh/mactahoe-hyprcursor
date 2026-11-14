# MacTahoe Hyprcursor

MacTahoe cursors for [Hyprcursor](https://github.com/hyprwm/hyprcursor), built
from the original SVG artwork in
[vinceliuice/MacTahoe-icon-theme](https://github.com/vinceliuice/MacTahoe-icon-theme).

It comes in two variants: `MacTahoe-hyprcursor` (light) and
`MacTahoe-dark-hyprcursor` (dark).

## Install

Download the archive for the variant you want from
[Releases](https://github.com/Vantesh/mactahoe-hyprcursor/releases), then:

```bash
mkdir -p ~/.local/share/icons
tar -xzf MacTahoe-hyprcursor.tar.gz -C ~/.local/share/icons
```

## Hyprland

Add to `~/.config/hypr/hyprland.conf`:

```ini
env = HYPRCURSOR_THEME,MacTahoe-hyprcursor
env = HYPRCURSOR_SIZE,24
```

Use `MacTahoe-dark-hyprcursor` for the dark variant, then restart Hyprland.

## XCursor fallback

Some apps still use XCursor. The upstream submodule ships matching XCursor
themes:

```bash
mkdir -p ~/.local/share/icons/MacTahoe-cursors
mkdir -p ~/.local/share/icons/MacTahoe-dark-cursors
cp -r upstream/MacTahoe-icon-theme/cursors/dist/.      ~/.local/share/icons/MacTahoe-cursors/
cp -r upstream/MacTahoe-icon-theme/cursors/dist-dark/. ~/.local/share/icons/MacTahoe-dark-cursors/
```

```ini
env = XCURSOR_THEME,MacTahoe-cursors
env = XCURSOR_SIZE,24
```

## Build

You need Git, Python 3.10+, and `hyprcursor-util` (the `hyprcursor` package on
Arch).

```bash
git clone --recurse-submodules https://github.com/Vantesh/mactahoe-hyprcursor.git
cd mactahoe-hyprcursor
python3 scripts/build.py
```

The themes are written to `dist/`.

## Releases

Releases are tagged `v<version>-<upstream-commit>`, so you can always see which
upstream revision a build came from. The archives contain the compiled themes
plus the license and attribution files.

## License

The artwork belongs to
[vinceliuice/MacTahoe-icon-theme](https://github.com/vinceliuice/MacTahoe-icon-theme)
and is licensed under GPL-3.0. See [COPYING](COPYING) for the full text.
