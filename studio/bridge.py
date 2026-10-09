"""Explicit, origin-bound pairing for the hosted UI and a loopback engine.

No tunnel, no LAN listener, no credentials shipped to Vercel. The local UI
approves an HTTPS origin and issues a revocable bearer token to that origin.
"""
from __future__ import annotations
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

SESSION_LIFETIME = 30 * 86400

class BridgeAuth:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.RLock()

    def _read(self):
        try:
            return json.loads(self.path.read_text())
        except (OSError, ValueError):
            return []

    def _write(self, sessions):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(sessions))
        os.chmod(temp, 0o600)
        temp.replace(self.path)

    @staticmethod
    def validate_origin(origin: str) -> str:
        url = urlsplit(origin)
        if (url.scheme != 'https' or not url.hostname or url.username or url.password
                or url.path or url.query or url.fragment or url.port not in (None, 443)):
            raise ValueError('Une origine HTTPS exacte est requise, sans chemin ni identifiants.')
        return origin

    def approve(self, origin: str):
        origin = self.validate_origin(origin)
        token = secrets.token_urlsafe(32)
        with self.lock:
            sessions = [s for s in self._read() if s['origin'] != origin and s['expires'] > time.time()]
            sessions.append({'origin': origin, 'digest': hashlib.sha256(token.encode()).hexdigest(),
                             'expires': time.time() + SESSION_LIFETIME})
            self._write(sessions)
        return token

    def allowed(self, origin: str) -> bool:
        with self.lock:
            return any(s['origin'] == origin and s['expires'] > time.time() for s in self._read())

    def authorized(self, origin: str, token: str) -> bool:
        digest = hashlib.sha256(token.encode()).hexdigest()
        with self.lock:
            return any(s['origin'] == origin and s['expires'] > time.time()
                       and hmac.compare_digest(s['digest'], digest) for s in self._read())

    def list_origins(self):
        with self.lock:
            return [{'origin': s['origin'], 'expires': s['expires']}
                    for s in self._read() if s['expires'] > time.time()]

    def revoke_all(self):
        with self.lock:
            self._write([])
