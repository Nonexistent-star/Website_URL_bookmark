# -*- coding: utf-8 -*-
"""生成 WebJump 应用图标：蓝色渐变圆角底 + 白色地球经纬线 + 金色闪电（寓意全球网站、极速跳转）"""
from PIL import Image, ImageDraw

S = 256
TOP, BOT = (31, 111, 214), (9, 38, 92)

# 垂直渐变背景
grad = Image.linear_gradient("L").resize((S, S))
layer_a = Image.new("RGB", (S, S), TOP)
layer_b = Image.new("RGB", (S, S), BOT)
bg = Image.composite(layer_a, layer_b, grad)

mask = Image.new("L", (S, S), 0)
ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=56, fill=255)
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
img.paste(bg, (0, 0), mask)

d = ImageDraw.Draw(img)

# 地球：白色圆 + 经纬线
cx, cy, r = 128, 132, 82
d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(255, 255, 255, 235), width=9)
d.ellipse([cx - int(r * 0.45), cy - r, cx + int(r * 0.45), cy + r],
          outline=(255, 255, 255, 170), width=6)
d.ellipse([cx - r, cy - int(r * 0.38), cx + r, cy + int(r * 0.38)],
          outline=(255, 255, 255, 170), width=6)
d.line([cx - r, cy, cx + r, cy], fill=(255, 255, 255, 170), width=6)

# 闪电：深色描边 + 金色填充
bolt = [(150, 34), (84, 142), (122, 142), (102, 222), (174, 110), (134, 110)]
d.polygon(bolt, fill=(10, 30, 70, 255))
d.polygon([(x, y) for x, y in bolt], outline=(10, 30, 70, 255), width=10)
inner = [(150, 40), (90, 140), (126, 140), (107, 214), (168, 112), (132, 112)]
d.polygon(inner, fill=(255, 210, 63, 255))

img.save("webjump_icon.png")
img.save("app.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                           (64, 64), (128, 128), (256, 256)])
print("icon ok")
