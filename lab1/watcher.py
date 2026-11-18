import os
import sys
import time
import hashlib
import logging
from pathlib import Path

import requests
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

WATCH_DIR  = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          'data', 'uploads')
SERVER_URL      = 'http://127.0.0.1:8000'
SYNC_ENDPOINT   = f'{SERVER_URL}/api/documents/sync'
DELETE_ENDPOINT = f'{SERVER_URL}/api/documents/delete'
HASHES_ENDPOINT = f'{SERVER_URL}/api/documents/hashes'
DEBOUNCE = 3.0
EXTENSIONS = ('.txt', '.md', '.text')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
)
log = logging.getLogger('watcher')


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_bytes(path: str) -> bytes:
    with open(path, 'rb') as f:
        return f.read()


def is_temp_file(name: str) -> bool:
    if name.startswith('~$') or name.startswith('.'):
        return True
    if name.endswith(('.tmp', '.swp', '.bak', '.crdownload')):
        return True
    if '.tmp-' in name or '.tmp_' in name:
        return True
    return False


class IpsHandler(FileSystemEventHandler):
    def __init__(self):
        super().__init__()
        self._last_event = {}
        self._server_hashes = {}

    def _is_target(self, path):
        name = os.path.basename(path)
        if is_temp_file(name):
            return False
        return path.lower().endswith(EXTENSIONS)

    def _debounce_ok(self, path):
        now = time.time()
        last = self._last_event.get(path, 0)
        if now - last < DEBOUNCE:
            return False
        self._last_event[path] = now
        return True

    def refresh_hashes(self):
        try:
            r = requests.get(HASHES_ENDPOINT, timeout=10)
            if r.status_code == 200:
                self._server_hashes = r.json()
                log.info('Хеши с сервера: %d файлов', len(self._server_hashes))
        except Exception as e:
            log.error('Не удалось получить хеши: %s', e)

    def _upload(self, path):
        if not os.path.exists(path):
            return
        name = os.path.basename(path)

        try:
            size = os.path.getsize(path)
        except OSError:
            return
        if size < 20:
            log.debug('= %s слишком мал (%d байт), пропуск', name, size)
            return

        try:
            data1 = read_bytes(path)
            time.sleep(0.3)
            data2 = read_bytes(path)
        except Exception as e:
            log.error('Не читается %s: %s', name, e)
            return

        if data1 != data2:
            log.debug('= %s ещё пишется, пропуск', name)
            return

        data = data2
        if not data.strip():
            log.debug('= %s пустой, пропуск', name)
            return

        data = data.replace(b'\r\n', b'\n')

        local_hash = sha256_bytes(data)
        if self._server_hashes.get(name) == local_hash:
            return

        try:
            files = {'files': (name, data, 'text/plain')}
            r = requests.post(SYNC_ENDPOINT, files=files, timeout=30)
            if r.status_code == 200:
                info = r.json()
                self._server_hashes[name] = local_hash
                log.info('✓ %s → added=%s updated=%s',
                         name, info.get('added'), info.get('updated'))
            else:
                log.error('✗ %s → HTTP %s: %s',
                          name, r.status_code, r.text[:200])
        except requests.ConnectionError:
            log.error('✗ Сервер недоступен: %s', SERVER_URL)
        except Exception as e:
            log.error('✗ %s → %s', name, e)

    def _delete(self, path):
        name = os.path.basename(path)
        if name not in self._server_hashes:
            return
        try:
            r = requests.post(DELETE_ENDPOINT,
                              json={'filename': name}, timeout=15)
            if r.status_code == 200:
                self._server_hashes.pop(name, None)
                log.info('🗑 %s удалён с сервера', name)
        except Exception as e:
            log.error('✗ удаление %s → %s', name, e)

    def on_created(self, event):
        if event.is_directory or not self._is_target(event.src_path):
            return
        if not self._debounce_ok(event.src_path):
            return
        log.info('＋ Создан: %s', os.path.basename(event.src_path))
        self._upload(event.src_path)

    def on_modified(self, event):
        if event.is_directory or not self._is_target(event.src_path):
            return
        if not self._debounce_ok(event.src_path):
            return
        log.info('✎ Изменён: %s', os.path.basename(event.src_path))
        self._upload(event.src_path)

    def on_deleted(self, event):
        if event.is_directory or not self._is_target(event.src_path):
            return
        log.info('－ Удалён: %s', os.path.basename(event.src_path))
        self._delete(event.src_path)

    def on_moved(self, event):
        if event.is_directory:
            return
        if self._is_target(event.src_path):
            self._delete(event.src_path)
        if self._is_target(event.dest_path):
            self._upload(event.dest_path)


def initial_sync(handler, folder):
    log.info('Первичная синхронизация: %s', folder)
    handler.refresh_hashes()
    count = 0
    for p in Path(folder).iterdir():
        if p.is_file() and p.suffix.lower() in EXTENSIONS and not is_temp_file(p.name):
            handler._upload(str(p))
            count += 1
    log.info('Первичная синхронизация завершена, файлов: %s', count)


def main():
    folder = WATCH_DIR
    os.makedirs(folder, exist_ok=True)

    try:
        requests.get(SERVER_URL, timeout=3)
        log.info('Сервер доступен: %s', SERVER_URL)
    except Exception:
        log.error('Сервер недоступен: %s', SERVER_URL)
        log.error('Сначала запусти uvicorn app:app --port 8000')
        sys.exit(1)

    handler = IpsHandler()
    initial_sync(handler, folder)

    observer = Observer()
    observer.schedule(handler, folder, recursive=False)
    observer.start()
    log.info('👁  Слежу за папкой: %s', folder)
    log.info('    Ctrl+C для выхода')

    try:
        last_refresh = time.time()
        while True:
            time.sleep(1)
            if time.time() - last_refresh > 30:
                handler.refresh_hashes()
                last_refresh = time.time()
    except KeyboardInterrupt:
        log.info('Остановлено.')
        observer.stop()
    observer.join()


if __name__ == '__main__':
    main()