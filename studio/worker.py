"""One isolated WanGP job; terminating it releases its model memory."""
import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def validate_image(path):
    from PIL import Image
    with Image.open(path) as image:
        extrema = image.convert('RGB').getextrema()
        if all(lo == hi == 0 for lo, hi in extrema):
            raise RuntimeError('Le modèle a produit une image entièrement noire. Le calcul numérique a probablement échoué ; aucune image valide à afficher.')

def main():
    folder = Path(sys.argv[1]).resolve()
    started = time.monotonic()
    payload = json.loads((folder / 'request.json').read_text())
    def status(**data):
        if data.get('state') in ('completed', 'failed'):
            data['elapsed_seconds'] = round(time.monotonic() - started, 1)
        path = folder / 'status.json'
        tmp = folder / 'status.worker.tmp'
        tmp.write_text(json.dumps(data, ensure_ascii=False))
        tmp.replace(path)

    class Callbacks:
        def on_status(self, value):
            text = str(value)
            download = 'download' in text.lower()
            status(state='downloading' if download else 'running', message='Téléchargement du modèle…' if download else 'Préparation de la création…', detail=text, progress=None)
        def on_progress(self, value):
            status(state='running', message='Chargement du modèle…' if any(word in str(value.status).lower() for word in ('loading', 'preparing')) else 'Ton idée prend forme…', detail=str(value.status),
                   progress=max(0, min(100, value.progress)), step=value.current_step, total=value.total_steps)
        def on_stream(self, value):
            if 'download' in value.text.lower():
                status(state='downloading', message='Téléchargement des fichiers du modèle…', detail=value.text[-300:], progress=None)
    try:
        status(state='starting', message='Démarrage du moteur…', progress=None)
        cli_args = ['--attention', 'sdpa', '--profile', '4', '--ram-allocator', 'default']
        if sys.platform == 'darwin':
            # Upstream classifies M2 as FP16-only. Modern macOS/PyTorch can
            # execute BF16; probe it before retaining the model's native range.
            import torch
            try:
                probe = torch.ones((4, 4), device='mps', dtype=torch.bfloat16)
                if bool(torch.isfinite(probe @ probe).all()):
                    cli_args.append('--bf16')
                del probe
            except (RuntimeError, TypeError):
                pass
        from shared.api import init
        config = json.loads((ROOT / 'wgp_config.json').read_text()) if (ROOT / 'wgp_config.json').exists() else {}
        if sys.platform == 'darwin':
            config['vae_precision'] = '32'
        config_path = folder / 'wgp_config.json'
        config_path.write_text(json.dumps(config))
        session = init(root=ROOT, config_path=config_path, output_dir=ROOT / '.studio' / 'raw',
                       cli_args=cli_args,
                       console_isatty=False)
        settings = session.get_default_settings(payload['settings']['model_type'])
        settings.update(payload['settings'])
        job = session.submit_task(settings, callbacks=Callbacks())
        result = job.result()
        files = []
        for index, filename in enumerate(result.generated_files):
            source = Path(filename)
            if not source.is_absolute():
                source = ROOT / source
            suffix = source.suffix.lower()
            if source.is_file() and suffix in {'.png', '.jpg', '.jpeg', '.webp', '.mp4', '.webm'}:
                if suffix in {'.png', '.jpg', '.jpeg', '.webp'}:
                    validate_image(source)
                name = f'{folder.name}-{index}{suffix}'
                shutil.copy2(source, ROOT / '.studio' / 'media' / name)
                entry = {'url': '/media/' + name, 'kind': 'video' if suffix in {'.mp4', '.webm'} else 'image'}
                if entry['kind'] == 'image':
                    from PIL import Image
                    with Image.open(source) as image:
                        entry.update(width=image.width, height=image.height)
                files.append(entry)
        if result.success and files:
            status(state='completed', message='C’est prêt.', progress=100, files=files)
        else:
            errors = '\n'.join(error.message for error in result.errors) or 'Le moteur n’a retourné aucun fichier.'
            status(state='failed', message='La génération n’a pas abouti.', error=errors, files=files, progress=None)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        status(state='failed', message='Le moteur a rencontré un problème.', error=str(exc), progress=None)

if __name__ == '__main__':
    main()
