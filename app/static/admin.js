'use strict';
const el=id=>document.getElementById(id),node=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=String(text);return n;};
let allItems=[],editing=null;
async function api(path,options={}){const r=await fetch(path,{credentials:'same-origin',...options});const d=await r.json().catch(()=>({}));if(!r.ok)throw Error(typeof d.detail==='string'?d.detail:'Yêu cầu thất bại');return d;}
function toggle(ok){el('loginPanel').hidden=ok;el('workspace').hidden=!ok;el('logout').hidden=!ok;if(ok){refresh();loadAnalytics();}}
async function check(){try{await api('/api/admin/me');toggle(true);}catch{toggle(false);}}
el('loginForm').addEventListener('submit',async e=>{e.preventDefault();el('loginError').textContent='';try{await api('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:el('password').value})});el('password').value='';toggle(true);}catch(e){el('loginError').textContent=e.message;}});
el('logout').addEventListener('click',async()=>{await api('/api/auth/logout',{method:'POST'}).catch(()=>{});toggle(false);});
function resetForm(){editing=null;el('itemForm').reset();el('formHeading').textContent='Thêm giao diện mới';el('saveBtn').textContent='Lưu vào kho';el('cancelBtn').hidden=true;}
function showItems(){
 const q=el('filterItems').value.trim().toLowerCase();const parent=el('items');parent.replaceChildren();
 for(const item of allItems.filter(x=>[x.page_url,...(x.tags||[])].join(' ').toLowerCase().includes(q))){
  const itemEl=node('div','itemrow');const left=node('div','itemleft');
  left.append(node('strong','',item.title));left.append(node('small','',item.page_url));
  const tags=node('div','tags');(item.tags||[]).slice(0,4).forEach(t=>tags.append(node('span','chip',t)));left.append(tags);
  const buttons=node('div','itemactions');
  const visit=node('a','subtle smallbtn','Mở ↗');visit.href=item.page_url;visit.target='_blank';visit.rel='noopener noreferrer';buttons.append(visit);
  const edit=node('button','subtle smallbtn','Sửa');edit.type='button';edit.addEventListener('click',()=>{editing=item.id;el('pageUrl').value=item.page_url;el('keywords').value=(item.tags||[]).join(', ');el('formHeading').textContent='Sửa học liệu';el('saveBtn').textContent='Lưu thay đổi';el('cancelBtn').hidden=false;el('itemForm').scrollIntoView({behavior:'smooth'});});buttons.append(edit);
  const del=node('button','danger smallbtn','Xóa');del.type='button';del.addEventListener('click',async()=>{if(!confirm('Xóa liên kết này khỏi kho học liệu? Trang GitHub Pages sẽ không bị xóa.'))return;try{await api('/api/admin/items/'+encodeURIComponent(item.id),{method:'DELETE'});if(editing===item.id)resetForm();await refresh();}catch(e){alert(e.message);}});buttons.append(del);
  itemEl.append(left,buttons);parent.append(itemEl);
 }
 if(!parent.children.length)parent.append(node('p','subcopy','Chưa có học liệu phù hợp.'));
}
async function refresh(){try{const data=await api('/api/admin/items');allItems=data.items;el('count').textContent=allItems.length;showItems();}catch(e){if(e.message.includes('đăng nhập'))toggle(false);else el('formMessage').textContent=e.message;}}
el('filterItems').addEventListener('input',showItems);el('refreshBtn').addEventListener('click',refresh);
el('cancelBtn').addEventListener('click',resetForm);
el('itemForm').addEventListener('submit',async e=>{
 e.preventDefault();const body={page_url:el('pageUrl').value.trim(),keywords:el('keywords').value.trim()};el('saveBtn').disabled=true;el('formMessage').textContent='Đang lưu YAML và lập chỉ mục…';
 try{const endpoint=editing?'/api/admin/items/'+encodeURIComponent(editing):'/api/admin/items';await api(endpoint,{method:editing?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});resetForm();el('formMessage').textContent='Đã lưu và cập nhật chỉ mục. Sinh viên có thể tìm ngay.';await refresh();}
 catch(ex){el('formMessage').textContent='Lỗi: '+ex.message;}
 finally{el('saveBtn').disabled=false;}
});
check();


async function loadAnalytics(){
 const days=Number(el('statDays')?.value||30),note=el('statsNote');
 try{
  const r=await api('/api/admin/stats?days='+days);
  el('statsCsv').href='/api/admin/stats.csv?days='+days;
  el('statsKpis').replaceChildren();el('statsQueries').replaceChildren();el('statsDaily').replaceChildren();
  if(!r.enabled){note.textContent=r.message||'Thống kê chưa được bật trên máy chủ.';return;}
  note.textContent='Số liệu lưu trong cơ sở dữ liệu, không ghi IP, theo UTC. Khách duy nhất là trình duyệt trong ngày, không phải người dùng riêng biệt.';
  const nf=new Intl.NumberFormat('vi-VN');
  const cells=[['Lượt truy cập',r.summary.visits],['Lượt tìm kiếm',r.summary.searches],['Mở giao diện',r.summary.clicks],['Không có kết quả',r.summary.no_results],['Trình duyệt hôm nay',r.summary.unique_browsers_today]];
  for(const [label,n] of cells){const card=node('div','statskpi');card.append(node('b','',nf.format(n)));card.append(node('small','',label));el('statsKpis').append(card);}
  const queries=r.top_queries||[];
  for(const q of queries){const row=node('div','statsline');row.append(node('span','',q.query));row.append(node('b','',String(q.count)));el('statsQueries').append(row);}
  if(!queries.length)el('statsQueries').append(node('p','subcopy','Chưa có từ khóa hoặc đang tắt chế độ lưu nội dung truy vấn.'));
  const rows=(r.daily||[]).filter(x=>x.visits||x.searches||x.clicks).slice(-15).reverse();
  for(const d of rows){const row=node('div','statsline');row.append(node('span','',d.date));row.append(node('b','',d.visits+' truy cập · '+d.searches+' tìm'));el('statsDaily').append(row);}
  if(!rows.length)el('statsDaily').append(node('p','subcopy','Chưa có dữ liệu.'));
 }catch(ex){note.textContent='Lỗi thống kê: '+ex.message;}
}
el('statDays')?.addEventListener('change',loadAnalytics);
el('statsRefresh')?.addEventListener('click',loadAnalytics);
