"""Build the YoungLion SVGs, transparent PNGs, and browsable catalog."""

from collections import Counter, defaultdict
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

import cairosvg
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
GRID = 64
PNG_SIZE = 256
COLORS = {"png": "#18332a", "png-light": "#f7fff9"}
NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
BADGES = {
    "add": "M48 43v10m-5-5h10",
    "remove": "M43 48h10",
    "check": "M43 48l3 3 7-7",
    "edit": "M43 50l8-8 3 3-8 8-4 1Z",
    "search": "M49 46a3 3 0 1 1-6 0 3 3 0 0 1 6 0Zm-1 2 5 5",
    "warning": "M48 43v5;d 48 52 1.25",
    "lock": "r 44 47 8 6 1;M46 47v-2a2 2 0 0 1 4 0v2",
    "download": "M48 42v8m-4-4 4 4 4-4m-9 7h10",
    "upload": "M48 50v-8m-4 4 4-4 4 4m-9 7h10",
    "share": "d 44 48 1.75;d 52 43 1.75;d 52 53 1.75;M44 48l8-5m-8 5 8 5",
    "history": "M44 47a4 4 0 1 1 1 4m-2-7v4h4m1-3v3l2 1",
    "favorite": "M48 53l-5-5c-3-3 2-7 5-3 3-4 8 0 5 3Z",
    "translate": "M42 44h7m-4-2v2m-2 2 4 4m1-6c0 3-2 5-5 6m6 3 4-7 3 7m-6-2h5",
    "play": "M46 43l7 5-7 5Z",
    "mute": "M42 46h2l4-3v10l-4-3h-2Zm9 0 4 4m0-4-4 4",
    "filter": "M43 43h10l-4 5v4l-2 1v-5Z",
    "restore": "M43 47a5 5 0 1 1 1 5m-1-10v6h5",
    "unread": "d 48 48 3.75",
    "clock": "c 48 48 5;M48 45v3l2 1",
    "close": "M44 44l8 8m0-8-8 8",
    "pause": "M46 43v10m4-10v10",
    "sync": "M44 47a4 4 0 0 1 7-3l2 2m0-4v4h-4m3 3a4 4 0 0 1-7 3l-2-2m0 4v-4h4",
    "off": "M48 42v5m-3-3a5 5 0 1 0 6 0",
    "charge": "M49 42l-5 7h4l-1 5 5-7h-4Z",
}


def elements(drawing):
    shapes = []
    primitives = {
        "c": ("circle", ("cx", "cy", "r")),
        "d": ("circle", ("cx", "cy", "r")),
        "e": ("ellipse", ("cx", "cy", "rx", "ry")),
        "r": ("rect", ("x", "y", "width", "height", "rx")),
    }
    for shape in drawing.split(";"):
        if shape.startswith("M"):
            tag, attributes = "path", {"d": shape}
        else:
            kind, *values = shape.split()
            tag, keys = primitives[kind]
            attributes = dict(zip(keys, values, strict=True))
            if kind == "d":
                attributes.update(fill="currentColor", stroke="none")
        shapes.append(ET.tostring(ET.Element(tag, attributes), encoding="unicode"))
    return "".join(shapes)


def lines(path):
    return (line.strip() for line in path.read_text().splitlines() if line and not line.startswith("#"))


def read_designs():
    icons = {}
    legacy_names = {}
    legacy = json.loads((ROOT / "designs/legacy.json").read_text())
    for category, designs in legacy.items():
        for name, body in designs.items():
            legacy_names[name] = category
            if body:
                icons[name] = (category, "refined", body)
    for line in lines(ROOT / "designs/icons.txt"):
        category, name, drawing = line.split("|")
        if name in icons:
            raise ValueError(f"Duplicate name: {name}")
        origin = "redrawn" if name in legacy_names else "new"
        icons[name] = (category, origin, elements(drawing))
    if not legacy_names.keys() <= icons.keys():
        raise ValueError("Missing legacy icon")

    for line in lines(ROOT / "designs/variants.txt"):
        base, states = line.split("|")
        category, _, body = icons[base]
        for state in states.split():
            name = f"{base}-{state}"
            if name in icons:
                raise ValueError(f"Duplicate name: {name}")
            drawing = (
                f'<g transform="translate(1 1) scale(.68)" stroke-width="4.15">{body}</g>'
                f'<circle cx="48" cy="48" r="10.5" stroke-width="2.7"/>'
                f'<g stroke-width="2.7">{elements(BADGES[state])}</g>'
            )
            icons[name] = (category, "state", drawing)
    return icons, legacy_names


def vector(body, color=None):
    color_attribute = f' color="{color}"' if color else ""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{GRID}" height="{GRID}" '
        f'viewBox="0 0 {GRID} {GRID}" fill="none"{color_attribute} stroke="currentColor" '
        f'stroke-width="3" stroke-linecap="round" stroke-linejoin="round">\n  {body}\n</svg>\n'
    ).encode()


def render(body, color, size):
    return cairosvg.svg2png(bytestring=vector(body, color), output_width=size, output_height=size)


def image_from_png(png):
    with Image.open(BytesIO(png)) as image:
        return image.convert("RGBA")


def put(path, contents):
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(contents)


def write_json(path, contents):
    put(path, (json.dumps(contents, indent=2, ensure_ascii=False) + "\n").encode())


def contact_sheet(previews, target, heading, overview=False):
    cols = 8
    cell_width = 154
    cell_height = 85
    rows = (len(previews) + cols - 1) // cols
    width = cols * cell_width + 24
    height = rows * cell_height + 70
    image = Image.new("RGB", (width, height), "#edf1eb")
    draw = ImageDraw.Draw(image)
    title = ImageFont.load_default(size=26)
    label_fonts = {size: ImageFont.load_default(size=size) for size in (13, 11, 9)}
    draw.text((17, 17), heading, fill="#18332a", font=title)
    for index, (name, preview) in enumerate(previews):
        x, y = 12 + index % cols * cell_width, 58 + index // cols * cell_height
        draw.rounded_rectangle((x + 3, y, x + cell_width - 4, y + 78), radius=9, fill="#ffffff")
        icon = image_from_png(preview)
        image.paste(icon, (x + (cell_width - 44) // 2, y + 6), icon)
        name = name.replace("-", " ") if overview else name
        label = next((font for font in label_fonts.values() if font.getlength(name) <= cell_width - 16), label_fonts[9])
        draw.text((x + cell_width / 2, y + 64), name, fill="#18332a", anchor="mm", font=label)
    image.save(ROOT / target, optimize=True)


def build():
    designs, legacy_names = read_designs()
    if len(designs) <= 500:
        raise ValueError(f"Need more than 500 icons, found {len(designs)}")

    manifest = []
    categories = defaultdict(list)
    signatures = {}
    for name, (category, origin, body) in sorted(designs.items(), key=lambda item: (item[1][0], item[0])):
        if not NAME.fullmatch(name) or not NAME.fullmatch(category):
            raise ValueError(f"Invalid icon path: {category}/{name}")
        stem = f"{category}/{name}"
        svg_path = f"assets/svg/{stem}.svg"
        put(svg_path, vector(body))
        entry = {"id": name, "category": category, "origin": origin, "svg": svg_path}
        if name in legacy_names:
            entry["legacyName"] = name.replace("-", "_")
        for directory, color in COLORS.items():
            path = f"assets/{directory}/{stem}.png"
            png = render(body, color, PNG_SIZE)
            image = image_from_png(png)
            alpha = image.getchannel("A")
            box = alpha.getbbox()
            if box is None or min(box[0], box[1], PNG_SIZE - box[2], PNG_SIZE - box[3]) < 3:
                raise ValueError(f"Empty or clipped icon: {name}, {box}")
            if directory == "png":
                signature = sha256(alpha.tobytes()).digest()
                if signature in signatures:
                    raise ValueError(f"Same drawing: {name} and {signatures[signature]}")
                signatures[signature] = name
            put(path, png)
            entry[directory] = path
        preview = render(body, COLORS["png"], 44)
        categories[category].append((entry, preview))
        manifest.append(entry)

    output_paths = {entry[key] for entry in manifest for key in ("svg", *COLORS)}
    existing_paths = {path.relative_to(ROOT).as_posix() for path in (ROOT / "assets").rglob("*") if path.is_file()}
    if existing_paths != output_paths:
        raise ValueError(f"Unexpected generated files: {sorted(existing_paths - output_paths)}")
    write_json("manifest.json", {
        "license": "MIT", "viewBox": [0, 0, GRID, GRID], "pngSize": PNG_SIZE,
        "iconCount": len(manifest), "categories": {name: len(items) for name, items in categories.items()},
        "icons": manifest,
    })
    migration = {icon["legacyName"]: icon["id"] for icon in manifest if "legacyName" in icon}
    write_json("migration.json", migration)

    (ROOT / "previews").mkdir(exist_ok=True)
    catalog = ["# YoungLionAssets catalog", "", f"{len(manifest)} icons across {len(categories)} categories.", "",
               "SVG uses `currentColor`. PNGs have transparent backgrounds.", ""]
    catalog.extend(f"- [{name.replace('-', ' ').title()} ({len(items)})](#{name})" for name, items in categories.items())
    overview = []
    for category, items in categories.items():
        heading = category.replace("-", " ").title()
        preview_path = f"previews/{category}.png"
        pairs = [(entry["id"], preview) for entry, preview in items]
        contact_sheet(pairs, preview_path, heading)
        bases = [(entry["id"], preview) for entry, preview in items if entry["origin"] != "state"]
        overview.extend(bases[:2])
        catalog.extend(["", f"## {heading}", "", f"![{heading} icon previews]({preview_path})", "",
                        "| Icon | SVG | PNG | Light PNG |", "| --- | --- | --- | --- |"])
        catalog.extend(
            f"| `{entry['id']}` | [SVG]({entry['svg']}) | [PNG]({entry['png']}) | [PNG]({entry['png-light']}) |"
            for entry, _ in items
        )
    put("CATALOG.md", ("\n".join(catalog) + "\n").encode())
    contact_sheet(overview, "previews/overview.png", "YoungLionAssets", overview=True)
    print(json.dumps({"icons": len(manifest), "categories": len(categories),
                      "origins": dict(Counter(icon["origin"] for icon in manifest)),
                      "pngFiles": len(manifest) * len(COLORS)}, indent=2))


if __name__ == "__main__":
    build()
