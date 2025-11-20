import os
import time
import replicate
from pathlib import Path
from PIL import Image
from dotenv import load_dotenv
import httpx

# === НАСТРОЙКИ ===
INPUT_DIR = "input"              # Откуда брать (ваши чистые фото)
UPSCALED_DIR = "final_upscaled"  # Куда класть после апскейла
WB_DIR = "ready_for_wb"          # Итоговая папка для WB

# Параметры для WB
TARGET_W, TARGET_H = 900, 1200
QUALITY = 95

# Параметры Replicate
MODEL_VERSION = "recraft-ai/recraft-crisp-upscale"
API_DELAY = 0.5

def resize_and_crop(img, target_width, target_height):
    """Умный ресайз и кроп по центру"""
    img_ratio = img.width / img.height
    target_ratio = target_width / target_height

    if img_ratio > target_ratio:
        new_height = target_height
        new_width = int(new_height * img_ratio)
    else:
        new_width = target_width
        new_height = int(new_width / img_ratio)

    img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

    left = (new_width - target_width) / 2
    top = (new_height - target_height) / 2
    right = (new_width + target_width) / 2
    bottom = (new_height + target_height) / 2

    return img.crop((left, top, right, bottom))

def step_1_upscale():
    print(f"\n🚀 ШАГ 1: Апскейл фото из '{INPUT_DIR}'...")
    
    images = list(Path(INPUT_DIR).glob("*.jpg")) + list(Path(INPUT_DIR).glob("*.png"))
    total = len(images)
    
    if total == 0:
        print(f"⚠️  В папке {INPUT_DIR} нет фото!")
        return

    client = replicate.Client(
        api_token=os.getenv("REPLICATE_API_TOKEN"),
        timeout=httpx.Timeout(300.0, connect=60.0)
    )

    for i, img_path in enumerate(images, 1):
        output_filename = Path(UPSCALED_DIR) / f"upscaled_{img_path.name}"
        
        if output_filename.exists():
            print(f"[{i}/{total}] ⏭️  Пропуск (уже есть): {img_path.name}")
            continue

        print(f"[{i}/{total}] ⏳ Отправка в Replicate: {img_path.name}...")
        
        max_retries = 2
        success = False
        
        for attempt in range(max_retries):
            try:
                with open(img_path, "rb") as file:
                    output = client.run(
                        MODEL_VERSION,
                        input={"image": file}
                    )
                
                with open(output_filename, "wb") as f_out:
                    f_out.write(output.read())
                    
                print(f"      ✨ Успех! Сохранено в: {UPSCALED_DIR}/{output_filename.name}")
                success = True
                break
                
            except Exception as e:
                error_msg = str(e)
                retryable_errors = ["timed out", "timeout", "peer closed", "connection reset"]
                is_retryable = any(err in error_msg.lower() for err in retryable_errors)
                
                if is_retryable and attempt < max_retries - 1:
                    print(f"      🔄 Сбой сети, повтор через 5 сек...")
                    time.sleep(5)
                    continue
                elif "429" in error_msg:
                    print(f"      🛑 Лимит запросов. Ждем 10 сек...")
                    time.sleep(10)
                    continue
                
                print(f"      ❌ Ошибка: {e}")
                break
        
        if success:
            time.sleep(API_DELAY)

def step_2_prepare_for_wb():
    print(f"\n📦 ШАГ 2: Подготовка для Wildberries ({TARGET_W}x{TARGET_H})...")
    
    images = list(Path(UPSCALED_DIR).glob("*"))
    total = len(images)
    
    if total == 0:
        print("⚠️  Нет файлов для обработки.")
        return

    for i, img_path in enumerate(images, 1):
        if img_path.name.startswith('.'): continue
        
        try:
            with Image.open(img_path) as img:
                # Если есть прозрачность -> белый фон
                if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                    background = Image.new("RGB", img.size, (255, 255, 255))
                    background.paste(img, mask=img.split()[3])
                    img = background
                else:
                    img = img.convert("RGB")

                # Ресайз и кроп
                final_img = resize_and_crop(img, TARGET_W, TARGET_H)

                # Сохранение
                save_path = Path(WB_DIR) / f"{img_path.stem}.jpg"
                final_img.save(save_path, "JPEG", quality=QUALITY, optimize=True)
                
                print(f"[{i}/{total}] ✅ Готово: {save_path.name}")
                
        except Exception as e:
            print(f"❌ Ошибка с файлом {img_path.name}: {e}")

def main():
    load_dotenv()
    if not os.getenv("REPLICATE_API_TOKEN"):
        print("❌ Ошибка: Нет токена в .env")
        return

    # Создаем папки
    for d in [UPSCALED_DIR, WB_DIR]:
        os.makedirs(d, exist_ok=True)

    # Запускаем процесс
    step_1_upscale()
    step_2_prepare_for_wb()
    
    print("\n🎉 ВСЕ ГОТОВО! Проверьте папку 'ready_for_wb'")

if __name__ == "__main__":
    main()
