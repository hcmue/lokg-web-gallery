"""Build optional static gallery listing from whatever HTML pages exist.
Use after expand_to_150.py. This file never changes the YAML catalog.
"""
from pathlib import Path
import json
root=Path(__file__).resolve().parents[1]
ids=sorted(p.stem for p in (root/'docs/pages').glob('WEB-*.html'))
assert len(ids)==150,f'Expected 150 pages, found {len(ids)}'
labels={'ECO':'Th\u01b0\u01a1ng m\u1ea1i \u0111i\u1ec7n t\u1eed','EDU':'Gi\u00e1o d\u1ee5c','BUS':'Doanh nghi\u1ec7p',
        'NEW':'Tin t\u1ee9c / Blog','LAN':'Landing page','DAS':'Dashboard / Bi\u1ec3u m\u1eabu'}
js='const ids='+json.dumps(ids,ensure_ascii=False)+';\nconst names='+json.dumps(labels,ensure_ascii=False)+';\n'+'''const grid=document.querySelector('#grid');if(grid)for(const id of ids){
const a=document.createElement('a');a.className='card';a.href='pages/'+id+'.html';a.target='_blank';a.rel='noopener';
const img=document.createElement('img');img.src='previews/'+id+'.webp';img.alt='Xem truoc '+id;img.loading='lazy';
const body=document.createElement('div');body.className='body';
const h=document.createElement('b');h.textContent=id;const s=document.createElement('small');s.textContent=names[id.split('-')[1]]||'Web UI';
body.append(h,s);a.append(img,body);grid.append(a);}
'''
(root/'docs/catalog.js').write_text(js,encoding='utf-8')
print(f'Updated optional catalogue for {len(ids)} pages')
