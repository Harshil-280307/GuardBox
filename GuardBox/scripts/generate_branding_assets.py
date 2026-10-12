"""
Script to generate high-resolution, pixel-perfect branding assets for
TRINETRA Security System (Frontend, Android Mobile App, and Backend Email/Push).
"""

import os
import sys
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

SOURCE_PATHS = [
    r"D:\Downloads\Trinetra.png",
    r"e:\GuardBox\trinetra_source.png"
]

def find_source():
    for p in SOURCE_PATHS:
        if os.path.exists(p):
            return p
    raise FileNotFoundError("Could not find Trinetra.png in candidate paths")

def generate_assets():
    src_path = find_source()
    print(f"[1/6] Loading source image from: {src_path}")
    src_bgr = cv2.imread(src_path)
    h, w, _ = src_bgr.shape

    # 1. Background color detection & alpha generation
    bg_color = np.array([src_bgr[0,0,0], src_bgr[0,0,1], src_bgr[0,0,2]], dtype=np.float32)
    diff = src_bgr.astype(np.float32) - bg_color
    dist = np.sqrt(np.sum(diff**2, axis=2))
    
    # Smooth anti-aliased alpha thresholding
    alpha = np.clip((dist - 10.0) / 30.0 * 255.0, 0, 255).astype(np.uint8)
    src_bgra = cv2.merge([src_bgr[:,:,0], src_bgr[:,:,1], src_bgr[:,:,2], alpha])

    # 2. Extract Full Logo (Emblem + "TRINETRA" text)
    fg_coords = np.argwhere(alpha > 20)
    y0, x0 = fg_coords.min(axis=0)
    y1, x1 = fg_coords.max(axis=0)
    pad = 30
    y0_pad = max(0, y0 - pad)
    y1_pad = min(h, y1 + pad)
    x0_pad = max(0, x0 - pad)
    x1_pad = min(w, x1 + pad)

    full_logo_crop = src_bgra[y0_pad:y1_pad, x0_pad:x1_pad]
    full_logo_rgba = Image.fromarray(cv2.cvtColor(full_logo_crop, cv2.COLOR_BGRA2RGBA))
    
    # Also create non-transparent original crop
    full_logo_rgb_crop = src_bgr[y0_pad:y1_pad, x0_pad:x1_pad]
    full_logo_rgb = Image.fromarray(cv2.cvtColor(full_logo_rgb_crop, cv2.COLOR_BGR2RGB))

    # 3. Extract Emblem Only (Symbol/Eye at top)
    # The letters begin around y=670
    emblem_mask = np.zeros_like(alpha)
    emblem_mask[0:665, :] = alpha[0:665, :]
    emblem_coords = np.argwhere(emblem_mask > 20)
    ey0, ex0 = emblem_coords.min(axis=0)
    ey1, ex1 = emblem_coords.max(axis=0)
    epad = 20
    ey0_pad = max(0, ey0 - epad)
    ey1_pad = min(h, ey1 + epad)
    ex0_pad = max(0, ex0 - epad)
    ex1_pad = min(w, ex1 + epad)

    emblem_crop = src_bgra[ey0_pad:ey1_pad, ex0_pad:ex1_pad]
    emblem_rgba = Image.fromarray(cv2.cvtColor(emblem_crop, cv2.COLOR_BGRA2RGBA))

    # Square Transparent Emblem (1024x1024)
    ew, eh = emblem_rgba.size
    max_dim = max(ew, eh)
    sq_size = int(max_dim * 1.15)
    emblem_sq = Image.new('RGBA', (sq_size, sq_size), (0, 0, 0, 0))
    emblem_sq.paste(emblem_rgba, ((sq_size - ew) // 2, (sq_size - eh) // 2), emblem_rgba)
    emblem_sq_1024 = emblem_sq.resize((1024, 1024), Image.Resampling.LANCZOS)

    # 4. Create Dark Cyber Shield Badge Emblem (1024x1024)
    # Designed for launcher icon, circular icons, dark mode UI
    dark_badge = Image.new('RGBA', (1024, 1024), (7, 17, 28, 255))
    glow = Image.new('RGBA', (1024, 1024), (0, 0, 0, 0))
    draw_glow = ImageDraw.Draw(glow)
    for r in range(460, 120, -20):
        a = int((460 - r) / 460 * 40)
        draw_glow.ellipse((512-r, 512-r, 512+r, 512+r), fill=(0, 202, 158, a))
    glow = glow.filter(ImageFilter.GaussianBlur(16))
    dark_badge.paste(glow, (0, 0), glow)
    
    scaled_emblem = emblem_sq.resize((820, 820), Image.Resampling.LANCZOS)
    dark_badge.paste(scaled_emblem, (102, 102), scaled_emblem)

    # Round Dark Badge
    round_mask = Image.new('L', (1024, 1024), 0)
    draw_round = ImageDraw.Draw(round_mask)
    draw_round.ellipse((20, 20, 1004, 1004), fill=255)
    round_dark_badge = Image.new('RGBA', (1024, 1024), (0, 0, 0, 0))
    round_dark_badge.paste(dark_badge, (0, 0), round_mask)

    print("[2/6] Writing Frontend (Laptop / Web) Assets...")
    frontend_dirs = [
        r"e:\GuardBox\frontend\public",
        r"e:\GuardBox\frontend\src\assets"
    ]
    for d in frontend_dirs:
        os.makedirs(d, exist_ok=True)
        full_logo_rgb.save(os.path.join(d, "trinetra-logo.png"), "PNG")
        full_logo_rgba.save(os.path.join(d, "trinetra-logo-transparent.png"), "PNG")
        emblem_sq_1024.save(os.path.join(d, "trinetra-emblem.png"), "PNG")
        dark_badge.save(os.path.join(d, "trinetra-emblem-dark.png"), "PNG")
        emblem_sq_1024.resize((512, 512), Image.Resampling.LANCZOS).save(os.path.join(d, "favicon.png"), "PNG")

    # Multi-size ICO for browser favicon
    ico_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    dark_badge.save(r"e:\GuardBox\frontend\public\favicon.ico", format="ICO", sizes=ico_sizes)

    print("[3/6] Writing Android Mobile App Drawable Assets...")
    android_drawable = r"e:\GuardBox\android\app\src\main\res\drawable"
    os.makedirs(android_drawable, exist_ok=True)
    full_logo_rgb.save(os.path.join(android_drawable, "trinetra_logo.png"), "PNG")
    full_logo_rgba.save(os.path.join(android_drawable, "trinetra_logo_transparent.png"), "PNG")
    emblem_sq_1024.save(os.path.join(android_drawable, "trinetra_emblem.png"), "PNG")
    dark_badge.save(os.path.join(android_drawable, "trinetra_emblem_dark.png"), "PNG")

    print("[4/6] Writing Android Launcher Mipmap Assets...")
    mipmap_configs = [
        ("mipmap-mdpi", 48),
        ("mipmap-hdpi", 72),
        ("mipmap-xhdpi", 96),
        ("mipmap-xxhdpi", 144),
        ("mipmap-xxxhdpi", 192),
    ]

    for folder_name, size in mipmap_configs:
        folder_path = os.path.join(r"e:\GuardBox\android\app\src\main\res", folder_name)
        os.makedirs(folder_path, exist_ok=True)
        
        # Square launcher icon
        icon_square = dark_badge.resize((size, size), Image.Resampling.LANCZOS)
        icon_square.save(os.path.join(folder_path, "ic_launcher.webp"), "WEBP")

        # Round launcher icon
        icon_round = round_dark_badge.resize((size, size), Image.Resampling.LANCZOS)
        icon_round.save(os.path.join(folder_path, "ic_launcher_round.webp"), "WEBP")

    print("[5/6] Writing Backend Assets for Email & Push Alerting and Windows Icons...")
    backend_assets = r"e:\GuardBox\backend\app\assets"
    os.makedirs(backend_assets, exist_ok=True)
    full_logo_rgb.save(os.path.join(backend_assets, "trinetra_logo.png"), "PNG")
    full_logo_rgba.save(os.path.join(backend_assets, "trinetra_logo_transparent.png"), "PNG")
    emblem_sq_1024.save(os.path.join(backend_assets, "trinetra_emblem.png"), "PNG")
    dark_badge.save(os.path.join(backend_assets, "trinetra_emblem_dark.png"), "PNG")

    # Windows Application & Installer Multi-Resolution .ico
    win_ico_sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    windows_ico_paths = [
        os.path.join(backend_assets, "trinetra.ico"),
        r"e:\GuardBox\installer\trinetra.ico",
        r"e:\GuardBox\backend\trinetra.ico"
    ]
    for ico_path in windows_ico_paths:
        os.makedirs(os.path.dirname(ico_path), exist_ok=True)
        emblem_sq_1024.save(ico_path, format="ICO", sizes=win_ico_sizes)

    print("[6/6] All branding assets generated successfully!")

if __name__ == "__main__":
    generate_assets()
