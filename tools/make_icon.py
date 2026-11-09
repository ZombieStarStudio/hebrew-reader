r"""icon.ico: the studio's green star on a dark rounded square, from C:Tairogoectorpng (small sizes use the small star)."""
from pathlib import Path

from PIL import Image, ImageDraw

LOGO = Path(r"C:\Tair\Logo\vector\png")
OUT = Path(__file__).resolve().parent.parent / "icon.ico"


def tile(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle((0, 0, size - 1, size - 1), radius=max(2, size // 5), fill=(18, 20, 26, 255))
    small = size <= 48
    src = LOGO / (f"star-small-{size}.png" if small and (LOGO / f"star-small-{size}.png").exists() else "star-512.png")
    star = Image.open(src).convert("RGBA")
    star = star.crop(star.getbbox())
    inner = int(size * (0.86 if small else 0.78))
    star = star.resize((inner, inner), Image.LANCZOS)
    img.alpha_composite(star, ((size - inner) // 2, (size - inner) // 2))
    return img


sizes = [16, 24, 32, 48, 64, 128, 256]
images = [tile(s) for s in sizes]
images[-1].save(OUT, sizes=[(s, s) for s in sizes], append_images=images[:-1])
images[-1].save(OUT.with_suffix(".png"))
print("icon", OUT)
