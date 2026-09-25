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
FLAG_RED = (188, 0, 45)       # 日の丸の赤


def generate():
    # 背景は白(日の丸の白地)、中央に大きな赤丸。「代表」は小さく、「TV」は大きく。
    img = Image.new("RGB", (SIZE, SIZE), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    sun_r = SIZE * 0.42
    cx, cy = SIZE / 2, SIZE / 2
    draw.ellipse([cx - sun_r, cy - sun_r, cx + sun_r, cy + sun_r], fill=FLAG_RED)

    try:
        font_small = ImageFont.truetype("meiryob.ttc", 54)
        font_large = ImageFont.truetype("arialbd.ttf", 74)
    except OSError:
        font_large = ImageFont.load_default()
        font_small = ImageFont.load_default()

    def center_text(text, font, y_center):
        bbox = draw.textbbox((0, 0), text, font=font)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(((SIZE - w) / 2 - bbox[0], y_center - h / 2 - bbox[1]),
                  text, font=font, fill=TEXT_COLOR)

    center_text("代表", font_small, SIZE * 0.36)
    center_text("TV", font_large, SIZE * 0.66)

    img.save(OUTPUT, "PNG")
    print(f"アイコンを保存しました: {OUTPUT}")


if __name__ == "__main__":
    generate()
