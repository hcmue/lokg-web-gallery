"""Generate a valid YAML link catalog using hosted GitHub Pages URLs.

Run after you know your real GitHub Pages address, then commit data/catalog.yaml.
Never run the script on a deployed app automatically; it is an explicit prep step.
"""
import argparse, json, sys, yaml
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
from app.catalog import make_item
from app.config import get_settings
p=argparse.ArgumentParser()
p.add_argument('--base-url',required=True,help='e.g. https://username.github.io/lokg-web-gallery')
p.add_argument('--out',default='data/catalog.yaml')
args=p.parse_args()
base=args.base_url.rstrip('/')
if not base.startswith('https://') or '.github.io' not in base:
    raise SystemExit('Provide your REAL GitHub Pages HTTPS base URL')
source=root/'seed_original_metadata.jsonl'
if not source.is_file():raise SystemExit('Missing seed_original_metadata.jsonl')
items=[]
for line in source.read_text(encoding='utf8').splitlines():
    row=json.loads(line)
    url=f'{base}/pages/{row["id"]}.html'
    # Teacher-provided keywords only: no claims of automatic visual recognition.
    kws=[row.get('category_vi','')]+row.get('components',[])[:7]+row.get('tags',[])[:9]
    it=make_item(url,kws,get_settings(),item_id=row['id'])
    it['title']=row.get('title') or it['title']
    it['source']='synthetic_gallery_seed'
    it['verified']=False
    items.append(it)
output=root/args.out
output.parent.mkdir(exist_ok=True,parents=True)
keys=('id','page_url','title','description','tags','source','created_at','updated_at')
content={'schema_version':1,'items':[{k:it[k] for k in keys} for it in items]}
output.write_text(yaml.safe_dump(content,allow_unicode=True,sort_keys=False,width=110),encoding='utf-8')
print(f'Created {output} with {len(items)} GitHub Pages links; commit and push it.')
