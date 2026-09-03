#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ホーム画面用アイコン(180x180 PNG、サムライブルー基調)を生成する。"""

import os
from PIL import Image, ImageDraw, ImageFont

SIZE = 180
OUTPUT = os.path.join(os.path.dirname(__file__), "icon.png")

BG_COLOR = (11, 26, 51)       # サムライブルー(紺)
ACCENT_COLOR = (0, 160, 233)  # 水色アクセント
TEXT_COLOR = (255, 255, 255)


def generate():
    img = Image.new("RGB", (SIZE, SIZE), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # 角丸っぽい縁取り(アクセントカラーの枠)
    draw.rectangle([4, 4, SIZE - 5, SIZE - 5], outline=ACCENT_COLOR, width=6)

    try:
        font_large = ImageFont.truetype("meiryob.ttc", 64)
        font_small = ImageFont.truetype("arialbd.ttf", 28)
    except OSError:
        font_large = ImageFont.load_default()
        font_small = ImageFont.load_default()

    text1 = "代表"
    bbox1 = draw.textbbox((0, 0), text1, font=font_large)
    w1, h1 = bbox1[2] - bbox1[0], bbox1[3] - bbox1[1]
    draw.text(((SIZE - w1) / 2 - bbox1[0], SIZE * 0.28 - h1 / 2 - bbox1[1]),
              text1, font=font_large, fill=TEXT_COLOR)

    text2 = "TV"
    bbox2 = draw.textbbox((0, 0), text2, font=font_small)
    w2, h2 = bbox2[2] - bbox2[0], bbox2[3] - bbox2[1]
    draw.text(((SIZE - w2) / 2 - bbox2[0], SIZE * 0.68 - h2 / 2 - bbox2[1]),
              text2, font=font_small, fill=ACCENT_COLOR)

    img.save(OUTPUT, "PNG")
    print(f"アイコンを保存しました: {OUTPUT}")


if __name__ == "__main__":
    generate()
