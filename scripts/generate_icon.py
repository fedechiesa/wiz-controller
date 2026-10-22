"""Draw our geometric W/lightning mark; no external images or fonts needed."""
from pathlib import Path

from PIL import Image, ImageDraw


def generate(destination):
    destination.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((8, 8, 504, 504), radius=112, fill="#10131E", outline="#323C60", width=8)
    draw.rounded_rectangle((35, 35, 477, 477), radius=94, outline="#9561F9", width=8)
    draw.line([(110, 164), (157, 357), (244, 215), (289, 357), (385, 164)],
              fill="#F0F1FA", width=42, joint="curve")
    draw.polygon([(291, 96), (222, 224), (277, 224), (233, 310), (352, 181), (289, 181)], fill="#30D9E8")
    image.save(destination / "wiz-controller.png")
    image.save(destination / "wiz-controller.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


if __name__ == "__main__":
    generate(Path(__file__).resolve().parent.parent / "assets")
