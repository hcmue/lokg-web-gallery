"""Build the static GitHub Pages gallery JS from the bundled 72 sample page names."""
from pathlib import Path
root=Path(__file__).resolve().parents[1]
ids=sorted(p.stem for p in (root/'docs'/'pages').glob('*.html'))
assert len(ids)==72
names={'ECO':'Thương mại điện tử','EDU':'Giáo dục','BUS':'Doanh nghiệp','NEW':'Tin tức / blog','LAN':'Landing page','DAS':'Dashboard / Biểu mẫu'}
js='''const ids='''+str(ids).replace("'",'"')+''';
const names='''+str(names).replace("'",'"')+''';
const grid=document.querySelector('#grid');for(const id of ids){
const a=document.createElement('a');a.className='card';a.href='pages/'+id+'.html';a.target='_blank';a.rel='noopener';
const img=document.createElement('img');img.src='previews/'+id+'.webp';img.alt='Xem trước '+id;img.loading='lazy';
const body=document.createElement('div');body.className='body';
const h=document.createElement('b');h.textContent=id;const s=document.createElement('small');s.textContent=names[id.split('-')[1]]||'Mẫu Web';
body.append(h,s);a.append(img,body);grid.append(a);}
'''
(root/'docs'/'catalog.js').write_text(js,encoding='utf8')
print(f'{len(ids)} gallery pages')
