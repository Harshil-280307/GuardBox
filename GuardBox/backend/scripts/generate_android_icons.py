import os
import cv2
import numpy as np

def create_icons():
    # Load the transparent cropped emblem
    emblem_path = r'E:\GuardBox\frontend\public\trinetra-emblem.png'
    emblem = cv2.imread(emblem_path, cv2.IMREAD_UNCHANGED)
    if emblem is None:
        print("Emblem not found!")
        return

    eh, ew, _ = emblem.shape

    densities = {
        'mipmap-mdpi': 48,
        'mipmap-hdpi': 72,
        'mipmap-xhdpi': 96,
        'mipmap-xxhdpi': 144,
        'mipmap-xxxhdpi': 192
    }

    base_res_dirs = [
        r'E:\GuardBox\android\app\src\main\res',
        r'E:\GuardBox\GuardBoxApp\app\src\main\res'
    ]

    for res_dir in base_res_dirs:
        if not os.path.exists(res_dir):
            continue

        for folder, size in densities.items():
            target_dir = os.path.join(res_dir, folder)
            os.makedirs(target_dir, exist_ok=True)

            # 1. Square Icon with dark background (#07111C to #0D1B2A)
            # Create size x size canvas
            canvas_square = np.zeros((size, size, 4), dtype=np.uint8)
            
            # Draw rounded rect or dark circle background
            # Background gradient / color: #07111C -> (28, 17, 7 in BGR)
            # Fill canvas with dark bg with 10% corner radius or full square
            bg_bgr = [28, 17, 7]  # #07111C in BGR
            for y in range(size):
                # subtle gradient from top to bottom
                factor = 1.0 + (y / float(size)) * 0.4
                b = min(255, int(bg_bgr[0] * factor))
                g = min(255, int(bg_bgr[1] * factor))
                r = min(255, int(bg_bgr[2] * factor))
                canvas_square[y, :, 0] = b
                canvas_square[y, :, 1] = g
                canvas_square[y, :, 2] = r
                canvas_square[y, :, 3] = 255

            # Compute emblem size to fit inside 78% of size
            target_w = int(size * 0.80)
            target_h = int(target_w * (eh / float(ew)))
            if target_h > int(size * 0.80):
                target_h = int(size * 0.80)
                target_w = int(target_h * (ew / float(eh)))

            resized_emblem = cv2.resize(emblem, (target_w, target_h), interpolation=cv2.INTER_AREA)

            # Center overlay
            yo = (size - target_h) // 2
            xo = (size - target_w) // 2

            # Alpha blend emblem over square canvas
            emb_rgb = resized_emblem[:, :, :3]
            emb_a = resized_emblem[:, :, 3] / 255.0

            for c in range(3):
                canvas_square[yo:yo+target_h, xo:xo+target_w, c] = (
                    emb_a * emb_rgb[:, :, c] + (1.0 - emb_a) * canvas_square[yo:yo+target_h, xo:xo+target_w, c]
                ).astype(np.uint8)

            # 2. Round Icon (Circular mask)
            canvas_round = canvas_square.copy()
            mask = np.zeros((size, size), dtype=np.uint8)
            cv2.circle(mask, (size // 2, size // 2), size // 2 - 1, 255, -1, cv2.LINE_AA)
            canvas_round[:, :, 3] = mask

            # Save both .webp and .png formats
            cv2.imwrite(os.path.join(target_dir, 'ic_launcher.webp'), canvas_square)
            cv2.imwrite(os.path.join(target_dir, 'ic_launcher_round.webp'), canvas_round)
            cv2.imwrite(os.path.join(target_dir, 'ic_launcher.png'), canvas_square)
            cv2.imwrite(os.path.join(target_dir, 'ic_launcher_round.png'), canvas_round)

    print("All Android launcher mipmap icons generated successfully!")

if __name__ == '__main__':
    create_icons()
