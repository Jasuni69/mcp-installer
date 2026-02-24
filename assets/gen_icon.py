"""Generate MCP Installer icon — gear shape with Fabric orange/gold accent."""
import math
from PIL import Image, ImageDraw

SIZE = 256
CENTER = SIZE // 2
BG_COLOR = (30, 30, 46)        # Dark background (matches installer theme)
GEAR_COLOR = (205, 214, 244)   # Light silver
ACCENT_COLOR = (243, 139, 49)  # Fabric orange
BOLT_COLOR = (250, 179, 35)    # Gold accent


def draw_gear(draw, cx, cy, outer_r, inner_r, teeth, tooth_depth):
    """Draw a gear shape."""
    points = []
    for i in range(teeth * 2):
        angle = math.pi * 2 * i / (teeth * 2) - math.pi / 2
        if i % 2 == 0:
            r = outer_r
        else:
            r = outer_r - tooth_depth
        x = cx + r * math.cos(angle)
        y = cy + r * math.sin(angle)
        points.append((x, y))
    draw.polygon(points, fill=GEAR_COLOR)
    # Inner circle (hole)
    draw.ellipse(
        [cx - inner_r, cy - inner_r, cx + inner_r, cy + inner_r],
        fill=BG_COLOR,
    )


def draw_lightning(draw, cx, cy, scale):
    """Draw a small lightning bolt (MCP/power symbol)."""
    points = [
        (cx - 4 * scale, cy - 18 * scale),
        (cx + 6 * scale, cy - 3 * scale),
        (cx - 1 * scale, cy - 3 * scale),
        (cx + 4 * scale, cy + 18 * scale),
        (cx - 6 * scale, cy + 3 * scale),
        (cx + 1 * scale, cy + 3 * scale),
    ]
    draw.polygon(points, fill=BOLT_COLOR)


def main():
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Background circle
    pad = 12
    draw.ellipse([pad, pad, SIZE - pad, SIZE - pad], fill=BG_COLOR)

    # Outer accent ring
    ring_w = 6
    draw.ellipse(
        [pad, pad, SIZE - pad, SIZE - pad],
        outline=ACCENT_COLOR,
        width=ring_w,
    )

    # Main gear
    draw_gear(draw, CENTER, CENTER, outer_r=90, inner_r=32, teeth=10, tooth_depth=18)

    # Lightning bolt in center
    draw_lightning(draw, CENTER, CENTER, scale=1.4)

    # Save as .ico with multiple sizes
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    icons = []
    for s in sizes:
        resized = img.resize(s, Image.LANCZOS)
        icons.append(resized)

    icons[0].save(
        "assets/icon.ico",
        format="ICO",
        sizes=[s for s in sizes],
        append_images=icons[1:],
    )

    # Also save a PNG for tkinter window icon
    img.save("assets/icon.png")
    # 32x32 PNG for taskbar
    img.resize((32, 32), Image.LANCZOS).save("assets/icon_32.png")

    print(f"Generated assets/icon.ico + assets/icon.png + assets/icon_32.png")


if __name__ == "__main__":
    main()
