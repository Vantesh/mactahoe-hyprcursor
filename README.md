# MacTahoe Hyprcursor

MacTahoe cursors for [Hyprcursor](https://github.com/hyprwm/hyprcursor), built
from the original SVG artwork in
[vinceliuice/MacTahoe-icon-theme](https://github.com/vinceliuice/MacTahoe-icon-theme).

It comes in two variants: `MacTahoe-hyprcursor` (light) and
`MacTahoe-dark-hyprcursor` (dark).

## Install

Download the archives for the variants you want from
[Releases](https://github.com/Vantesh/mactahoe-hyprcursor/releases), then:

```bash
mkdir -p ~/.local/share/icons
tar -xzf MacTahoe-hyprcursor.tar.gz -C ~/.local/share/icons
tar -xzf MacTahoe-cursors.tar.gz -C ~/.local/share/icons
```

Use `MacTahoe-dark-hyprcursor.tar.gz` and `MacTahoe-dark-cursors.tar.gz` for the
dark variants.

## Hyprland

Add to `~/.config/hypr/hyprland.lua`:

```lua
hl.env("HYPRCURSOR_THEME", "MacTahoe-hyprcursor")
hl.env("HYPRCURSOR_SIZE", "24")
```

Use `MacTahoe-dark-hyprcursor` for the dark variant, then restart Hyprland.

To switch cursors without restarting:

```bash
hyprctl setcursor MacTahoe-hyprcursor 24
```

## XCursor fallback

Some apps still use XCursor. Download `MacTahoe-cursors.tar.gz` (or
`MacTahoe-dark-cursors.tar.gz`) from Releases and extract it into
`~/.local/share/icons`:

```bash
mkdir -p ~/.local/share/icons
tar -xzf MacTahoe-cursors.tar.gz -C ~/.local/share/icons
```

```lua
hl.env("XCURSOR_THEME", "MacTahoe-cursors")
hl.env("XCURSOR_SIZE", "24")
```

## Build

You need Git, Python 3.10+, and `hyprcursor-util` (the `hyprcursor` package on
Arch).

```bash
git clone --recurse-submodules https://github.com/Vantesh/mactahoe-hyprcursor.git
cd mactahoe-hyprcursor
python3 scripts/build.py
```

The themes are written to `dist/`. The build produces two Hyprcursor archives
and two XCursor fallback archives.

## Releases

Releases are tagged `v<version>-<upstream-commit>`, so you can always see which
upstream revision a build came from. The archives contain the compiled themes
plus the license and attribution files.

## License

The artwork belongs to
[vinceliuice/MacTahoe-icon-theme](https://github.com/vinceliuice/MacTahoe-icon-theme)
and is licensed under GPL-3.0. See [COPYING](COPYING) for the full text.
