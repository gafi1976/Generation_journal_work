#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт генерации журнала Lotus Notes.
Создаёт файл экспорта с записями для каждого рабочего дня
с 01.07.2024 по 19.06.2026 (включительно).
Если на дату уже есть запись — берётся из оригинального файла.
Если нет — генерируется пустой шаблон.
"""

import re
from datetime import datetime, timedelta

INPUT_FILE  = 'jurnal_my.txt'
OUTPUT_FILE = 'jurnal_import.txt'
ENCODING    = 'cp1251'
CRLF        = '\r\n'

# Диапазон генерации
DATE_START = datetime(2024, 7, 1)
DATE_END   = datetime(2026, 6, 19)

# ─────────────────────────────────────────────
# 1. Загрузка и парсинг оригинального файла
# ─────────────────────────────────────────────
with open(INPUT_FILE, 'rb') as f:
    content = f.read().decode(ENCODING)

parts = content.split('\x0c')

existing = {}          # datetime -> строковый блок записи (без \x0c и без \r\n в начале/конце)
existing_raw = {}      # datetime -> RAW блок (для точного воспроизведения)

for part in parts:
    m = re.search(r'date:\s+(\d{2}\.\d{2}\.\d{4})', part)
    if m:
        datestr = m.group(1)
        try:
            d = datetime.strptime(datestr, '%d.%m.%Y')
            existing_raw[d] = part.strip('\r\n')
        except ValueError:
            pass

print(f'Загружено записей из оригинала: {len(existing_raw)}')

# ─────────────────────────────────────────────
# 2. Шаблон для пустого рабочего дня
# ─────────────────────────────────────────────
def make_empty_record(dt: datetime) -> str:
    datestr = dt.strftime('%d.%m.%Y')
    lines = [
        't:  ',
        'c:  ',
        f'date:  {datestr}',
        'record_type:  ',
        'record_type_r:  ',
        'Executor:  Холбеков.Г.Т.',
        'mail_node_name:  ',
        'mail_node_name_r:  ',
        'node_number:  ',
        'node_param:  ',
        'abonent_name:  ',
        'res_data:  ',
        'model_hardware:  ',
        'inventar:  ',
        'adv_param_name2:  ',
        'inventar_1:  ',
        'port:  ',
        'time_no_work:  ',
        'adv_param_name_3:  ',
        'category:  нет',
        'node_name:  ',
        'node_location:  ',
        'adv_param_label:  ',
        'adv_param_name:  ',
        'adv_param_label_2:  ',
        'adv_param_name2_r:  ',
        'adv_param_label_3:  ',
        'adv_param_name_3_r:  ',
        '$UpdatedBy:  CN=tech10/O=Guli',
        '',
        'Events:  ',
        'Note:  ',
        '',
    ]
    return CRLF.join(lines)

# ─────────────────────────────────────────────
# 3. Генерация списка рабочих дней и сборка блоков
# ─────────────────────────────────────────────
blocks = []
total_days    = 0
existing_used = 0
generated     = 0

current = DATE_START
while current <= DATE_END:
    # Рабочий день = пн-пт (weekday 0..4)
    if current.weekday() < 5:
        total_days += 1
        if current in existing_raw:
            block_text = existing_raw[current]
            existing_used += 1
        else:
            block_text = make_empty_record(current)
            generated += 1
        blocks.append(block_text)
    current += timedelta(days=1)

print(f'Всего рабочих дней в диапазоне: {total_days}')
print(f'  Взято из оригинала:  {existing_used}')
print(f'  Сгенерировано пустых: {generated}')

# ─────────────────────────────────────────────
# 4. Сборка финального файла
#    Формат: блок \x0c блок \x0c ... последний блок \x0c \r\n\r\n
# ─────────────────────────────────────────────
separator = '\x0c' + CRLF   # form-feed + CRLF перед следующим блоком

output_parts = []
for i, block in enumerate(blocks):
    if i == 0:
        output_parts.append(block)
    else:
        # Каждый следующий блок начинается после \x0c\r\n
        output_parts.append(CRLF + block)

final_text = ('\x0c' + CRLF).join(output_parts)
# В конце — form-feed + пустая строка (как в оригинале)
final_text += CRLF + '\x0c' + CRLF + CRLF

# ─────────────────────────────────────────────
# 5. Запись файла в Windows-1251 + CRLF
# ─────────────────────────────────────────────
with open(OUTPUT_FILE, 'wb') as f:
    f.write(final_text.encode(ENCODING))

print(f'\nФайл сохранён: {OUTPUT_FILE}')
print(f'Размер: {len(final_text.encode(ENCODING))} байт')
