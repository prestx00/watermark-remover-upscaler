import os
import subprocess
import time
import replicate
from pathlib import Path
from PIL import Image, ImageDraw
from dotenv import load_dotenv
import httpx

# ==========================================
# ⚙️ НАСТРОЙКИ
# ==========================================

# Папки
INPUT_DIR = "input"            # Исходные фото
CLEAN_DIR = "output"           # Фото без вотермарок
FINAL_DIR = "final_upscaled"   # Финальные 4K фото
MASK_PATH = "mask_auto.png"    # Имя файла маски (генерируется автоматически)

# Настройки маски (под ваши фото 832x1248 с ромбиком в углу)
IMG_W, IMG_H = 832, 1248
MARK_W, MARK_H = 100, 100      # Размер квадрата удаления
MARGIN_RIGHT = 0               # Отступ справа
MARGIN_BOTTOM = 0              # Отступ снизу

# Настройки Wildberries
WB_DIR = "ready_for_wb"        # Куда кладем готовое для WB
TARGET_W = 900                 # Ширина WB
TARGET_H = 1200                # Высота WB
QUALITY = 95                   # Качество JPG

# Настройки Replicate (Recraft Crisp Upscale)
# Модель: recraft-ai/recraft-crisp-upscale
MODEL_VERSION = "recraft-ai/recraft-crisp-upscale"
API_DELAY = 0.5                # Пауза между запросами (сек) для защиты от лимитов

# ==========================================

def setup_environment():
    """Проверка окружения и токенов"""
    load_dotenv()
    
    if not os.getenv("REPLICATE_API_TOKEN"):
        print("❌ ОШИБКА: Токен не найден!")
        print("Создайте файл .env и добавьте туда: REPLICATE_API_TOKEN=r8_ваш_токен")
        exit(1)
        
    # Создаем папки, если их нет
    os.makedirs(INPUT_DIR, exist_ok=True)
    os.makedirs(CLEAN_DIR, exist_ok=True)
    os.makedirs(FINAL_DIR, exist_ok=True)
    os.makedirs(WB_DIR, exist_ok=True)

    # Проверяем наличие фото
    files = list(Path(INPUT_DIR).glob("*"))
    if not files:
        print(f"⚠️  Папка '{INPUT_DIR}' пуста! Положите туда фотографии.")
        exit(1)
    
    print(f"✅ Найдено {len(files)} файлов для обработки.")


def generate_mask():
    """Генерация идеальной маски под правый нижний угол"""
    print("\n🎨 Генерируем маску...")
    
    mask = Image.new('L', (IMG_W, IMG_H), 0)  # Черный фон
    draw = ImageDraw.Draw(mask)

    # Координаты
    x1 = IMG_W - MARK_W - MARGIN_RIGHT
    y1 = IMG_H - MARK_H - MARGIN_BOTTOM
    x2 = IMG_W - MARGIN_RIGHT
    y2 = IMG_H - MARGIN_BOTTOM

    # Рисуем белый квадрат
    draw.rectangle([x1, y1, x2, y2], fill=255)
    
    mask.save(MASK_PATH)
    print(f"✅ Маска сохранена: {MASK_PATH} (Удаление зоны: {MARK_W}x{MARK_H} px в углу)")


def step_1_remove_watermarks():
    """Запуск IOPaint для удаления вотермарок"""
    print("\n🧹 ШАГ 1: Удаляем вотермарки через IOPaint (локально)...")
    
    # Команда запуска
    # Используем mps для Mac M1/M2, если ошибка - поменяйте на cpu
    cmd = [
        "iopaint", "run",
        "--model=lama",
        "--device=mps", 
        f"--image={INPUT_DIR}",
        f"--mask={MASK_PATH}",
        f"--output={CLEAN_DIR}"
    ]
    
    try:
        subprocess.run(cmd, check=True)
        print("✅ Вотермарки успешно удалены.")
    except subprocess.CalledProcessError as e:
        print(f"❌ Ошибка IOPaint: {e}")
        exit(1)
    except FileNotFoundError:
        print("❌ Ошибка: iopaint не установлен! Выполните: pip install iopaint")
        exit(1)


def step_2_upscale():
    """Апскейлинг через Replicate API с retry и увеличенным таймаутом"""
    print("\n🚀 ШАГ 2: Улучшаем качество (Upscale) через Replicate...")
    
    images = list(Path(CLEAN_DIR).glob("*.jpg")) + list(Path(CLEAN_DIR).glob("*.png"))
    total = len(images)
    
    if total == 0:
        print("⚠️  Нет файлов для апскейла.")
        return

    # Создаем клиент с увеличенным таймаутом (5 минут)
    client = replicate.Client(
        api_token=os.getenv("REPLICATE_API_TOKEN"),
        timeout=httpx.Timeout(300.0, connect=60.0)
    )

    for i, img_path in enumerate(images, 1):
        output_filename = Path(FINAL_DIR) / f"upscaled_{img_path.name}"
        
        # Пропускаем, если уже обработано
        if output_filename.exists():
            print(f"[{i}/{total}] ⏭️  Пропуск (файл существует): {img_path.name}")
            continue

        print(f"[{i}/{total}] ⏳ Отправка в Replicate: {img_path.name}...")
        
        # Retry логика (до 2 попыток)
        max_retries = 2
        success = False
        
        for attempt in range(max_retries):
            try:
                with open(img_path, "rb") as file:
                    # Вызов API с кастомным клиентом
                    output = client.run(
                        MODEL_VERSION,
                        input={"image": file}
                    )
                
                # Сохранение результата
                with open(output_filename, "wb") as f_out:
                    f_out.write(output.read())
                    
                print(f"      ✨ Успех! Сохранено в: {FINAL_DIR}/{output_filename.name}")
                success = True
                break  # Выходим из retry loop при успехе
                
            except Exception as e:
                error_msg = str(e)
                
                # Список ошибок, которые стоит повторить
                retryable_errors = [
                    "timed out",
                    "timeout",
                    "peer closed connection",
                    "connection reset",
                    "incomplete message"
                ]
                
                # Проверяем, можно ли повторить
                is_retryable = any(err in error_msg.lower() for err in retryable_errors)
                
                if is_retryable and attempt < max_retries - 1:
                    print(f"      🔄 Обрыв соединения (попытка {attempt + 1}/{max_retries}), повтор через 5 сек...")
                    time.sleep(5)
                    continue
                
                # Если это rate limit
                elif "429" in error_msg or "throttled" in error_msg.lower():
                    print(f"      🛑 Rate limit. Пауза 10 секунд...")
                    time.sleep(10)
                    if attempt < max_retries - 1:
                        continue
                
                # Финальная ошибка (после всех попыток)
                print(f"      ❌ Ошибка API: {e}")
                break  # Прекращаем retry, переходим к следующему файлу
        
        # Небольшая пауза между запросами для защиты от лимитов
        if success and i < total:
            time.sleep(API_DELAY)


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


def step_3_prepare_for_wb():
    """Подготовка финальных фото для Wildberries"""
    print("\n📦 ШАГ 3: Подготовка для Wildberries...")
    
    # Берем фото из папки с апскейлом
    images = list(Path(FINAL_DIR).glob("*.*"))
    total = len(images)

    if total == 0:
        print("⚠️  Нет файлов для подготовки к WB.")
        return

    for i, img_path in enumerate(images, 1):
        try:
            # Пропускаем системные файлы
            if img_path.name.startswith('.'): continue

            print(f"[{i}/{total}] Обработка: {img_path.name}...", end=" ")
            
            with Image.open(img_path) as img:
                # Если есть прозрачность (PNG), заливаем белым
                if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                    background = Image.new("RGB", img.size, (255, 255, 255))
                    background.paste(img, mask=img.split()[3])
                    img = background
                else:
                    img = img.convert("RGB")

                # Ресайз + Кроп
                final_img = resize_and_crop(img, TARGET_W, TARGET_H)
                
                # Сохраняем как JPG
                new_filename = img_path.stem + ".jpg"
                save_path = Path(WB_DIR) / new_filename
                
                final_img.save(save_path, "JPEG", quality=QUALITY, optimize=True)
                
                size_mb = save_path.stat().st_size / (1024 * 1024)
                print(f"✅ OK ({size_mb:.2f} MB)")

        except Exception as e:
            print(f"❌ Ошибка: {e}")


def main():
    print("=== 🚀 ЗАПУСК АВТОМАТИЧЕСКОЙ ОБРАБОТКИ ФОТО ===")
    setup_environment()
    
    # 1. Создаем маску
    generate_mask()
    
    # 2. Чистим вотермарки
    step_1_remove_watermarks()
    
    # 3. Апскейлим
    step_2_upscale()

    # 4. Готовим для WB
    step_3_prepare_for_wb()
    
    print("\n🎉 ГОТОВО! Все фото обработаны.")
    print(f"📂 Результат здесь: {os.path.abspath(WB_DIR)}")

if __name__ == "__main__":
    main()