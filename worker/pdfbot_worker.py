#!/usr/bin/env python3
import json
import os
import subprocess
import tempfile
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BOT_API_PORT = int(os.environ.get('TELEGRAM_HTTP_PORT', '8081'))
WORKER_PORT = int(os.environ.get('PDFBOT_WORKER_PORT', '8090'))
TELEGRAM_WORK_DIR = Path(os.environ.get('TELEGRAM_WORK_DIR', '/var/lib/telegram-bot-api'))
CALLBACK_HEADER = 'x-pdfbot-worker-secret'


def send_json(url, payload, secret=None):
    data = json.dumps(payload).encode('utf-8')
    request = urllib.request.Request(url, data=data, method='POST', headers={'content-type': 'application/json'})
    if secret:
        request.add_header(CALLBACK_HEADER, secret)
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def bot_call(token, method, payload):
    data = json.dumps(payload).encode('utf-8')
    url = f'http://127.0.0.1:{BOT_API_PORT}/bot{token}/{method}'
    request = urllib.request.Request(url, data=data, method='POST', headers={'content-type': 'application/json'})
    with urllib.request.urlopen(request, timeout=60) as response:
        result = json.loads(response.read().decode('utf-8'))
    if not result.get('ok'):
        raise RuntimeError(result.get('description', f'Telegram {method} failed'))
    return result.get('result')


def resolve_file(file_path):
    candidate = Path(file_path)
    if candidate.is_absolute():
        return candidate
    return TELEGRAM_WORK_DIR / candidate


def _large_image_pages_from_pypdf(path, sample_end):
    from pypdf import PdfReader

    reader = PdfReader(str(path), strict=False)
    pages = min(sample_end, len(reader.pages))
    text_parts = []
    large_image_pages = set()
    for index, page in enumerate(reader.pages[:pages], start=1):
        text_parts.append(page.extract_text() or '')
        try:
            resources = page.get('/Resources')
            if resources is not None:
                resources = resources.get_object()
            xobjects = resources.get('/XObject') if resources else None
            if xobjects is not None:
                xobjects = xobjects.get_object()
                for ref in xobjects.values():
                    obj = ref.get_object()
                    if obj.get('/Subtype') == '/Image':
                        width = int(obj.get('/Width', 0))
                        height = int(obj.get('/Height', 0))
                        if width * height >= 500_000:
                            large_image_pages.add(index)
                            break
        except Exception:
            continue
    return pages, ' '.join(text_parts), large_image_pages


def classify_pdf(path, progress):
    progress('structure', 'Reading PDF structure with pypdf', 35)
    info = subprocess.run(['pdfinfo', str(path)], text=True, capture_output=True, timeout=180)
    if info.returncode != 0:
        raise RuntimeError(info.stderr.strip() or 'pdfinfo could not read the PDF')
    pages = 0
    for line in info.stdout.splitlines():
        if line.lower().startswith('pages:'):
            pages = int(line.split(':', 1)[1].strip())
            break
    sample_end = min(max(pages, 1), 3)
    progress('sampling', f'Sampling pages 1-{sample_end} with pypdf OCR/image analysis', 65)
    try:
        sampled_pages, normalized, large_image_pages = _large_image_pages_from_pypdf(path, sample_end)
    except Exception as exc:
        print(f'pypdf inspection fallback: {exc}', flush=True)
        text = subprocess.run(['pdftotext', '-f', '1', '-l', str(sample_end), '-enc', 'UTF-8', str(path), '-'], text=True, capture_output=True, timeout=240)
        if text.returncode != 0:
            raise RuntimeError(text.stderr.strip() or 'PDF text inspection failed')
        normalized = ' '.join(text.stdout.split())
        sampled_pages = sample_end
        large_image_pages = set()
        images = subprocess.run(['pdfimages', '-f', '1', '-l', str(sample_end), '-list', str(path)], text=True, capture_output=True, timeout=240)
        if images.returncode == 0:
            for line in images.stdout.splitlines():
                fields = line.split()
                if len(fields) >= 5 and fields[0].isdigit() and fields[3].isdigit() and fields[4].isdigit() and int(fields[3]) * int(fields[4]) >= 500_000:
                    large_image_pages.add(int(fields[0]))
    text_found = len(' '.join(normalized.split())) >= 40
    majority_image_pages = len(large_image_pages) >= max(1, (sampled_pages + 1) // 2)
    if not text_found or majority_image_pages:
        return 'Scanned', pages, len(normalized), 'local-pypdf-image-coverage-ocr-aware'
    return 'Selectable', pages, len(normalized), 'local-pypdf-text-layer-without-page-image-coverage'


def run_job(job):
    token = job['bot_token']
    callback_url = job['callback_url']
    callback_secret = job.get('callback_secret', '')
    job_id = job.get('job_id', '')

    def progress(stage, message, percent):
        payload = {'job_id': job_id, 'stage': stage, 'message': message, 'percent': percent, 'status': 'processing', 'context': job.get('context', {})}
        try:
            send_json(callback_url, payload, callback_secret)
        except Exception as exc:
            print(f'callback progress failed: {exc}', flush=True)

    try:
        progress('locating', 'Locating the Telegram file on the local Bot API server', 15)
        result = bot_call(token, 'getFile', {'file_id': job['file_id']})
        path = resolve_file(result['file_path'])
        if not path.exists():
            raise RuntimeError(f'Local Telegram file path is unavailable: {path}')
        progress('located', 'File is available locally; no second Telegram download is required', 25)
        classification, pages, text_length, strategy = classify_pdf(path, progress)
        payload = {
            'job_id': job_id, 'status': 'complete', 'stage': 'classified', 'percent': 100,
            'classification': classification, 'pages_sampled': min(pages, 3),
            'bytes_read': path.stat().st_size, 'text_length': text_length,
            'strategy': strategy, 'context': job.get('context', {}),
        }
        send_json(callback_url, payload, callback_secret)
    except Exception as exc:
        print(f'PDF-BOT job failed: {exc}', flush=True)
        try:
            send_json(callback_url, {
                'job_id': job_id, 'status': 'failed', 'stage': 'failed', 'percent': 100,
                'classification': 'Needs inspection', 'strategy': 'local-worker-failed',
                'error': str(exc)[:500], 'context': job.get('context', {}),
            }, callback_secret)
        except Exception as callback_error:
            print(f'callback failure report failed: {callback_error}', flush=True)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(fmt % args, flush=True)

    def do_GET(self):
        if self.path == '/pdfbot/health':
            body = b'{"ok":true,"service":"pdfbot-local-classifier"}'
            self.send_response(200)
            self.send_header('content-type', 'application/json')
            self.send_header('content-length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)

    def do_POST(self):
        if self.path != '/pdfbot/classify':
            self.send_error(404)
            return
        length = int(self.headers.get('content-length', '0'))
        try:
            job = json.loads(self.rfile.read(length).decode('utf-8'))
            if os.environ.get('PDFBOT_WORKER_SECRET') and self.headers.get(CALLBACK_HEADER) != os.environ['PDFBOT_WORKER_SECRET']:
                self.send_error(401)
                return
            required = ['bot_token', 'file_id', 'callback_url']
            missing = [key for key in required if not job.get(key)]
            if missing:
                self.send_error(400, 'missing: ' + ','.join(missing))
                return
            threading.Thread(target=run_job, args=(job,), daemon=True).start()
            body = b'{"ok":true,"accepted":true}'
            self.send_response(202)
            self.send_header('content-type', 'application/json')
            self.send_header('content-length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:
            self.send_error(400, str(exc))


if __name__ == '__main__':
    ThreadingHTTPServer(('127.0.0.1', WORKER_PORT), Handler).serve_forever()
