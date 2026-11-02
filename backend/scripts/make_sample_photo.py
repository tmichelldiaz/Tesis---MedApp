import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT_DIR = Path("C:/Windows/Fonts")
ROWS = [
    ("Examen", "Resultado", "Unidad", "Referencia"),
    ("Hemoglobina", "13.8", "g/dL", "12.0 - 16.0"),
    ("Hematocrito", "41", "%", "36 - 46"),
    ("Leucocitos", "11.2", "x10^3/uL", "4.5 - 11.0"),
    ("Plaquetas", "248", "x10^3/uL", "150 - 450"),
    ("Ácido úrico", "6.9", "mg/dL", "2.4 - 6.0"),
    ("TSH", "2.1", "mUI/L", "0.4 - 4.0"),
]


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_DIR / name), size)


def build(path: Path) -> None:
    random.seed(7)
    w, h = 900, 1100
    paper = Image.new("RGB", (w, h), (247, 246, 240))
    d = ImageDraw.Draw(paper)

    d.text((60, 60), "Centro de Diagnóstico Ejemplo", font=font("arialbd.ttf", 30), fill=(20, 20, 30))
    d.text((60, 105), "Resultado de laboratorio (documento sintético)", font=font("arial.ttf", 20), fill=(50, 50, 60))
    d.text((60, 160), "Paciente: Paciente de Prueba", font=font("arial.ttf", 22), fill=(20, 20, 30))
    d.text((60, 192), "Fecha: 22/07/2026    Solicitado por: Dr. Ejemplo", font=font("arial.ttf", 22), fill=(20, 20, 30))
    d.text((60, 250), "HEMOGRAMA Y PERFIL TIROIDEO", font=font("arialbd.ttf", 26), fill=(20, 20, 30))

    y = 305
    for i, row in enumerate(ROWS):
        f = font("arialbd.ttf", 21) if i == 0 else font("arial.ttf", 21)
        for x, cell in zip((60, 330, 480, 680), row):
            d.text((x, y), cell, font=f, fill=(25, 25, 35))
        y += 46
        d.line((55, y - 8, 850, y - 8), fill=(190, 190, 185), width=1)

    d.text((60, y + 30), "Nota: valor de leucocitos y ácido úrico fuera de rango.", font=font("arial.ttf", 20), fill=(60, 60, 70))
    d.text((60, y + 60), "Interpretación a cargo del médico tratante.", font=font("arial.ttf", 20), fill=(60, 60, 70))
    d.ellipse((560, y + 120, 820, y + 240), outline=(40, 70, 160), width=4)
    d.text((610, y + 165), "LABORATORIO", font=font("arialbd.ttf", 22), fill=(40, 70, 160))

    desk = Image.new("RGB", (1100, 1300), (92, 78, 66))
    tilted = paper.rotate(2.6, expand=True, resample=Image.BICUBIC, fillcolor=(92, 78, 66))
    desk.paste(tilted, (60, 70))

    shade = Image.linear_gradient("L").resize(desk.size).rotate(28)
    shade = shade.point(lambda v: int(v * 0.55))
    dark = Image.new("RGB", desk.size, (0, 0, 0))
    desk = Image.composite(dark, desk, shade)

    desk = desk.filter(ImageFilter.GaussianBlur(1.3))
    px = desk.load()
    for _ in range(int(desk.width * desk.height * 0.06)):
        x, yy = random.randrange(desk.width), random.randrange(desk.height)
        r, g, b = px[x, yy]
        n = random.randint(-28, 28)
        px[x, yy] = (max(0, min(255, r + n)), max(0, min(255, g + n)), max(0, min(255, b + n)))

    path.parent.mkdir(parents=True, exist_ok=True)
    desk.save(path, "JPEG", quality=55)


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("out/foto_laboratorio.jpg")
    build(target)
    print(f"Foto sintética -> {target}")
