"""Apply a presentation-only bundle in the authenticated Pod; no restart or pool edits."""
from pathlib import Path
import base64,gzip,json,hashlib,urllib.request,os,time
ROOT=Path('/home/khdp-user/workspace/icu-runtime/kmimic-board-v1')
W=ROOT.parent
incoming=json.loads(gzip.decompress(base64.b64decode(Path(W/'sicu-visual-bundle.b64').read_text())))
FILES={'shared-clinical-controller.js':'\n/* SICU_PRIVATE_UI_START */\n','shared-clinical.css':'\n/* SICU_PRIVATE_CSS_START */\n'}
def get(path):
 with urllib.request.urlopen('http://127.0.0.1:8007/'+path,timeout=30) as r:return r.read()
api_before=hashlib.sha256(get('api/cases')).hexdigest()
backup=W/('sicu-ui-backup-'+time.strftime('%Y%m%d-%H%M%S'));backup.mkdir(mode=0o700)
original={}
for name,marker in FILES.items():
 p=ROOT/'static'/name;original[name]=p.read_bytes();(backup/name).write_bytes(original[name])
 content=p.read_text().split(marker)[0]+marker+incoming[name]
 temp=p.with_suffix(p.suffix+'.sicu-tmp');temp.write_text(content);os.replace(temp,p)
try:
 for name in FILES:assert get(name)==(ROOT/'static'/name).read_bytes()
 assert api_before==hashlib.sha256(get('api/cases')).hexdigest(),'Patient payload changed'
 assert b'SICU_ASSETS' in get('shared-clinical-controller.js')
except Exception:
 for name,raw in original.items():(ROOT/'static'/name).write_bytes(raw)
 raise
receipt={'ui':'SICU LINK private integration v1','backup':str(backup),'clinical_payload_unchanged':True,'files':{name:hashlib.sha256((ROOT/'static'/name).read_bytes()).hexdigest() for name in FILES}}
(W/'sicu-ui-deploy-receipt.json').write_text(json.dumps(receipt,indent=2))
print(json.dumps(receipt,indent=2))
