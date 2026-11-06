'use strict';
const el=id=>document.getElementById(id);
let nextOffset=0,total=0,busy=false;
const LIMIT=12;
function node(tag,cls,txt){const x=document.createElement(tag);if(cls)x.className=cls;if(txt!==undefined)x.textContent=String(txt);return x;}
function imageUrl(url){try{const u=new URL(url);if(u.protocol!=='https:'||!u.hostname.endsWith('.github.io'))return null;if(!u.pathname.includes('/pages/')||!u.pathname.endsWith('.html'))return null;u.pathname=u.pathname.replace('/pages/','/previews/').replace(/\.html$/,'.webp');u.search='';u.hash='';return u.href;}catch{return null;}}
function card(item){
  const a=node('article','resultcard');
  const preview=node('div','preview');
  const imgSrc=imageUrl(item.page_url);
  if(imgSrc){const img=node('img');img.src=imgSrc;img.alt='Ảnh minh họa giao diện '+item.title;img.loading='lazy';img.addEventListener('error',()=>{img.remove();preview.append(node('span','previewfallback','WEB UI'));});preview.append(img);} else {preview.append(node('span','previewfallback','WEB UI'));}
  const label=node('span','score','Điểm '+Number(item.score||0).toFixed(3));preview.append(label);
  a.append(preview);
  const body=node('div','cardbody');
  body.append(node('div','cardeyebrow',(item.category||'other').toUpperCase()));
  body.append(node('h3','',item.title));
  const tags=node('div','tags');(item.tags||[]).slice(0,5).forEach(t=>tags.append(node('span','chip',t)));body.append(tags);
  const link=node('a','openlink','Xem giao diện ↗');link.href=item.page_url;link.target='_blank';link.rel='noopener noreferrer';link.addEventListener('click',()=>{
    if(!item.id)return;
    const payload=JSON.stringify({item_id:item.id});
    const blob=new Blob([payload],{type:'application/json'});
    if(navigator.sendBeacon)navigator.sendBeacon('/api/analytics/click',blob);
    else fetch('/api/analytics/click',{method:'POST',headers:{'Content-Type':'application/json'},body:payload,keepalive:true}).catch(()=>{});
  });body.append(link);
  a.append(body);return a;
}
async function fetchResults(reset=false){
 if(busy)return;busy=true;
 if(reset){nextOffset=0;el('cards').replaceChildren();}
 el('status').textContent='Đang truy hồi…';el('loadMore').hidden=true;
 try{
  const params=new URLSearchParams({query:el('query').value,mode:el('mode').value,limit:LIMIT,offset:nextOffset});
  const r=await fetch('/api/search?'+params.toString());const d=await r.json();if(!r.ok)throw Error(d.detail||'Lỗi API');
  for(const item of d.results)el('cards').append(card(item));
  nextOffset+=d.results.length;total=d.total;
  el('empty').hidden=nextOffset>0;
  el('status').textContent=total+' mẫu · '+d.latency_ms+' ms · '+d.mode.toUpperCase();
  el('loadMore').hidden=nextOffset>=total;
  if(reset&&el('query').value.trim())loadStats();
 }catch(e){el('status').textContent='Không thể tìm kiếm: '+e.message;}
 finally{busy=false;}
}
el('searchForm').addEventListener('submit',e=>{e.preventDefault();fetchResults(true);});
el('mode').addEventListener('change',()=>fetchResults(true));
el('loadMore').addEventListener('click',()=>fetchResults(false));
document.querySelectorAll('[data-query]').forEach(b=>b.addEventListener('click',()=>{el('query').value=b.dataset.query;fetchResults(true);}));
async function loadStats(){
  try{
    const r=await fetch('/api/stats/public',{cache:'no-store'});const d=await r.json();
    const label=el('visitStats');
    if(!d.enabled){label.textContent='Thống kê chưa bật';return;}
    const nf=new Intl.NumberFormat('vi-VN');
    label.textContent=nf.format(d.visits)+' lượt truy cập · '+nf.format(d.searches)+' lượt tìm kiếm · '+nf.format(d.unique_browsers_today)+' trình duyệt hôm nay';
  }catch{el('visitStats').textContent='Thống kê chưa sẵn sàng';}
}
async function trackVisit(){
  try{await fetch('/api/analytics/visit',{method:'POST',credentials:'same-origin'});}catch{}
  loadStats();
}
trackVisit();
fetchResults(true);
