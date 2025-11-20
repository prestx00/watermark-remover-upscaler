import os
import time
import replicate
from pathlib import Path
from dotenv import load_dotenv
import httpx

# НАСТРОЙКИ
CLEAN_DIR = "output"           # Откуда брать
FINAL_DIR = "final_upscaled"   # Куда класть
MODEL_NAME = "recraft-ai/recraft-crisp-upscale"
API_DELAY = 0.5

def main():
    load_dotenv()
    if not os.getenv("REPLICATE_API_TOKEN"):
        print("❌ Ошибка: нет токена в .env")
        return

    os.makedirs(FINAL_DIR, exist_ok=True)
    
    # Создаем клиент с увеличенным таймаутом (5 минут)
    client = replicate.Client(
        api_token=os.getenv("REPLICATE_API_TOKEN"),
        timeout=httpx.Timeout(300.0, connect=60.0)
    )
    
    # Ищем фото
    images = list(Path(CLEAN_DIR).glob("*.jpg")) + list(Path(CLEAN_DIR).glob("*.png"))
    print(f"🔎 Найдено {len(images)} фото в папке {CLEAN_DIR}")

    for i, img_path in enumerate(images, 1):
        output_filename = Path(FINAL_DIR) / f"upscaled_{img_path.name}"
        
        if output_filename.exists():
            print(f"[{i}/{len(images)}] ⏭️  Уже готово: {img_path.name}")
            continue

        print(f"[{i}/{len(images)}] 🚀 Отправка: {img_path.name}...")
        
        # Retry логика (до 2 попыток)
        max_retries = 2
        success = False
        
        for attempt in range(max_retries):
            try:
                with open(img_path, "rb") as file:
                    output = client.run(MODEL_NAME, input={"image": file})
                
                with open(output_filename, "wb") as f_out:
                    f_out.write(output.read())
                    
                print(f"      ✅ Сохранено!")
                success = True
                break
                
            except Exception as e:
                error_msg = str(e)
                
                # Список ошибок для retry
                retryable_errors = [
                    "timed out", "timeout",
                    "peer closed connection",
                    "connection reset",
                    "incomplete message"
                ]
                
                is_retryable = any(err in error_msg.lower() for err in retryable_errors)
                
                if is_retryable and attempt < max_retries - 1:
                    print(f"      🔄 Ошибка соединения (попытка {attempt + 1}/{max_retries}), повтор через 5 сек...")
                    time.sleep(5)
                    continue
                
                elif "429" in error_msg or "throttled" in error_msg.lower():
                    print(f"      🛑 Rate limit. Пауза 10 секунд...")
                    time.sleep(10)
                    if attempt < max_retries - 1:
                        continue
                
                print(f"      ❌ Ошибка: {e}")
                break
        
        if success:
            time.sleep(API_DELAY)

if __name__ == "__main__":
    main()

