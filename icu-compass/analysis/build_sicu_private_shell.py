"""Bundle the PR's visual layer into the existing private assets (no new API routes).
Run after build_private_shared_shell.py. Idempotent. Does not load patient data.
"""
from pathlib import Path
import base64, json
from datetime import datetime, timezone
ROOT=Path(__file__).resolve().parents[1]
UI=ROOT/'static/sicu-ui'
JS_MARK='\n/* SICU_PRIVATE_UI_START */\n'
CSS_MARK='\n/* SICU_PRIVATE_CSS_START */\n'
def bundle(root=ROOT):
    assets={key:'data:image/svg+xml;base64,'+base64.b64encode((UI/'vendor'/file).read_bytes()).decode() for key,file in [('bed','bed-topview.svg'),('empty','bed-topview-empty.svg'),('logo','logo-mark.svg')]}
    staff=(UI/'vendor/staff-visuals.js').read_text()
    spatial=(UI/'vendor/spatial-symbols.js').read_text().replace('root.SpatialSymbols = api','root.SICUSpatialSymbols = api')
    controller=root/'static/shared-clinical-controller.js'
    controller.write_text(controller.read_text().split(JS_MARK)[0]+JS_MARK+'const SICU_UPDATED_AT='+json.dumps(datetime.now(timezone.utc).isoformat(timespec='seconds'))+';\n'+'const SICU_ASSETS='+json.dumps(assets)+';\n'+staff+'\n'+spatial+'\n'+(UI/'adapter.js').read_text())
    css=root/'static/shared-clinical.css'
    css.write_text(css.read_text().split(CSS_MARK)[0]+CSS_MARK+(UI/'presentation.css').read_text())
    print('SICU LINK visuals bundled; clinical APIs and original record controller preserved.')
if __name__=='__main__': bundle()
