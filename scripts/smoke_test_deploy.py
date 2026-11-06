"""Smoke-test an already deployed LOKG-IR demo without administrator credentials."""
from __future__ import annotations
import argparse
import httpx
p=argparse.ArgumentParser()
p.add_argument('--api',required=True,help='https://NAME.onrender.com')
p.add_argument('--pages',required=True,help='https://USER.github.io/REPO')
p.add_argument('--with-search',action='store_true',help='record one real search in analytics')
a=p.parse_args()
checks=[
 ('Render health',a.api.rstrip('/')+'/api/health'),
 ('Student home',a.api.rstrip('/')+'/'),
 ('Analytics public',a.api.rstrip('/')+'/api/stats/public'),
 ('GitHub Pages home',a.pages.rstrip('/')+'/'),
 ('One static sample',a.pages.rstrip('/')+'/pages/WEB-ECO-001.html'),
]
if a.with_search:
 checks.append(('Search (will count)',a.api.rstrip('/')+'/api/search?query=navbar&mode=lokg'))
failed=0
with httpx.Client(timeout=90,follow_redirects=True) as client:
 for name,url in checks:
  try:
   r=client.get(url)
   print(('PASS' if r.status_code<400 else 'FAIL'),r.status_code,name,url)
   if r.status_code>=400:failed+=1
   if name in ('Render health','Analytics public') and r.status_code==200:
    print('  ',str(r.json())[:280])
  except Exception as exc:
   failed+=1
   print('FAIL',name,url,type(exc).__name__,str(exc))
raise SystemExit(1 if failed else 0)
