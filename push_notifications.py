"""Persistent device-scoped arrival watches and Web Push delivery."""
import base64
import hashlib
import json
import math
import os
import re
import sqlite3
import threading
import time
from pathlib import Path
from contextlib import contextmanager
from urllib.parse import urlsplit

import requests


def valid_subscription(value):
    if not isinstance(value, dict):
        raise ValueError('Invalid push subscription')
    endpoint = value.get('endpoint', '')
    url = urlsplit(endpoint)
    host = url.hostname or ''
    allowed = host in {'fcm.googleapis.com', 'updates.push.services.mozilla.com', 'web.push.apple.com'} or host.endswith('.push.apple.com')
    if not (allowed and url.scheme == 'https' and url.port in (None, 443) and not url.username and not url.password and len(endpoint) < 2048):
        raise ValueError('Unsupported browser push provider')
    keys = value.get('keys', {})
    for key, length in [('p256dh', 65), ('auth', 16)]:
        raw = keys.get(key, '')
        if not isinstance(raw, str) or len(raw) > 120:
            raise ValueError('Invalid subscription key')
        try:
            decoded = base64.b64decode(raw + '=' * (-len(raw) % 4), altchars=b'-_', validate=True)
        except Exception as exc:
            raise ValueError('Invalid subscription key') from exc
        if len(decoded) != length:
            raise ValueError('Invalid subscription key')
    return dict(endpoint=endpoint, keys={key:keys[key] for key in ('p256dh','auth')})


def arrival_due(row, watch, now):
    live, updated = row.get('live'), row.get('updated_at')
    return bool(row.get('status') == 'Live' and live is not None and updated is not None
                and -30 <= now-updated <= 120 and 0 < live-now <= watch['minutes']*60
                and (not watch.get('route_id') or row['route_id'] == watch['route_id']))


class NoRedirectSession(requests.Session):
    def request(self, *args, **kwargs):
        kwargs['allow_redirects'] = False
        return super().request(*args, **kwargs)


class PushStore:
    def __init__(self, directory='.cache/push', sender=None):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = self.directory/'watches.sqlite3'
        self.key = self.directory/'vapid.pem'
        self.guard = threading.RLock()
        self.sender = sender or self.send
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS devices(id TEXT PRIMARY KEY, subscription TEXT, watches TEXT, error TEXT DEFAULT '', updated REAL);
                CREATE TABLE IF NOT EXISTS sent(device TEXT, arrival TEXT, retry_after REAL, PRIMARY KEY(device,arrival));
            ''')
        if os.name != 'nt':
            self.db.chmod(0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.db, timeout=15)
        try:
            with db:
                yield db
        finally:
            db.close()

    def public_key(self):
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import serialization
        with self.guard:
            if not self.key.exists():
                key = ec.generate_private_key(ec.SECP256R1())
                pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
                fd = os.open(self.key, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd,'wb') as file:
                    file.write(pem)
            key = serialization.load_pem_private_key(self.key.read_bytes(), password=None)
            raw = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
            return base64.urlsafe_b64encode(raw).decode().rstrip('=')

    @staticmethod
    def identity(token):
        if not re.fullmatch(r'[A-Za-z0-9_-]{40,128}', token or ''):
            raise ValueError('Missing device key')
        return hashlib.sha256(token.encode()).hexdigest()

    def save(self, token, subscription, watches):
        identity = self.identity(token)
        with self.guard, self.connect() as db:
            db.execute('INSERT INTO devices(id,subscription,watches,updated) VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET subscription=excluded.subscription,watches=excluded.watches,error="",updated=excluded.updated',
                       (identity, json.dumps(subscription), json.dumps(watches), time.time()))

    def read(self, token):
        with self.connect() as db:
            row = db.execute('SELECT watches,error FROM devices WHERE id=?',(self.identity(token),)).fetchone()
        return dict(watches=json.loads(row[0]),error=row[1]) if row else dict(watches=[],error='')

    def send(self, subscription, payload):
        from pywebpush import webpush
        self.public_key()
        with NoRedirectSession() as session:
            response = webpush(subscription_info=subscription, data=json.dumps(payload),
                    vapid_private_key=str(self.key), vapid_claims={'sub':os.environ['VAPID_SUBJECT']},
                    ttl=60, timeout=10, headers={'Urgency':'high'}, requests_session=session)
            if not 200 <= response.status_code < 300:
                raise RuntimeError('Push rejected')

    def tick(self, board, updates, feed_time, now=None):
        now = now or time.time()
        if board is None or not feed_time or not -30 <= now-feed_time <= 120:
            return
        with self.connect() as db:
            devices = db.execute('SELECT id,subscription,watches FROM devices').fetchall()
            db.execute('DELETE FROM sent WHERE retry_after<?',(now-172800,))
        boards = {}
        for device, subscription, raw_watches in devices:
            for watch in json.loads(raw_watches):
                if not watch.get('enabled'):
                    continue
                stop_id = watch['stop']['id']
                if stop_id not in boards:
                    boards[stop_id] = board.arrivals(stop_id, updates, feed_time, now, limit=None)
                for row in boards[stop_id]:
                    if not arrival_due(row, watch, now):
                        continue
                    arrival = json.dumps([stop_id,row['trip_id'],row['service_date'],row['sequence']])
                    with self.guard, self.connect() as db:
                        current = db.execute('SELECT watches FROM devices WHERE id=?',(device,)).fetchone()
                        if not current or not any(w.get('enabled') and w['revision']==watch['revision'] for w in json.loads(current[0])):
                            break
                        prior = db.execute('SELECT retry_after FROM sent WHERE device=? AND arrival=?',(device,arrival)).fetchone()
                        if prior and prior[0] > now:
                            continue
                        # Reserve before network I/O so concurrent ticks cannot double-send.
                        db.execute('INSERT OR REPLACE INTO sent VALUES(?,?,?)',(device,arrival,now+60))
                    minutes = max(1, math.ceil((row['live']-now)/60))
                    payload = dict(title=f"Line {row['line']} · {minutes} min", body=f"{watch['stop']['name']} → {row['destination']}",
                                   stop=watch['stop'], arrival=row['live'], revision=watch['revision'],
                                   tag=hashlib.sha256((device+arrival).encode()).hexdigest(), sent_at=now)
                    try:
                        self.sender(json.loads(subscription), payload)
                        with self.connect() as db:
                            db.execute('UPDATE sent SET retry_after=? WHERE device=? AND arrival=?',(now+172800,device,arrival))
                            db.execute('UPDATE devices SET error="" WHERE id=?',(device,))
                    except Exception as exc:
                        status = getattr(getattr(exc,'response',None),'status_code',None)
                        with self.connect() as db:
                            if status in (404,410):
                                disabled=json.loads(raw_watches)
                                for w in disabled:w['enabled']=False
                                db.execute('UPDATE devices SET watches=?,error=? WHERE id=?',(json.dumps(disabled),'Reconnect notifications on this device',device))
                            else:
                                db.execute('UPDATE devices SET error=? WHERE id=?',('Delivery delayed; retrying',device))
                        if status in (404,410):
                            break


def attach_push(app, snapshot):
    from flask import jsonify, request
    store = PushStore()
    test_times = {}

    @app.post('/api/notifications/test')
    def push_test():
        try:
            identity=store.identity(request.headers.get('Authorization','').removeprefix('Bearer '))
            with store.guard, store.connect() as db:
                row=db.execute('SELECT subscription,watches FROM devices WHERE id=?',(identity,)).fetchone()
                active=next((w for w in json.loads(row[1]) if w['enabled']),None) if row else None
                if not active:return jsonify(error='Enable a stop notification first'),400
                now=time.time()
                if now-test_times.get(identity,0)<30:return jsonify(error='Wait 30 seconds before another test'),429
                test_times[identity]=now
            store.send(json.loads(row[0]),dict(title='Notifications are working',body='This is a test. Your arrival alerts are enabled.',
                       stop=active['stop'],revision=active['revision'],arrival=now+60,sent_at=now,tag='transit-test'))
            return jsonify(ok=True)
        except ValueError:return jsonify(error='Invalid device key'),400
        except Exception:return jsonify(error='Push delivery failed. Try re-enabling notifications.'),502

    @app.get('/api/notifications/config')
    def push_config():
        subject = os.getenv('VAPID_SUBJECT', '').strip()
        contact = urlsplit(subject)
        if not ((contact.scheme == 'mailto' and '@' in contact.path)
                or (contact.scheme == 'https' and contact.hostname)):
            return jsonify(error='Notifications are not configured: set VAPID_SUBJECT to an operator contact.'), 503
        try:
            return jsonify(public_key=store.public_key())
        except ImportError:
            return jsonify(error='Push dependencies are not installed'),503

    @app.route('/api/notifications/device', methods=['GET','PUT'])
    def push_device():
        token = request.headers.get('Authorization','').removeprefix('Bearer ')
        try:
            store.identity(token)
            if request.method=='GET':
                return jsonify(store.read(token))
            if request.content_length and request.content_length > 65536:
                return jsonify(error='Too many tracking settings'),413
            data = request.get_json(silent=True) or {}
            subscription = valid_subscription(data.get('subscription'))
            watches=data.get('watches')
            if not isinstance(watches,list) or len(watches)>20:
                raise ValueError('Track up to 20 stops per device')
            board,_,_=snapshot()
            if board is None:return jsonify(error='Stops are loading; try again shortly'),503
            cleaned=[]
            for w in watches:
                stop_id=str(w.get('stop',{}).get('id',''))
                minutes=w.get('minutes')
                route_id=str(w.get('route_id',''))
                revision=w.get('revision','')
                if stop_id not in board.stops or type(minutes) is not int or not 1<=minutes<=60 or type(w.get('enabled')) is not bool:
                    raise ValueError('Choose a valid stop and 1–60 minutes')
                if route_id and route_id not in board.stop_routes.get(stop_id,()):
                    raise ValueError('That line does not serve this stop')
                if not re.fullmatch(r'[a-zA-Z0-9-]{16,80}',revision):raise ValueError('Invalid tracking revision')
                if any(c['stop']['id']==stop_id for c in cleaned):raise ValueError('Duplicate stop')
                stop=board.stops[stop_id]
                cleaned.append(dict(stop=dict(id=stop_id,name=stop['name'],lat=stop['lat'],lon=stop['lon']),minutes=minutes,
                                    route_id=route_id,enabled=w['enabled'],revision=revision))
            store.save(token,subscription,cleaned)
            return jsonify(store.read(token))
        except (ValueError,TypeError,AttributeError,KeyError):
            return jsonify(error='Invalid notification settings or device key'),400

    def worker():
        while True:
            try:
                board, updates, timestamp = snapshot()
                store.tick(board,updates,timestamp)
            except Exception:
                app.logger.warning('Arrival notification check failed; retrying')
            time.sleep(5)
    return worker
