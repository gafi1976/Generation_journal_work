#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Генератор журнала Lotus Notes.

Для каждого рабочего дня (пн-пт) с 01.07.2024 по 19.06.2026
случайно берётся одна из 234 существующих записей оригинального файла,
её содержимое (Events, Note, record_type, category и т.д.) переносится
в новую запись, а дата заменяется на нужную.

Служебные поля $Revisions, $FILE, $Links убираются.
Кодировка: Windows-1251, разделители строк: CRLF.
Разделитель между записями: form-feed (\x0c).
"""

import re
import random
from datetime import datetime, timedelta

INPUT_FILE  = 'jurnal_my.txt'
OUTPUT_FILE = 'jurnal_import.txt'
ENCODING    = 'cp1251'
CRLF        = '\r\n'

DATE_START  = datetime(2024, 7, 1)
DATE_END    = datetime(2026, 6, 19)

# Фиксируем seed для воспроизводимости результата
random.seed(42)

# ─────────────────────────────────────────────────────────────
# 1. Загружаем оригинальный файл и парсим каждую запись
# ─────────────────────────────────────────────────────────────
with open(INPUT_FILE, 'rb') as f:
    content = f.read().decode(ENCODING)

raw_parts = content.split('\x0c')

# Поля, которые надо удалять из копируемой записи
SKIP_FIELDS = {'$Revisions', '$FILE', '$Links'}

# Список фиксированных полей в строгом порядке (без 'date' — его вставляем сами)
FIXED_FIELDS = [
    't', 'c', 'record_type', 'record_type_r', 'Executor',
    'mail_node_name', 'mail_node_name_r', 'node_number', 'node_param',
    'abonent_name', 'res_data', 'model_hardware', 'inventar',
    'adv_param_name2', 'inventar_1', 'port', 'time_no_work',
    'adv_param_name_3', 'category', 'node_name', 'node_location',
    'adv_param_label', 'adv_param_name', 'adv_param_label_2',
    'adv_param_name2_r', 'adv_param_label_3', 'adv_param_name_3_r',
    '$UpdatedBy',
]

def parse_record(raw: str):
    """
    Парсит raw-блок одной записи в словарь.
    Возвращает None, если дата не найдена.
    """
    lines = raw.strip('\r\n').split('\r\n')
    rec = {}
    i = 0
    # Сначала читаем однострочные поля
    while i < len(lines):
        line = lines[i]
        # Пропускаем пустые строки до Events
        if not line.strip():
            i += 1
            continue
        # Служебные поля — пропускаем
        skip = False
        for sf in SKIP_FIELDS:
            if line.startswith(sf + ':'):
                skip = True
                break
        if skip:
            i += 1
            continue
        # Поле Events — собираем всё что идёт до Note или конца
        if line.startswith('Events:'):
            events_lines = [line]
            i += 1
            while i < len(lines):
                next_line = lines[i]
                if next_line.startswith('Note:'):
                    break
                events_lines.append(next_line)
                i += 1
            rec['Events'] = CRLF.join(events_lines)
            continue
        # Поле Note — собираем до конца блока
        if line.startswith('Note:'):
            note_lines = [line]
            i += 1
            while i < len(lines):
                note_lines.append(lines[i])
                i += 1
            rec['Note'] = CRLF.join(note_lines).rstrip('\r\n')
            continue
        # Обычное однострочное поле  "key:  value"
        m = re.match(r'^(\$?[A-Za-z_][A-Za-z_0-9]*):\s*(.*)', line)
        if m:
            key, val = m.group(1), m.group(2)
            rec[key] = val
        i += 1

    if 'date' not in rec:
        return None
    return rec


def build_record(rec: dict, new_date: datetime) -> str:
    """
    Собирает текст одной записи из словаря, подставляя новую дату.
    """
    date_str = new_date.strftime('%d.%m.%Y')
    out_lines = []

    for field in FIXED_FIELDS:
        if field == 't':
            out_lines.append('t:  ' + rec.get('t', ''))
        elif field == 'c':
            out_lines.append('c:  ' + rec.get('c', ''))
        else:
            val = rec.get(field, '')
            out_lines.append(f'{field}:  {val}')

    # Вставляем дату после 'c' (в оригинале date идёт третьей строкой)
    # Перестраиваем: t, c, date, ...rest
    # out_lines сейчас: [t, c, record_type, ...]
    # Вставляем date на позицию 2
    out_lines.insert(2, f'date:  {date_str}')

    # Пустая строка перед Events
    out_lines.append('')

    # Events
    if 'Events' in rec:
        out_lines.append(rec['Events'])
    else:
        out_lines.append('Events:  ')

    # Note (если есть)
    if 'Note' in rec:
        out_lines.append(rec['Note'])

    # Пустая строка в конце
    out_lines.append('')

    return CRLF.join(out_lines)


# ─────────────────────────────────────────────────────────────
# 2. Строим пул записей — только те, у которых есть дата
# ─────────────────────────────────────────────────────────────
pool = []
skipped = 0
for raw in raw_parts:
    rec = parse_record(raw)
    if rec is not None:
        pool.append(rec)
    else:
        skipped += 1

print(f'Загружено записей в пул: {len(pool)}  (пропущено без даты: {skipped})')

# ─────────────────────────────────────────────────────────────
# 3. Генерируем список рабочих дней и собираем блоки
# ─────────────────────────────────────────────────────────────
blocks = []
current = DATE_START
total = 0
while current <= DATE_END:
    if current.weekday() < 5:          # пн=0 … пт=4
        source_rec = random.choice(pool)
        block_text = build_record(source_rec, current)
        blocks.append(block_text)
        total += 1
    current += timedelta(days=1)

print(f'Рабочих дней сгенерировано: {total}')

# ─────────────────────────────────────────────────────────────
# 4. Склеиваем файл: блоки разделяются  \x0c\r\n
#    В конце файла — \x0c\r\n\r\n  (как в оригинале)
# ─────────────────────────────────────────────────────────────
separator = '\x0c' + CRLF

pieces = []
for i, block in enumerate(blocks):
    if i == 0:
        pieces.append(block)
    else:
        pieces.append(CRLF + block)   # перед каждым блоком (кроме первого) — CRLF

final_text = separator.join(pieces) + CRLF + '\x0c' + CRLF + CRLF

# ─────────────────────────────────────────────────────────────
# 5. Запись
# ─────────────────────────────────────────────────────────────
with open(OUTPUT_FILE, 'wb') as f:
    f.write(final_text.encode(ENCODING))

print(f'Файл сохранён: {OUTPUT_FILE}  ({len(final_text.encode(ENCODING))} байт)')
