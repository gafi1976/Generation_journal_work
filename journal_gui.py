#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Генератор журнала Lotus Notes — веб-интерфейс.
Запуск:  python3 journal_gui.py
Затем открыть в браузере:  http://localhost:8765
"""

import json
import os
import re
import random
import urllib.parse
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer

ENCODING = 'cp1251'
CRLF     = '\r\n'
PORT     = 8765

# ─── Праздники Узбекистана (фиксированные + приблизительные переходящие) ─────
UZ_HOLIDAYS = {
    # Новый год
    date(2024,1,1), date(2025,1,1), date(2026,1,1), date(2027,1,1),
    # День защитников Родины
    date(2024,1,14), date(2025,1,14), date(2026,1,14), date(2027,1,14),
    # 8 Марта
    date(2024,3,8), date(2025,3,8), date(2026,3,8), date(2027,3,8),
    # Навруз
    date(2024,3,21), date(2025,3,21), date(2026,3,21), date(2027,3,21),
    # Рамазан-хайит (приблизительно)
    date(2024,4,10), date(2025,3,20), date(2026,3,20),
    # День Победы
    date(2024,5,9), date(2025,5,9), date(2026,5,9), date(2027,5,9),
    # Курбан-хайит (приблизительно)
    date(2024,6,17), date(2025,6,7), date(2026,5,27),
    # День независимости
    date(2024,9,1), date(2025,9,1), date(2026,9,1), date(2027,9,1),
    # День учителей
    date(2024,10,1), date(2025,10,1), date(2026,10,1), date(2027,10,1),
    # День Конституции
    date(2024,12,8), date(2025,12,8), date(2026,12,8), date(2027,12,8),
}


# ─── Парсинг шаблонного файла ─────────────────────────────────────────────────
def parse_template(file_bytes: bytes) -> list:
    """
    Читает файл экспорта Lotus Notes (cp1251).
    Возвращает список словарей с полями каждой записи.
    """
    try:
        text = file_bytes.decode('cp1251')
    except Exception:
        text = file_bytes.decode('utf-8', errors='replace')

    records = []
    for part in text.split('\x0c'):
        part = part.strip('\r\n')
        if not part:
            continue
        rec = {}
        lines = part.split('\r\n')
        i = 0
        while i < len(lines):
            line = lines[i]
            # Пропускаем служебные поля и пустые строки
            if not line.strip() or line.startswith('$FILE') \
               or line.startswith('$Revisions') or line.startswith('$Links'):
                i += 1
                continue
            # Events — многострочное
            if line.startswith('Events:'):
                ev_lines = [line]
                i += 1
                while i < len(lines) and not lines[i].startswith('Note:'):
                    ev_lines.append(lines[i])
                    i += 1
                rec['Events'] = '\r\n'.join(ev_lines)
                continue
            # Note — до конца блока
            if line.startswith('Note:'):
                nt_lines = [line]
                i += 1
                while i < len(lines):
                    nt_lines.append(lines[i])
                    i += 1
                rec['Note'] = '\r\n'.join(nt_lines).rstrip('\r\n')
                continue
            # Обычное поле  key:  value
            m = re.match(r'^(\$?[A-Za-z_][A-Za-z_0-9]*):\s*(.*)', line)
            if m:
                rec[m.group(1)] = m.group(2)
            i += 1

        if 'date' in rec and rec.get('Events', '').strip():
            records.append(rec)

    return records


# ─── Построение одной записи ──────────────────────────────────────────────────
def build_record(d: date, rec: dict, executor: str, updated_by: str) -> str:
    """
    Собирает текстовый блок одной записи для импорта в Lotus Notes.
    Берёт поля из rec, подставляет новую дату и исполнителя.
    """
    record_type = rec.get('record_type', rec.get('c', ''))
    category    = rec.get('category', 'нет')
    events      = rec.get('Events', 'Events:  ')
    note        = rec.get('Note', '')

    lines = [
        't:  ',
        f'c:  {record_type}',
        f'date:  {d.strftime("%d.%m.%Y")}',
        f'record_type:  {record_type}',
        f'record_type_r:  {record_type}',
        f'Executor:  {executor}',
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
        f'category:  {category}',
        'node_name:  ',
        'node_location:  ',
        'adv_param_label:  ',
        'adv_param_name:  ',
        'adv_param_label_2:  ',
        'adv_param_name2_r:  ',
        'adv_param_label_3:  ',
        'adv_param_name_3_r:  ',
        f'$UpdatedBy:  {updated_by}',
        '',
        events,
    ]
    if note:
        lines.append(note)
    lines.append('')
    return CRLF.join(lines)


# ─── Генерация итогового файла ────────────────────────────────────────────────
def generate_journal(date_from: date, date_to: date,
                     executor1: str, executor2: str,
                     template_records: list,
                     special_days: dict,
                     updated_by: str = 'CN=tech10/O=Guli') -> bytes:
    """
    special_days: {date: {'events': str, 'note': str, 'executor': str}}
    Если поле пустое — день комбинируется из шаблона.
    """
    random.seed(42)
    blocks = []
    prev_type = None
    cur = date_from

    while cur <= date_to:
        is_holiday = cur in UZ_HOLIDAYS
        is_weekend = cur.weekday() >= 5
        if not is_holiday and not is_weekend:
            sd = special_days.get(cur)

            # Если есть заполненный спецдень — берём его
            if sd and sd.get('events', '').strip():
                rec = {
                    'record_type': sd.get('record_type', 'Текущие работы'),
                    'category':    sd.get('category', 'нет'),
                    'Events':      'Events:  ' + sd['events'],
                    'Note':        ('Note:  ' + sd['note']) if sd.get('note', '').strip() else '',
                }
                exc = sd.get('executor') or executor1
                blocks.append(build_record(cur, rec, exc, updated_by))
            else:
                # Комбинируем из шаблона
                if template_records:
                    candidates = [r for r in template_records if r.get('record_type') != prev_type]
                    if not candidates:
                        candidates = template_records
                    chosen = random.choice(candidates)
                    prev_type = chosen.get('record_type', '')
                    # Чередуем исполнителей
                    exc = executor1 if len(blocks) % 2 == 0 else (executor2 or executor1)
                    blocks.append(build_record(cur, chosen, exc, updated_by))

        cur += timedelta(days=1)

    if not blocks:
        return b''

    SEP = CRLF + '\x0c' + CRLF
    final = SEP.join(blocks) + CRLF + '\x0c' + CRLF
    return final.encode(ENCODING)


# ─── HTML страница ────────────────────────────────────────────────────────────
HTML_PAGE = r"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Генератор журнала Lotus Notes</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:'Segoe UI',Arial,sans-serif;background:#f0f4f8;color:#2d3748;min-height:100vh}
  .header{background:linear-gradient(135deg,#1a365d,#2b6cb0);color:#fff;padding:22px 32px;
          box-shadow:0 2px 8px rgba(0,0,0,.25)}
  .header h1{font-size:1.5rem;font-weight:600;letter-spacing:.3px}
  .header p{font-size:.85rem;opacity:.8;margin-top:4px}
  .container{max-width:900px;margin:28px auto;padding:0 16px}
  .card{background:#fff;border-radius:10px;padding:24px 28px;margin-bottom:20px;
        box-shadow:0 1px 6px rgba(0,0,0,.1)}
  .card h2{font-size:1rem;font-weight:600;color:#2b6cb0;margin-bottom:16px;
           padding-bottom:8px;border-bottom:2px solid #ebf8ff}
  .row{display:flex;gap:16px;flex-wrap:wrap}
  .field{flex:1;min-width:200px;display:flex;flex-direction:column;gap:5px}
  label{font-size:.82rem;font-weight:500;color:#4a5568}
  input[type=text],input[type=date],select,textarea{
    border:1px solid #cbd5e0;border-radius:6px;padding:8px 10px;
    font-size:.88rem;width:100%;outline:none;transition:border .2s}
  input:focus,select:focus,textarea:focus{border-color:#3182ce;
    box-shadow:0 0 0 3px rgba(49,130,206,.15)}
  textarea{resize:vertical;min-height:72px;font-family:inherit}
  .hint{font-size:.75rem;color:#718096;margin-top:2px}

  /* Upload zone */
  .upload-zone{border:2px dashed #bee3f8;border-radius:8px;padding:20px;
               text-align:center;cursor:pointer;transition:all .2s;background:#f7fbff}
  .upload-zone:hover,.upload-zone.drag{border-color:#3182ce;background:#ebf8ff}
  .upload-zone input{display:none}
  .upload-icon{font-size:2rem;margin-bottom:6px}
  .upload-text{font-size:.85rem;color:#4a5568}
  .upload-name{font-size:.8rem;color:#3182ce;margin-top:6px;font-weight:500}

  /* Special days table */
  #special-table{width:100%;border-collapse:collapse;font-size:.82rem}
  #special-table th{background:#ebf8ff;color:#2b6cb0;padding:8px 10px;
                     text-align:left;font-weight:600;border-bottom:2px solid #bee3f8}
  #special-table td{padding:6px 8px;border-bottom:1px solid #f0f4f8;vertical-align:top}
  #special-table tr:hover td{background:#f7fbff}
  #special-table input,#special-table select,#special-table textarea{
    border:1px solid #e2e8f0;padding:5px 7px;font-size:.8rem;border-radius:4px;width:100%}
  .btn-add{background:#ebf8ff;color:#2b6cb0;border:1px solid #bee3f8;
           border-radius:6px;padding:7px 16px;cursor:pointer;font-size:.82rem;
           font-weight:500;transition:all .2s}
  .btn-add:hover{background:#bee3f8}
  .btn-del{background:none;border:none;color:#e53e3e;cursor:pointer;
           font-size:1rem;padding:2px 6px;border-radius:4px}
  .btn-del:hover{background:#fff5f5}

  /* Generate button */
  .btn-gen{display:block;width:100%;padding:14px;background:linear-gradient(135deg,#2b6cb0,#1a365d);
           color:#fff;border:none;border-radius:8px;font-size:1rem;font-weight:600;
           cursor:pointer;transition:all .2s;letter-spacing:.3px}
  .btn-gen:hover{transform:translateY(-1px);box-shadow:0 4px 14px rgba(43,108,176,.4)}
  .btn-gen:active{transform:translateY(0)}
  .btn-gen:disabled{background:#a0aec0;cursor:not-allowed;transform:none;box-shadow:none}

  /* Status */
  #status{padding:12px 16px;border-radius:8px;font-size:.88rem;display:none;margin-top:12px}
  .status-ok{background:#f0fff4;color:#276749;border:1px solid #c6f6d5}
  .status-err{background:#fff5f5;color:#c53030;border:1px solid #fed7d7}
  .status-info{background:#ebf8ff;color:#2b6cb0;border:1px solid #bee3f8}

  /* Holidays reference */
  details{margin-top:8px}
  summary{cursor:pointer;font-size:.8rem;color:#718096;user-select:none}
  .holidays-grid{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
  .holiday-tag{background:#fff5f5;color:#c53030;border:1px solid #fed7d7;
               border-radius:4px;padding:3px 8px;font-size:.75rem}

  @media(max-width:600px){.row{flex-direction:column}}
</style>
</head>
<body>
<div class="header">
  <h1>📋 Генератор журнала Lotus Notes</h1>
  <p>Генерация рабочих дней с учётом праздников Узбекистана</p>
</div>
<div class="container">

<!-- Период и исполнители -->
<div class="card">
  <h2>⚙️ Параметры генерации</h2>
  <div class="row">
    <div class="field">
      <label>Период с</label>
      <input type="date" id="date_from" value="2024-07-01">
    </div>
    <div class="field">
      <label>Период по</label>
      <input type="date" id="date_to" value="2026-06-19">
    </div>
  </div>
  <div class="row" style="margin-top:14px">
    <div class="field">
      <label>Исполнитель 1</label>
      <input type="text" id="exec1" value="Холбеков.Г.Т." placeholder="Фамилия.И.О.">
    </div>
    <div class="field">
      <label>Исполнитель 2 (необязательно)</label>
      <input type="text" id="exec2" value="Рахматов В.А." placeholder="Фамилия.И.О.">
    </div>
  </div>
  <div class="row" style="margin-top:14px">
    <div class="field">
      <label>$UpdatedBy</label>
      <input type="text" id="updated_by" value="CN=tech10/O=Guli">
    </div>
    <div class="field">
      <label>Имя выходного файла</label>
      <input type="text" id="out_filename" value="jurnal_import.txt">
    </div>
  </div>
  <details style="margin-top:14px">
    <summary>📅 Праздники Узбекистана (исключаются автоматически)</summary>
    <div class="holidays-grid">
      <span class="holiday-tag">1 янв — Янги йил</span>
      <span class="holiday-tag">14 янв — Ватан ҳимоячилари куни</span>
      <span class="holiday-tag">8 март — Хотин-қизлар куни</span>
      <span class="holiday-tag">21 март — Наврўз</span>
      <span class="holiday-tag">Рамазон ҳайити</span>
      <span class="holiday-tag">9 май — Хотира ва қадрлаш куни</span>
      <span class="holiday-tag">Қурбон ҳайити</span>
      <span class="holiday-tag">1 сент — Мустақиллик куни</span>
      <span class="holiday-tag">1 окт — Ўқитувчилар куни</span>
      <span class="holiday-tag">8 дек — Конституция куни</span>
    </div>
  </details>
</div>

<!-- Шаблон -->
<div class="card">
  <h2>📂 Файл шаблона</h2>
  <div class="upload-zone" id="upload-zone" onclick="document.getElementById('file-input').click()"
       ondragover="event.preventDefault();this.classList.add('drag')"
       ondragleave="this.classList.remove('drag')"
       ondrop="handleDrop(event)">
    <input type="file" id="file-input" accept=".txt" onchange="handleFile(this)">
    <div class="upload-icon">📄</div>
    <div class="upload-text">Нажмите или перетащите файл <b>jurnal_my.txt</b></div>
    <div class="upload-name" id="upload-name">Файл не выбран</div>
  </div>
  <p class="hint" style="margin-top:8px">
    Файл экспорта Lotus Notes в кодировке Windows-1251.
    Записи будут случайно комбинироваться для рабочих дней без особого содержания.
  </p>
</div>

<!-- Особые дни -->
<div class="card">
  <h2>✏️ Особые дни (вводятся вручную)</h2>
  <p class="hint" style="margin-bottom:12px">
    Заполните поле «Событие» — этот день не будет комбинироваться из шаблона.
    Если поле пустое — день берётся из шаблона автоматически.
  </p>
  <table id="special-table">
    <thead>
      <tr>
        <th style="width:130px">Дата</th>
        <th style="width:160px">Тип записи</th>
        <th style="width:180px">Исполнитель</th>
        <th>Событие (Events)</th>
        <th style="width:160px">Примечание (Note)</th>
        <th style="width:36px"></th>
      </tr>
    </thead>
    <tbody id="special-body"></tbody>
  </table>
  <button class="btn-add" onclick="addRow()" style="margin-top:10px">+ Добавить особый день</button>
</div>

<!-- Генерация -->
<div class="card">
  <h2>🚀 Генерация</h2>
  <button class="btn-gen" id="btn-gen" onclick="generate()">Создать файл журнала</button>
  <div id="status"></div>
</div>

</div><!-- /container -->

<script>
let templateFile = null;
const RECORD_TYPES = [
  'Настройка','Профилактика','Учеба','Работа с организациями',
  'Текущие работы','Отчет','Поездка','Профилактика'
];

function handleFile(input){
  if(input.files[0]){
    templateFile = input.files[0];
    document.getElementById('upload-name').textContent = '✅ ' + templateFile.name;
    document.getElementById('upload-zone').classList.add('drag');
    setTimeout(()=>document.getElementById('upload-zone').classList.remove('drag'),400);
  }
}
function handleDrop(e){
  e.preventDefault();
  document.getElementById('upload-zone').classList.remove('drag');
  const f = e.dataTransfer.files[0];
  if(f){ document.getElementById('file-input').files = e.dataTransfer.files; handleFile(document.getElementById('file-input')); }
}

function addRow(dateVal='', rtVal='Настройка', execVal='', evVal='', ntVal=''){
  const tbody = document.getElementById('special-body');
  const tr = document.createElement('tr');
  const opts = RECORD_TYPES.map(t=>`<option value="${t}"${t===rtVal?' selected':''}>${t}</option>`).join('');
  tr.innerHTML = `
    <td><input type="date" value="${dateVal}"></td>
    <td><select>${opts}</select></td>
    <td><input type="text" value="${execVal}" placeholder="Исполнитель"></td>
    <td><textarea rows="2" placeholder="Описание работ...">${evVal}</textarea></td>
    <td><textarea rows="2" placeholder="Примечание...">${ntVal}</textarea></td>
    <td><button class="btn-del" onclick="this.closest('tr').remove()" title="Удалить">✕</button></td>`;
  tbody.appendChild(tr);
}

function showStatus(msg, type){
  const el = document.getElementById('status');
  el.textContent = msg;
  el.className = 'status-' + type;
  el.style.display = 'block';
}

async function generate(){
  const dateFrom = document.getElementById('date_from').value;
  const dateTo   = document.getElementById('date_to').value;
  const exec1    = document.getElementById('exec1').value.trim();
  const exec2    = document.getElementById('exec2').value.trim();
  const updBy    = document.getElementById('updated_by').value.trim();
  const outName  = document.getElementById('out_filename').value.trim() || 'jurnal_import.txt';

  if(!dateFrom || !dateTo){ showStatus('⚠ Укажите период.','err'); return; }
  if(!exec1){ showStatus('⚠ Укажите хотя бы одного исполнителя.','err'); return; }

  // Собираем особые дни
  const specRows = document.getElementById('special-body').querySelectorAll('tr');
  const specialDays = [];
  specRows.forEach(row => {
    const cells = row.querySelectorAll('input,select,textarea');
    const d   = cells[0].value;
    const rt  = cells[1].value;
    const exc = cells[2].value.trim();
    const ev  = cells[3].value.trim();
    const nt  = cells[4].value.trim();
    if(d) specialDays.push({date:d, record_type:rt, executor:exc, events:ev, note:nt});
  });

  const btn = document.getElementById('btn-gen');
  btn.disabled = true;
  showStatus('⏳ Генерация...', 'info');

  const formData = new FormData();
  formData.append('date_from',   dateFrom);
  formData.append('date_to',     dateTo);
  formData.append('exec1',       exec1);
  formData.append('exec2',       exec2);
  formData.append('updated_by',  updBy);
  formData.append('special_days', JSON.stringify(specialDays));
  if(templateFile) formData.append('template', templateFile);

  try {
    const resp = await fetch('/generate', {method:'POST', body: formData});
    if(!resp.ok){
      const err = await resp.text();
      showStatus('❌ Ошибка: ' + err, 'err');
      btn.disabled = false;
      return;
    }
    const blob = await resp.blob();
    const info = resp.headers.get('X-Info') || '';
    const recM = info.match(/records=(\d+)/);
    const tmM  = info.match(/templates=(\d+)/);
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href     = url;
    a.download = outName;
    a.click();
    URL.revokeObjectURL(url);
    const msg = '✅ Готово! Записей: ' + (recM ? recM[1] : '?') + ', шаблонов загружено: ' + (tmM ? tmM[1] : '?') + '.  Файл скачан: ' + outName;
    showStatus(msg, 'ok');
  } catch(e){
    showStatus('❌ ' + e.message, 'err');
  }
  btn.disabled = false;
}
</script>
</body>
</html>
"""


# ─── HTTP-обработчик ─────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        pass  # заглушаем стандартный лог

    def do_GET(self):
        if self.path == '/' or self.path == '/index.html':
            body = HTML_PAGE.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path != '/generate':
            self.send_error(404)
            return

        content_type = self.headers.get('Content-Type', '')
        length       = int(self.headers.get('Content-Length', 0))
        raw_body     = self.rfile.read(length)

        try:
            result_bytes, info = self._handle_generate(content_type, raw_body)
        except Exception as e:
            msg = str(e).encode('utf-8')
            self.send_response(500)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Content-Length', str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)
            return

        self.send_response(200)
        self.send_header('Content-Type', 'application/octet-stream')
        self.send_header('Content-Disposition', 'attachment; filename="jurnal_import.txt"')
        self.send_header('Content-Length', str(len(result_bytes)))
        self.send_header('X-Info', info)
        self.send_header('Access-Control-Expose-Headers', 'X-Info')
        self.end_headers()
        self.wfile.write(result_bytes)

    # ── Разбор multipart/form-data и вызов генератора ─────────────────────
    def _handle_generate(self, content_type: str, raw_body: bytes):
        fields, file_bytes = parse_multipart(content_type, raw_body)

        date_from = _parse_date(fields.get('date_from', ''))
        date_to   = _parse_date(fields.get('date_to', ''))
        if not date_from or not date_to:
            raise ValueError('Некорректный период')
        if date_from > date_to:
            raise ValueError('Дата начала больше даты конца')

        exec1      = fields.get('exec1', '').strip()
        exec2      = fields.get('exec2', '').strip()
        updated_by = fields.get('updated_by', 'CN=tech10/O=Guli').strip()
        spec_json  = fields.get('special_days', '[]')

        special_list = json.loads(spec_json)
        special_days = {}
        for item in special_list:
            d = _parse_date(item.get('date', ''))
            if d:
                special_days[d] = {
                    'record_type': item.get('record_type', 'Текущие работы'),
                    'events':      item.get('events', ''),
                    'note':        item.get('note', ''),
                    'executor':    item.get('executor', '').strip(),
                }

        template_records = []
        if file_bytes:
            template_records = parse_template(file_bytes)

        result = generate_journal(
            date_from, date_to,
            exec1, exec2,
            template_records,
            special_days,
            updated_by,
        )

        if not result:
            raise ValueError('Нет рабочих дней в выбранном периоде')

        # Подсчитываем статистику (только ASCII — HTTP-заголовок не принимает кириллицу)
        blocks_count = result.count(b'\x0c')
        info = f'records={blocks_count} templates={len(template_records)}'
        return result, info


# ─── Утилиты ──────────────────────────────────────────────────────────────────
def _parse_date(s: str):
    s = s.strip()
    try:
        y, m, d = s.split('-')
        return date(int(y), int(m), int(d))
    except Exception:
        return None


def parse_multipart(content_type: str, body: bytes):
    """
    Простой парсер multipart/form-data без внешних зависимостей.
    Возвращает (fields_dict, file_bytes_or_None).
    """
    # Граница
    boundary = None
    for part in content_type.split(';'):
        part = part.strip()
        if part.startswith('boundary='):
            boundary = part[9:].strip('"').encode()
            break
    if not boundary:
        raise ValueError('Нет boundary в Content-Type')

    fields    = {}
    file_data = None
    delimiter = b'--' + boundary

    parts = body.split(delimiter)
    for chunk in parts:
        if chunk in (b'', b'--\r\n', b'--', b'\r\n'):
            continue
        # Разделяем заголовки и тело
        if b'\r\n\r\n' not in chunk:
            continue
        headers_raw, body_part = chunk.split(b'\r\n\r\n', 1)
        # Убираем концевой \r\n
        if body_part.endswith(b'\r\n'):
            body_part = body_part[:-2]

        headers_str = headers_raw.decode('utf-8', errors='replace')
        # Content-Disposition
        cd_match = re.search(r'Content-Disposition:[^\r\n]*name="([^"]+)"', headers_str, re.I)
        if not cd_match:
            continue
        field_name = cd_match.group(1)
        is_file    = 'filename=' in headers_str

        if is_file:
            file_data = body_part
        else:
            fields[field_name] = body_part.decode('utf-8', errors='replace')

    return fields, file_data


# ─── Точка входа ──────────────────────────────────────────────────────────────
if __name__ == '__main__':
    import webbrowser
    import threading

    server = HTTPServer(('localhost', PORT), Handler)
    url    = f'http://localhost:{PORT}'

    print('=' * 52)
    print('  Генератор журнала Lotus Notes')
    print(f'  Открыть в браузере: {url}')
    print('  Остановить: Ctrl+C')
    print('=' * 52)

    # Открываем браузер с небольшой задержкой
    def open_browser():
        import time; time.sleep(0.8)
        try: webbrowser.open(url)
        except Exception: pass

    threading.Thread(target=open_browser, daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nСервер остановлен.')
        server.server_close()
