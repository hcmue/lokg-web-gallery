"""Render thumbnails from actual new HTML pages using Chromium, not fake mockups.
Dependencies for development only: pip install playwright pillow
Usage: python scripts/render_150_previews.py [--force] [--chromium /path/to/chromium]
"""
from __future__ import annotations
import argparse
import io
from pathlib import Path
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--chromium',default=None)
parser.add_argument('--force',action='store_true')
args=parser.parse_args()
paths=sorted(p for p in (ROOT/'docs/pages').glob('WEB-*.html') if int(p.stem.split('-')[-1])>=13)
assert len(paths)==78,f'Expected 78 new pages, got {len(paths)}'
previews=ROOT/'docs/previews';previews.mkdir(parents=True,exist_ok=True)
with sync_playwright() as p:
    kwargs={'headless':True,'args':['--no-sandbox','--disable-dev-shm-usage']}
    if args.chromium:kwargs['executable_path']=args.chromium
    browser=p.chromium.launch(**kwargs)
    page=browser.new_page(viewport={'width':1280,'height':800},device_scale_factor=1)
    css=(ROOT/'docs/assets/sample-150.css').read_text(encoding='utf-8')
    for n,path in enumerate(paths,1):
        dest=previews/(path.stem+'.webp')
        if dest.exists() and not args.force:continue
        source=path.read_text(encoding='utf-8').replace('<link rel="stylesheet" href="../assets/sample-150.css">','<style>'+css+'</style>')
        page.set_content(source,wait_until='load',timeout=20000)
        # Use screenshot of exact HTML/CSS that students will open.
        png=page.screenshot(type='png',full_page=False,animations='disabled')
        with Image.open(io.BytesIO(png)) as im:
            im.convert('RGB').save(dest,format='WEBP',quality=78,method=5)
        if n%13==0:print(f'{n}/{len(paths)} screenshots created',flush=True)
    browser.close()
print(f'Preview files: {len(list(previews.glob("WEB-*.webp")))}')
