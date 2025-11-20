import os
from PIL import Image
from pathlib import Path

# --- НАСТРОЙКИ WILDBERRIES ---
SOURCE_DIR = "final_upscaled"   # Откуда берем (после Replicate)
WB_DIR = "ready_for_wb"         # Куда кладем готовое
TARGET_W = 900                  # Ширина WB
TARGET_H = 1200                 # Высота WB
QUALITY = 95                    # Качество JPG (для <10Мб хватит с головой)
# -----------------------------

def resize_and_crop(img, target_width, target_height):
    """
    Умный ресайз:
    1. Масштабирует картинку так, чтобы заполнить целевую область.
    2. Обрезает лишнее по центру (Center Crop).
    """
    img_ratio = img.width / img.height
    target_ratio = target_width / target_height

    if img_ratio > target_ratio:
        # Картинка шире, чем нужно (ресайзим по высоте)
        new_height = target_height
        new_width = int(new_height * img_ratio)
    else:
        # Картинка выше, чем нужно (ресайзим по ширине)
        new_width = target_width
        new_height = int(new_width / img_ratio)

    # 1. Ресайз (LANCZOS - лучшее качество для уменьшения)
    img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

    # 2. Кроп по центру
    left = (new_width - target_width) / 2
    top = (new_height - target_height) / 2
    right = (new_width + target_width) / 2
    bottom = (new_height + target_height) / 2

    return img.crop((left, top, right, bottom))

def main():
    print(f"🚀 Начинаем подготовку для Wildberries ({TARGET_W}x{TARGET_H})...")
    os.makedirs(WB_DIR, exist_ok=True)
    
    # Берем все картинки (png, jpg)
    images = list(Path(SOURCE_DIR).glob("*.*"))
    
    for i, img_path in enumerate(images, 1):
        try:
            print(f"[{i}/{len(images)}] Обработка: {img_path.name}...", end=" ")
            
            with Image.open(img_path) as img:
                # Если есть прозрачность (PNG), заливаем белым
                if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                    background = Image.new("RGB", img.size, (255, 255, 255))
                    background.paste(img, mask=img.split()[3]) # 3 канал = альфа
                    img = background
                else:
                    img = img.convert("RGB")

                # Ресайз + Кроп
                final_img = resize_and_crop(img, TARGET_W, TARGET_H)
                
                # Сохраняем как JPG
                # Меняем расширение на .jpg
                new_filename = img_path.stem + ".jpg"
                save_path = Path(WB_DIR) / new_filename
                
                final_img.save(save_path, "JPEG", quality=QUALITY, optimize=True)
                
                # Проверка размера
                size_mb = save_path.stat().st_size / (1024 * 1024)
                print(f"✅ OK ({size_mb:.2f} MB)")

        except Exception as e:
            print(f"❌ Ошибка: {e}")

    print(f"\n🎉 Готово! Файлы лежат в папке: {WB_DIR}")

if __name__ == "__main__":
    main()
