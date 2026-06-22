"""
Запуск Flask-приложения через Waitress (production WSGI-сервер для Windows).
Использование:  python run.py
"""

from waitress import serve
from app import app

HOST = '0.0.0.0'   # слушаем все сетевые интерфейсы
PORT = 5000        # порт (можно изменить)

if __name__ == '__main__':
    print('=' * 54)
    print('  Генератор журнала Lotus Notes')
    print(f'  Сервер запущен: http://0.0.0.0:{PORT}')
    print(f'  В браузере коллег: http://<IP-сервера>:{PORT}')
    print('  Остановить: Ctrl+C')
    print('=' * 54)
    serve(app, host=HOST, port=PORT, threads=8)
