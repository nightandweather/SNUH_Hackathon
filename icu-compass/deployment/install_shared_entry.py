"""Install an idempotent presentation redirect without replacing the private UI."""
from pathlib import Path
import argparse
START='<!-- ICU_SHARED_ENTRY_START -->'
END='<!-- ICU_SHARED_ENTRY_END -->'

def inject(html, script):
    if START in html:
        before,rest=html.split(START,1)
        _,after=rest.split(END,1)
        html=before+after
    block=START+'<script>'+script+'</script>'+END
    if '<head>' not in html: raise ValueError('Expected HTML head')
    return html.replace('<head>','<head>'+block,1)

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('html');args=a.parse_args()
    file=Path(args.html);script=Path(__file__).with_name('shared-entry.js').read_text()
    file.write_text(inject(file.read_text(),script))
