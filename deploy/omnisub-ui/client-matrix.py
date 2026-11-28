#!/usr/bin/env python3
"""Synthetic gateway parity checks. No real subscription, token or response is logged.
Usage: python3 client-matrix.py BASE_URL
Use --api-only to skip the full client catalog.
"""
import argparse, base64, csv, json, re, sys, time
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('base_url');p.add_argument('--api-only',action='store_true')
p.add_argument('--spacing',type=float,default=.5,help='minimum seconds between requests (default 0.5)')
a=p.parse_args(); base=a.base_url.rstrip('/')+'/'; results=[]; last=0
assert urlsplit(base).scheme in ('http','https')
def b64(s):return base64.urlsafe_b64encode(s.encode()).decode().rstrip('=')
def decode64(s):return base64.b64decode(s+'='*(-len(s)%4),altchars=b'-_',validate=True).decode()
SS='ss://'+b64('aes-128-gcm:synthetic-password')+'@ss.example.com:443#Synthetic-SS'
VL='vless://11111111-1111-4111-8111-111111111111@vl.example.com:443?encryption=none&security=tls&sni=vl.example.com&type=tcp#Synthetic-VLESS'
TR='trojan://synthetic-password@tr.example.com:443?sni=tr.example.com#Synthetic-Trojan'
HY='hysteria2://synthetic-password@hy.example.com:443?sni=hy.example.com#Synthetic-HY2'
VM='vmess://'+b64(json.dumps({'v':'2','ps':'Synthetic-VM','add':'vm.example.com','port':'443','id':'11111111-1111-4111-8111-111111111111','aid':'0','net':'tcp','type':'none','host':'','path':'','tls':''}))
SSR='ssr://'+b64('ssr.example.com:443:origin:aes-128-cfb:plain:'+b64('synthetic-password')+'/?remarks='+b64('Synthetic-SSR'))
FORMATS=['clash','clashr','stash','quan','quanx','loon','surfboard','mellow','singbox','ss','ssd','ssr','sssub','v2ray','v2rayn','v2rayng','shadowrocket','trojan','vless','hysteria2','mixed']
CHOICES=[(t,None) for t in FORMATS]+[('surge',v) for v in range(2,7)]
assert len(CHOICES)==26

def request(path,body=None):
 global last
 time.sleep(max(0,a.spacing-(time.monotonic()-last)));last=time.monotonic()
 u=urljoin(base,path);assert urlsplit(u).netloc==urlsplit(base).netloc
 req=Request(u,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'} if body is not None else {})
 try:
  with urlopen(req,timeout=50) as r:return r.status,r.headers.get_content_type(),r.read(3_000_001)
 except HTTPError as e:return e.code,e.headers.get_content_type(),e.read(100_000)

def check(name,fn):
 try:fn();results.append(True);print('PASS',name,flush=True)
 except Exception as e:results.append(False);print('FAIL',name,type(e).__name__,flush=True)

def recipe(t='clash',src=SS,v=None,**extra):
 d={'target':t,'sources':src,'list':False,**extra}
 if v is not None:d['ver']=str(v)
 return d

def make(d):
 status,mime,raw=request('/api/links',d);assert status==200 and mime=='application/json'
 doc=json.loads(raw);assert doc.get('count')==len(d['sources'].splitlines())
 path=doc.get('path');assert isinstance(path,str) and path.startswith('/s/') and len(path)>30
 status,mime,raw=request(path);assert status==200 and mime=='text/plain' and raw
 return raw.decode()

def section(text,name):
 m=re.search(r'^\['+re.escape(name)+r'\][ \t]*\r?\n(.*?)(?=^\[|\Z)',text,re.M|re.S|re.I)
 assert m
 return [line.strip() for line in m[1].splitlines() if line.strip() and not line.lstrip().startswith(('#',';'))]

def count_output(t,text):
 if t in ('clash','clashr','stash'):
  m=re.search(r'^proxies:[ \t]*(.*?)(?=^[A-Za-z][\w-]*:|\Z)',text,re.M|re.S);assert m
  return len(re.findall(r'\bname\s*:',m[1]))
 if t in ('surge','surfboard','loon','quan'):
  rows=section(text,'SERVER' if t=='quan' else 'Proxy')
  return sum(bool(re.match(r'^[^=]+=\s*(?!direct\b|reject\b)[\w-]+\s*,',x,re.I)) for x in rows)
 if t=='quanx':return sum(bool(re.match(r'^[\w-]+\s*=\s*[^,]+,',x)) for x in section(text,'server_local'))
 if t=='mellow':
  rows=[next(csv.reader([x],skipinitialspace=True)) for x in section(text,'Endpoint')]
  return sum(len(x)>2 and x[1].strip().lower()!='builtin' for x in rows)
 if t=='ssd':assert text.startswith('ssd://');return len(json.loads(decode64(text[6:].strip()))['servers'])
 if t=='sssub':
  doc=json.loads(text);rows=doc if isinstance(doc,list) else doc['servers'];assert all(isinstance(x,dict) and x.get('server') for x in rows);return len(rows)
 if t=='singbox':
  doc=json.loads(text);excluded={'direct','block','dns','selector','urltest'}
  return sum(x.get('type') not in excluded and bool(x.get('server')) for x in doc.get('outbounds',[]))+sum(x.get('type')=='wireguard' for x in doc.get('endpoints',[]))
 rows=decode64(text.strip()).splitlines();assert all(re.match(r'^[a-z0-9]+://',x,re.I) for x in rows)
 return len(rows)

def matrix_case(t,v):
 src={'ssr':SSR,'v2ray':VM,'vless':VL,'hysteria2':HY,'trojan':TR}.get(t,SS)
 text=make(recipe(t,src,v));assert count_output(t,text)==1

def capabilities():
 status,mime,raw=request('/healthz?capabilities=1');assert status==200 and mime=='application/json'
 d=json.loads(raw);assert str(d.get('backend','')).lower()=='omnisub'
 assert isinstance(d.get('version'),str) and d['version']
 assert set(d['targets']) == {t if v is None else f'{t}&ver={v}' for t,v in CHOICES}
 assert set(d['options']) == {'list','sort','append_type'}

def diagnose():
 status,mime,raw=request('/api/links',recipe(action='diagnose'));assert status==200 and mime=='application/json'
 d=json.loads(raw);assert d.get('status')=='ok' and d.get('count')==1
 assert not any(k in d for k in ('path','token','link'))
 assert b'/s/' not in raw and b'synthetic-password' not in raw

def options():
 text=make(recipe(src=VM+'\n'+SS,options={'sort':True,'append_type':True}))
 assert count_output('clash',text)==2
 assert text.index('Synthetic-SS') < text.index('Synthetic-VM')
 # append_type must affect emitted names, rather than merely accept options.
 assert re.search(r'name\s*:[^\n]*\[(?:SS|VMess|VMESS)\]',text,re.I) or re.search(r'name\s*:[^\n]*(?:SS|VMess)\s*\)',text,re.I)

def rejected(d):
 status,mime,raw=request('/api/links',d);assert status in (400,422) and mime=='application/json'
 doc=json.loads(raw);assert isinstance(doc.get('error'),str) and not any(k in doc for k in ('path','token','link'))

def count_and_validate_hy2(t):
 text=make(recipe(t,HY))
 assert count_output(t,text)==1
 if t in ('v2rayn','v2rayng'):
  link=urlsplit(decode64(text.strip()).strip())
  assert link.netloc=='hysteria2'
  assert json.loads(decode64(link.path[1:]))['Password']=='synthetic-password'
 else:
  assert 'synthetic-password' in text

check('capabilities',capabilities)
check('diagnose-without-token',diagnose)
check('clash-sort-and-append-type',options)
check('unknown-option-rejected',lambda:rejected(recipe(options={'unrecognized_option':True})))
check('partial-node-loss-rejected',lambda:rejected(recipe('ss',SS+'\n'+VL)))
check('Surge5-VLESS-rejected',lambda:rejected(recipe('surge',VL,5)))
def surge6_vless():
 text=make(recipe('surge',VL,6));assert count_output('surge',text)==1 and 'vless' in text.lower()
check('Surge6-VLESS',surge6_vless)
if not a.api_only:
 for t,v in CHOICES:check('client-'+t+('-v'+str(v) if v else ''),lambda t=t,v=v:matrix_case(t,v))
 for t in ('singbox','loon','v2rayn','v2rayng'):
  check(t+'-Hysteria2',lambda t=t:count_and_validate_hy2(t))
print('RESULT',sum(results),'passed;',len(results)-sum(results),'failed',flush=True)
sys.exit(0 if all(results) else 1)
