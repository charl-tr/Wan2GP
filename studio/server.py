"""Run with .venv/bin/python -m studio.server. Local-only by default."""
from __future__ import annotations
import json
import os
import signal
import subprocess
import sys
import threading
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field, ConfigDict
from studio.bridge import BridgeAuth

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / '.studio'
WEB = Path(__file__).parent / 'web'
for name in ('jobs', 'media', 'uploads', 'trash'):
    (DATA / name).mkdir(parents=True, exist_ok=True)

MODELS = {
    'flux2_klein_4b': {'name': 'Flux 2 Klein', 'size': '4B', 'kind': 'image', 'steps': 4},
    'z_image': {'name': 'Z-Image Turbo', 'size': '6B', 'kind': 'image', 'steps': 9},
    'flux_schnell': {'name': 'Flux Schnell', 'size': '12B', 'kind': 'image', 'steps': 4},
    't2v_1.3B': {'name': 'Wan 2.1', 'size': '1.3B', 'kind': 'video', 'steps': 20},
}
RESOLUTIONS = {
    'draft': {'1:1': '512x512', '16:9': '768x432', '9:16': '432x768', '4:3': '640x480'},
    'standard': {'1:1': '768x768', '16:9': '1024x576', '9:16': '576x1024', '4:3': '896x672'},
}

class GenerationRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    prompt: str = Field(min_length=1, max_length=8000)
    kind: Literal['image', 'video'] = 'image'
    mode: Literal['lazy', 'custom'] = 'lazy'
    aspect: Literal['1:1', '16:9', '9:16', '4:3'] = '1:1'
    quality: Literal['draft', 'standard'] = 'draft'
    model: str = 'flux2_klein_4b'
    steps: int = Field(default=4, ge=1, le=50)
    seed: int = Field(default=-1, ge=-1, le=2147483647)
    reference: str | None = Field(default=None, max_length=64)


def settings_for(body: GenerationRequest) -> dict:
    if not body.prompt.strip():
        raise HTTPException(422, 'Décris d’abord ce que tu veux créer.')
    model = body.model if body.mode == 'custom' else ('flux2_klein_4b' if body.kind == 'image' else 't2v_1.3B')
    if model not in MODELS or MODELS[model]['kind'] != body.kind:
        raise HTTPException(422, 'Ce modèle ne correspond pas au type de création.')
    settings = {'model_type': model, 'prompt': body.prompt.strip(),
                'resolution': RESOLUTIONS[body.quality][body.aspect], 'batch_size': 1,
                'num_inference_steps': body.steps if body.mode == 'custom' else MODELS[model]['steps'],
                'seed': body.seed if body.mode == 'custom' else -1}
    if body.kind == 'video':
        settings.update(video_length=33, force_fps=16)
    if body.reference:
        if model != 'flux2_klein_4b':
            raise HTTPException(422, 'Les références sont disponibles avec Flux 2 Klein.')
        path = DATA / 'uploads' / (body.reference + '.png')
        if not body.reference.isalnum() or not path.is_file():
            raise HTTPException(422, 'Image de référence introuvable. Ajoute-la à nouveau.')
        settings['image_refs'] = [str(path)]
        # 'KI' inherits the first reference's aspect ratio; 'I' conditions on
        # the image while preserving the format chosen in this studio.
        settings['video_prompt_type'] = 'I'
    return settings


def read_json(path, fallback=None):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return fallback


def write_json(path, data):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False))
    tmp.replace(path)

@asynccontextmanager
async def lifespan(app):
    yield
    with lock:
        for key, process in list(active.items()):
            active[key] = 'cancelled'
            if isinstance(process, subprocess.Popen) and process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass

app = FastAPI(title='AFTER Studio · Powered by WanGP', lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost'])
lock = threading.RLock()
active: dict = {}
bridge = BridgeAuth(DATA / 'bridge-sessions.json')

@app.middleware('http')
async def local_requests(request: Request, call_next):
    origin = request.headers.get('origin', '')
    local_origin = str(request.base_url).rstrip('/')
    remote = bool(origin and origin != local_origin)
    cors = {}
    if remote:
        if not bridge.allowed(origin):
            return JSONResponse({'detail': 'Ce site doit être appairé depuis le moteur local.'}, status_code=403)
        cors = {'Access-Control-Allow-Origin': origin, 'Vary': 'Origin',
                'Access-Control-Allow-Headers': 'Authorization, Content-Type, Idempotency-Key',
                'Access-Control-Allow-Methods': 'GET, POST, DELETE, OPTIONS',
                'Access-Control-Allow-Private-Network': 'true'}
        if request.method == 'OPTIONS':
            return JSONResponse({}, headers=cors)
        if request.url.path.startswith('/api/local/'):
            return JSONResponse({'detail': 'Action réservée au studio local.'}, status_code=403, headers=cors)
        token = request.headers.get('authorization', '').removeprefix('Bearer ')
        if not bridge.authorized(origin, token):
            return JSONResponse({'detail': 'Connexion expirée. Appaire à nouveau ton Mac.'}, status_code=401, headers=cors)
    elif request.headers.get('sec-fetch-site') == 'cross-site' and request.url.path != '/':
        # Cross-site image/form requests may omit Origin. Do not expose local files.
        return JSONResponse({'detail': 'Une connexion appairée est requise.'}, status_code=403)
    response = await call_next(request)
    response.headers.update(cors)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['X-Frame-Options'] = 'DENY'
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    return response

class PairRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    origin: str = Field(max_length=300)

@app.post('/api/local/pair')
def approve_pair(body: PairRequest):
    try:
        return {'token': bridge.approve(body.origin), 'origin': body.origin}
    except ValueError as exc:
        raise HTTPException(422, str(exc))

@app.get('/api/local/connections')
def connections():
    return bridge.list_origins()

@app.delete('/api/local/connections')
def revoke_connections():
    bridge.revoke_all()
    return {'ok': True}

@app.get('/api/health')
def health():
    return {'ok': True, 'version': '0.2.0', 'active_jobs': len(active)}

@app.get('/')
def index():
    return FileResponse(WEB / 'index.html', headers={'Cache-Control': 'no-cache'})

@app.get('/api/config')
def config():
    return {'models': [{'id': key, **value} for key, value in MODELS.items()],
            'version': '0.2.0', 'engine': 'WanGP', 'device': 'Apple Silicon' if sys.platform == 'darwin' else 'GPU local'}


def job_snapshot(folder):
    data = read_json(folder / 'request.json')
    if not data:
        return None
    status = read_json(folder / 'status.json', {'state': 'starting', 'message': 'Préparation du moteur…', 'progress': None})
    with lock:
        running_here = folder.name in active
    if status.get('state') in ('starting', 'running', 'downloading') and not running_here:
        status = {**status, 'state': 'failed', 'message': 'Le studio a été interrompu. Relance cette création.'}
    if status.get('state') in ('completed', 'failed', 'cancelled') and 'elapsed_seconds' not in status:
        status['elapsed_seconds'] = round(max(0, (folder / 'status.json').stat().st_mtime - data['created']), 1) if (folder / 'status.json').exists() else 0
    return {'id': folder.name, 'created': data['created'], 'request': data['request'], 'settings': data['settings'], **status}

@app.get('/api/jobs')
def jobs():
    return [j for p in sorted((DATA / 'jobs').iterdir(), key=lambda p: p.name, reverse=True)
            if p.is_dir() and (j := job_snapshot(p)) is not None]


def run_job(job_id, folder):
    log = open(folder / 'engine.log', 'w')
    try:
        with lock:
            if active.get(job_id) == 'cancelled':
                write_json(folder / 'status.json', {'state': 'cancelled', 'message': 'Création arrêtée.', 'progress': None})
                return
            process = subprocess.Popen([sys.executable, '-u', '-m', 'studio.worker', str(folder)],
                cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            active[job_id] = process
        try:
            code = process.wait(timeout=1800)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            code = -1
            write_json(folder / 'status.json', {'state': 'failed', 'message': 'Limite de 30 minutes atteinte.', 'error': 'Essaie une résolution plus basse ou un modèle plus léger.', 'progress': None})
        with lock:
            cancelled = active.get(job_id) == 'cancelled'
            status = read_json(folder / 'status.json', {})
            if cancelled:
                write_json(folder / 'status.json', {'state': 'cancelled', 'message': 'Création arrêtée.', 'progress': None})
            elif status.get('state') not in ('completed', 'failed'):
                write_json(folder / 'status.json', {'state': 'failed', 'message': 'Le moteur s’est arrêté. Consulte les détails pour diagnostiquer.', 'error': f'Worker exit code: {code}', 'progress': None})
    except Exception as exc:
        write_json(folder / 'status.json', {'state': 'failed', 'message': 'Impossible de démarrer le moteur.', 'error': str(exc)})
    finally:
        log.close()
        with lock:
            active.pop(job_id, None)

@app.post('/api/jobs', status_code=202)
def create_job(body: GenerationRequest, request: Request):
    settings = settings_for(body)
    with lock:
        idempotency_key = request.headers.get('idempotency-key', '')[:128]
        if idempotency_key:
            for folder in (DATA / 'jobs').iterdir():
                prior = read_json(folder / 'request.json', {})
                if prior.get('idempotency_key') == idempotency_key:
                    if prior['request'] != body.model_dump():
                        raise HTTPException(409, 'Cette requête a déjà été utilisée avec un autre prompt.')
                    return {'id': folder.name}
        if active:
            raise HTTPException(409, 'Une création est déjà en cours. Attends la fin ou arrête-la.')
        job_id = f'{time.time_ns()}-{uuid.uuid4().hex[:8]}'
        folder = DATA / 'jobs' / job_id
        folder.mkdir()
        write_json(folder / 'request.json', {'request': body.model_dump(), 'settings': settings, 'created': time.time(), 'idempotency_key': idempotency_key})
        write_json(folder / 'status.json', {'state': 'starting', 'message': 'Préparation du moteur…', 'progress': None})
        active[job_id] = None
        threading.Thread(target=run_job, args=(job_id, folder), daemon=True).start()
    return {'id': job_id}

@app.post('/api/jobs/{job_id}/cancel')
def cancel(job_id: str):
    with lock:
        if job_id not in active:
            raise HTTPException(409, 'Cette création est déjà terminée.')
        process = active[job_id]
        active[job_id] = 'cancelled'
        if isinstance(process, subprocess.Popen) and process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    return {'ok': True}

@app.get('/api/jobs/{job_id}/log')
def job_log(job_id: str):
    if '/' in job_id or '..' in job_id:
        raise HTTPException(404)
    path = DATA / 'jobs' / job_id / 'engine.log'
    if not path.is_file():
        raise HTTPException(404)
    with path.open('rb') as log:
        log.seek(max(0, path.stat().st_size - 18000))
        return {'text': log.read().decode(errors='replace')}


@app.delete('/api/jobs/{job_id}')
def archive_job(job_id: str):
    if '/' in job_id or '..' in job_id:
        raise HTTPException(404)
    with lock:
        if job_id in active:
            raise HTTPException(409, 'Arrête cette création avant de la retirer.')
        folder = DATA / 'jobs' / job_id
        if not folder.is_dir():
            raise HTTPException(404)
        (DATA / 'trash').mkdir(exist_ok=True)
        folder.rename(DATA / 'trash' / job_id)
    return {'ok': True}

@app.post('/api/uploads')
async def upload(file: UploadFile):
    import io
    from PIL import Image, ImageOps
    data = await file.read(10 * 1024 * 1024 + 1)
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(413, 'Image trop lourde (10 Mo maximum).')
    try:
        with Image.open(io.BytesIO(data)) as source:
            if source.width * source.height > 25_000_000:
                raise ValueError('Image too large')
            im = ImageOps.exif_transpose(source).convert('RGB')
            im.thumbnail((2048, 2048))
            key = uuid.uuid4().hex
            im.save(DATA / 'uploads' / (key + '.png'))
    except Exception:
        raise HTTPException(422, 'Choisis une image JPG, PNG ou WebP valide.')
    return {'id': key, 'url': f'/uploads/{key}.png'}

app.mount('/assets', StaticFiles(directory=WEB / 'assets'), name='assets')
app.mount('/media', StaticFiles(directory=DATA / 'media'), name='media')
app.mount('/uploads', StaticFiles(directory=DATA / 'uploads'), name='uploads')

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=7861)
