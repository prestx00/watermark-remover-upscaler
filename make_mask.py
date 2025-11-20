from PIL import Image, ImageDraw

# --- УЛУЧШЕННЫЕ НАСТРОЙКИ ПОД ВАШЕ ФОТО ---
IMG_W, IMG_H = 832, 1248 

# Размер квадрата удаления (100x100 хватит с запасом)
MARK_W, MARK_H = 100, 100 

# Уменьшаем отступы, так как ромбик почти в углу
MARGIN_RIGHT = 0    # 0 пикселей от правого края
MARGIN_BOTTOM = 0   # 0 пикселей от нижнего края
# -----------------

# Создаем черное полотно (фон)
mask = Image.new('L', (IMG_W, IMG_H), 0) # 0 = черный
draw = ImageDraw.Draw(mask)

# Считаем координаты прямоугольника
x1 = IMG_W - MARK_W - MARGIN_RIGHT
y1 = IMG_H - MARK_H - MARGIN_BOTTOM
x2 = IMG_W - MARGIN_RIGHT
y2 = IMG_H - MARGIN_BOTTOM

# Рисуем белый прямоугольник (зона удаления)
draw.rectangle([x1, y1, x2, y2], fill=255) # 255 = белый

# Сохраняем
mask.save('mask.png')
print(f"✅ Маска mask.png создана! Размер: {IMG_W}x{IMG_H}")
print(f"Белая зона (удаление): X={x1}..{x2}, Y={y1}..{y2}")
