"""Persistent local sessions with hashed tokens and the existing eight-hour expiry."""
import hashlib
import hmac
import os
import secrets
import time
from . import store


def init():
    with store.db() as db:
        db.execute('CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,role TEXT,name TEXT,expires REAL,auth_proof TEXT)')


def _key(token):
    return hashlib.sha256(token.encode()).hexdigest()


def _proof(token, role, local_roles):
    config = 'local-roles' if local_roles else 'password:' + os.getenv('HYDRO_' + role.upper() + '_PASSWORD', '')
    return hmac.new(token.encode(), (role + ':' + config).encode(), hashlib.sha256).hexdigest()


def create(role, name, local_roles):
    token = secrets.token_urlsafe(32)
    user = {'role': role, 'name': name, 'expires': time.time() + 28800}
    with store.db() as db:
        db.execute('DELETE FROM sessions WHERE expires <= ?', (time.time(),))
        db.execute('INSERT INTO sessions VALUES(?,?,?,?,?)', (_key(token), role, name, user['expires'], _proof(token, role, local_roles)))
    return token, user


def get(token, local_roles):
    if not token or len(token) > 128:
        return None
    with store.db() as db:
        row = db.execute('SELECT * FROM sessions WHERE token_hash=?', (_key(token),)).fetchone()
    if not row or row['expires'] <= time.time() or not hmac.compare_digest(row['auth_proof'], _proof(token, row['role'], local_roles)):
        return None
    return {key: row[key] for key in ('role', 'name', 'expires')}


def delete(token):
    if token:
        with store.db() as db:
            db.execute('DELETE FROM sessions WHERE token_hash=?', (_key(token),))
