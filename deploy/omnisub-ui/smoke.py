#!/usr/bin/env python3
"""Synthetic, stateless OmniSub public gateway checks; never prints feed tokens.

Usage: python3 smoke.py https://sub.example.com [--legacy] [--api-only]
--legacy: accepts the original UI and the old gateway's known Clash YAML rejection.
"""
import argparse
import base64
import json
import re
import sys
import time
from html.parser import HTMLParser
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

class HTML(HTMLParser):
    def __init__(self):
        super().__init__(); self.title = ''; self.in_title = False; self.assets = []
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'title': self.in_title = True
        if tag == 'script' and attrs.get('src'): self.assets.append(attrs['src'])
        if tag == 'link' and attrs.get('rel') == 'stylesheet': self.assets.append(attrs.get('href', ''))
    def handle_endtag(self, tag):
        if tag == 'title': self.in_title = False
    def handle_data(self, data):
        if self.in_title: self.title += data

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('base_url')
p.add_argument('--legacy', action='store_true')
p.add_argument('--api-only', action='store_true')
p.add_argument('--allow-known-clash-provider-rejection', action='store_true', help='accept only the known safe 422 for Clash YAML full configuration; node-list cases remain mandatory')
a = p.parse_args()
base = a.base_url.rstrip('/') + '/'
assert urlsplit(base).scheme in ('http', 'https'), 'base URL must be HTTP(S)'
results = []

def request(path, payload=None):
    # Stay below public gateway request limits; contains no real subscription.
    time.sleep(0.3)
    u = urljoin(base, path)
    if urlsplit(u).netloc != urlsplit(base).netloc:
        raise AssertionError('cross-origin URL refused')
    body = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None
    req = Request(u, data=body, headers={'Content-Type': 'application/json'} if body else {})
    try:
        with urlopen(req, timeout=50) as r:
            return r.status, r.headers.get_content_type(), r.read(3_000_001)
    except HTTPError as e:
        return e.code, e.headers.get_content_type(), e.read(100_000)

def check(name, fn):
    try:
        fn(); results.append((name, True)); print('PASS', name)
    except Exception as e:
        # No URLs, tokens, subscription content, or exception body in output.
        results.append((name, False)); print('FAIL', name, type(e).__name__)

def homepage():
    status, mime, raw = request('/')
    assert status == 200 and mime == 'text/html'
    html = HTML(); html.feed(raw.decode('utf-8'))
    assert 'OmniSub' in html.title
    assets = html.assets
    assert assets and any(urlsplit(x).path.endswith('.js') for x in assets)
    assert any(urlsplit(x).path.endswith('.css') for x in assets)
    for asset in assets:
        status, mime, raw = request(asset)
        assert status == 200 and raw
        if urlsplit(asset).path.endswith('.js'):
            assert mime in ('application/javascript', 'text/javascript', 'application/x-javascript')
        elif urlsplit(asset).path.endswith('.css'): assert mime == 'text/css'
    if not a.legacy:
        # New deployment preserves stable paths and may attach build cache keys.
        assert all(
            any(urlsplit(x).path == path and urlsplit(x).query.startswith('v=') for x in assets)
            for path in ('/assets/app.js', '/assets/style.css')
        )

def health():
    status, _, raw = request('/healthz')
    assert status == 200 and raw.strip() == b'ok'

ssauth = base64.urlsafe_b64encode(b'aes-128-gcm:synthetic-password').decode().rstrip('=')
ss = 'ss://' + ssauth + '@ss.example.com:443#Synthetic-SS'
vless = 'vless://11111111-1111-4111-8111-111111111111@vless.example.com:443?encryption=none&security=tls&sni=vless.example.com&type=tcp#Synthetic-VLESS'

def generate(target, source=ss, ver=None, reject=False, must_contain=None, list_only=False, allow_protected=False, count=1):
    payload = {'target': target, 'sources': source, 'list': list_only}
    if ver is not None: payload['ver'] = str(ver)
    status, mime, raw = request('/api/links', payload)
    if allow_protected and status == 422:
        assert json.loads(raw).get('error') == '转换后的 Hysteria2 认证与来源不一致，已停止交付。'
        print('KNOWN-PROTECTED Clash full YAML uses provider output; no invalid feed delivered')
        return
    if reject:
        assert status in (400, 422), 'expected explicit unsupported conversion rejection'
        assert isinstance(json.loads(raw).get('error'), str)
        return
    assert status == 200 and mime == 'application/json'
    doc = json.loads(raw)
    assert doc['count'] == count
    path = doc['path']
    assert isinstance(path, str) and path.startswith('/s/') and len(path) > 30
    status, mime, raw = request(path)
    assert status == 200 and mime == 'text/plain' and raw
    text = raw.decode('utf-8')
    if target in ('clash', 'stash'):
        assert re.search(r'^proxies:', text, re.M) and 'Synthetic-' in text
        if target == 'clash' and not (a.legacy or a.allow_known_clash_provider_rejection):
            assert not re.search(r'^proxy-providers:', text, re.M)
            assert not re.search(r'(?m)^\s+use:', text)
    elif target == 'surge':
        assert '[Proxy]' in text and 'Synthetic-' in text
        assert '#!MANAGED-CONFIG' not in text
    else:
        text = base64.b64decode(raw).decode('utf-8')
        assert 'ss://' in text
    if must_contain:
        for word in must_contain: assert word in text

if not a.api_only: check('homepage-title-and-linked-assets', homepage)
check('healthz', health)
for name, target, ver in [('Mihomo-Clash', 'clash', None), ('Stash', 'stash', None), ('Surge-5', 'surge', 5), ('Surge-6', 'surge', 6), ('Shadowrocket', 'shadowrocket', None)]:
    check(name + '-SS-create-and-download', lambda t=target, v=ver: generate(t, ver=v))
check('Surge-6-VLESS-create-and-download', lambda: generate('surge', vless, 6, must_contain=['vless']))
check('Surge-5-VLESS-explicit-rejection', lambda: generate('surge', vless, 5, reject=True))
for field in ('auth', 'password'):
    for complexity, secret in [('ordinary', 'synthetic-password'), ('complex', 'synthetic:auth@20%')]:
        source = 'proxies:\n  - name: Synthetic-HY2\n    type: hysteria2\n    server: hy2.example.com\n    port: 443\n    ' + field + ': "' + secret + '"\n    sni: hy2.example.com\n'
        for target in ('clash', 'stash'):
            allow = target == 'clash' and (a.legacy or a.allow_known_clash_provider_rejection)
            check('Hysteria2-' + field + '-' + complexity + '-full-to-' + target, lambda s=source, t=target, pw=secret, allowed=allow: generate(t, s, must_contain=[pw], allow_protected=allowed))
        check('Hysteria2-' + field + '-' + complexity + '-node-list-to-clash', lambda s=source, pw=secret: generate('clash', s, must_contain=[pw], list_only=True))
source = 'proxies:\n  - name: Synthetic-HY2\n    type: hysteria2\n    server: hy2.example.com\n    port: 443\n    auth: "synthetic-a"\n    password: "synthetic-b"\n'
check('Hysteria2-conflicting-auth-explicit-rejection', lambda: generate('stash', source, reject=True))
if not (a.legacy or a.allow_known_clash_provider_rejection):
    rows = [
        dict(name='Synthetic-YAML-SS', type='ss', server='ss.example.com', port=443,
             cipher='aes-128-gcm', password='synthetic-password'),
    ]
    rows.append({**rows[0], 'name': 'Synthetic-YAML-Second', 'server': 'ss2.example.com'})
    source = json.dumps({'proxies': rows})
    check('Mihomo-multiple-YAML-nodes-keep-group-and-rules', lambda: generate(
        'clash', source, count=2,
        must_contain=['Synthetic-YAML-SS', 'Synthetic-YAML-Second', 'MATCH,Proxy', 'DIRECT'],
    ))
failed = sum(not passed for _, passed in results)
print('RESULT', len(results) - failed, 'passed;', failed, 'failed')
sys.exit(1 if failed else 0)
