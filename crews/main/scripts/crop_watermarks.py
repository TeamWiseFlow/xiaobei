#!/usr/bin/env python3
"""
批量裁剪图片底部水印（知乎等平台右下角账号水印）
用法: python3 crop_watermarks.py <图片目录>
示例: python3 crop_watermarks.py ./output_articles/xxx/images
"""
from PIL import Image
import os
import sys

if len(sys.argv) < 2:
    print("用法: python3 crop_watermarks.py <图片目录>")
    sys.exit(1)

img_dir = sys.argv[1]
crop_h = 60  # 裁剪底部高度（px），覆盖知乎典型水印区域

if not os.path.isdir(img_dir):
    print(f"错误: {img_dir} 不是有效目录")
    sys.exit(1)

for fname in sorted(os.listdir(img_dir)):
    if not fname.endswith(('.jpg', '.png', '.jpeg', '.webp')):
        continue
    path = os.path.join(img_dir, fname)
    img = Image.open(path)
    w, h = img.size
    if h > crop_h + 100:
        cropped = img.crop((0, 0, w, h - crop_h))
        if cropped.mode != 'RGB':
            cropped = cropped.convert('RGB')
        cropped.save(path, 'JPEG', quality=92)
        print(f"{fname}: {w}x{h} → {w}x{h - crop_h} (已裁剪底部 {crop_h}px)")
    else:
        print(f"{fname}: {w}x{h} 太小，跳过")

print("完成")
