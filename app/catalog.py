"""Small YAML catalog of *links* (no web screenshots or HTML files on Render).

Local backend: atomic catalog.yaml write for development or paid persistent disk.
GitHub backend: one YAML file committed via the GitHub Contents API; suitable for
Render Free because no runtime filesystem writes are needed for persistence.
"""
from __future__ import annotations
import base64, os, re, tempfile, threading, uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from collections import Counter

import httpx
import yaml
from fastapi import HTTPException
from .config import Settings
from .search_aliases import detect, normalize

ID_RE=re.compile(r'^[A-Za-z0-9-]{3,64}$')
MAX_ITEMS=2500

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def require_github_pages(raw: str, cfg:Settings) -> str:
    value=str(raw or '').strip()
    if len(value)>1000:
        raise HTTPException(422,'Đường dẫn quá dài (tối đa 1.000 ký tự).')
    try:
        p=urlparse(value)
    except ValueError:
        raise HTTPException(422,'URL không hợp lệ.')
    try:
        port=p.port
    except ValueError:
        raise HTTPException(422,'Cổng URL không hợp lệ.')
    if (p.scheme!='https' or not p.hostname or p.username or p.password
            or port not in (None,443) or not p.path or p.hostname=='github.io'):
        raise HTTPException(422,'Hãy nhập đường dẫn HTTPS đầy đủ của một giao diện trên GitHub Pages.')
    host=p.hostname.lower().rstrip('.')
    rules=[r.strip() for r in cfg.allowed_page_hosts.split(',') if r.strip()]
    valid=any((host.endswith(rule[1:]) and host!=rule[2:]) if rule.startswith('*.')
              else host==rule for rule in rules)
    if not valid:
        raise HTTPException(422,'Tên miền không nằm trong danh sách GitHub Pages được phép.')
    # Do not fetch the URL from the server. This prevents SSRF and keeps writes fast.
    return value


def parse_keywords(raw: str | list[str]) -> list[str]:
    if isinstance(raw,list): chunks=raw
    else: chunks=re.split(r'[,;\n]+',str(raw or ''))
    result=[]
    seen=set()
    for t in chunks:
        tag=str(t).strip().strip('#')
        key=normalize(tag)
        if not tag:continue
        if len(tag)>90 or len(tag)<2:
            raise HTTPException(422,'Mỗi từ khóa phải có 2–90 ký tự.')
        if key and key not in seen:
            result.append(tag)
            seen.add(key)
    if not result or len(result)>25:
        raise HTTPException(422,'Nhập 1–25 từ khóa, ngăn cách bằng dấu phẩy.')
    return result


def infer_category(tags: list[str]) -> str:
    cats,_,_=detect(' '.join(tags))
    for c in ('ecommerce','education','business','news','landing','dashboard'):
        if c in cats:return c
    return 'other'


def infer_components(tags:list[str]) -> list[str]:
    _,comps,_=detect(' '.join(tags))
    return sorted(comps)


def derive_title(url:str,tags:list[str]) -> str:
    # Prefer the teacher's first descriptive keyword; no HTML scraping.
    candidate=tags[0].strip() if tags else ''
    if len(candidate)>=4:
        return candidate[:100].capitalize()
    part=Path(urlparse(url).path).stem.replace('-',' ').replace('_',' ').strip()
    return (part or 'Mẫu giao diện Web')[:100]


def derive_preview_url(url:str) -> str | None:
    """Only auto-map /pages/FOO.html -> /previews/FOO.webp, no fetch."""
    p=urlparse(url)
    if '/pages/' not in p.path or not p.path.lower().endswith('.html'):
        return None
    return f'{p.scheme}://{p.netloc}{p.path.replace("/pages/","/previews/")[:-5]}.webp'


def make_item(page_url:str,keywords:list[str],cfg:Settings,item_id:str|None=None)->dict:
    url=require_github_pages(page_url,cfg)
    tags=parse_keywords(keywords)
    when=utc_now()
    return {'id':item_id or 'WEB-'+uuid.uuid4().hex[:10].upper(),
            'page_url':url,
            'title':derive_title(url,tags),
            'description':'Mẫu giao diện Web: '+', '.join(tags[:8]),
            'category':infer_category(tags),
            'tags':tags,
            'components':infer_components(tags),
            'relations':[],   # No spatial relations are inferred from keywords.
            'layout':'',
            'links':[],
            'source':'teacher_keywords',
            'verified':False,
            'created_at':when,'updated_at':when}


def enrich(items:list[dict]) -> list[dict]:
    """Build lightweight wiki-links by non-ubiquitous teacher-supplied concepts."""
    cleaned=[]
    for entry in items:
        d=dict(entry)
        d['tags']=parse_keywords(d.get('tags',[]))
        # Keep explicitly annotated components/layout from the teaching catalog.
        # Existing 72 records without structured annotations still work unchanged.
        provided=[str(c).strip() for c in (d.get('components') or []) if str(c).strip()]
        d['components']=sorted(set(infer_components(d['tags']))|set(provided))
        d['category']=d.get('category') or infer_category(d['tags'])
        d['layout']=str(d.get('layout') or '')
        d['relations']=d.get('relations') or []
        d['links']=[]
        cleaned.append(d)
    df=Counter()
    for x in cleaned:
        df.update(set(normalize(k) for k in x['tags']))
    rare=[]
    for x in cleaned:
        rare.append({normalize(k) for k in x['tags'] if df[normalize(k)]<max(3,len(cleaned)*.45)})
    for i,x in enumerate(cleaned):
        similarities=[]
        for j,y in enumerate(cleaned):
            if i==j:continue
            score=len(rare[i]&rare[j])
            if score>0:similarities.append((score,y['id']))
        similarities.sort(key=lambda t:(-t[0],t[1]))
        x['links']=[id for _,id in similarities[:5]]
    return cleaned


class Catalog:
    def __init__(self, cfg:Settings):
        self.cfg=cfg
        self.lock=threading.RLock()
        self.sha=None
        self._items=[]
        self.refresh()

    def _github_headers(self):
        return {'Authorization':f'Bearer {self.cfg.github_token}',
                'Accept':'application/vnd.github+json',
                'X-GitHub-Api-Version':'2022-11-28'}

    def _github_endpoint(self):
        return f'https://api.github.com/repos/{self.cfg.github_repository}/contents/{self.cfg.github_catalog_path}'

    def _read_raw(self) -> str:
        if self.cfg.catalog_backend=='local':
            return self.cfg.catalog_path.read_text(encoding='utf-8') if self.cfg.catalog_path.exists() else 'schema_version: 1\nitems: []\n'
        if self.cfg.catalog_backend!='github':
            raise RuntimeError('CATALOG_BACKEND must be local or github')
        r=httpx.get(self._github_endpoint(),params={'ref':self.cfg.github_branch},
                    headers=self._github_headers(), timeout=15.0)
        if r.status_code==404:
            self.sha=None
            return 'schema_version: 1\nitems: []\n'
        if r.status_code!=200:
            raise RuntimeError(f'GitHub catalog read failed: HTTP {r.status_code}')
        payload=r.json()
        self.sha=payload.get('sha')
        if payload.get('encoding')!='base64':
            raise RuntimeError('Expected base64 content from GitHub.')
        return base64.b64decode(payload['content']).decode('utf-8')

    def _write_raw(self,content:str,commit_message:str):
        if self.cfg.catalog_backend=='local':
            path=self.cfg.catalog_path
            path.parent.mkdir(parents=True,exist_ok=True)
            with tempfile.NamedTemporaryFile(mode='w',suffix='.tmp',dir=path.parent,
                                             delete=False,encoding='utf-8') as tmp:
                tmp.write(content)
                temp=tmp.name
            os.replace(temp,path)
            return
        payload={'message':commit_message,'content':base64.b64encode(content.encode('utf-8')).decode(),
                 'branch':self.cfg.github_branch}
        if self.sha:payload['sha']=self.sha
        r=httpx.put(self._github_endpoint(),json=payload,headers=self._github_headers(),timeout=20.0)
        if r.status_code in (409,422):
            # Do not overwrite concurrent changes from another admin/Git commit.
            raise HTTPException(409,'Danh mục đã được thay đổi ở GitHub. Vui lòng tải lại và thử lại.')
        if r.status_code not in (200,201):
            raise HTTPException(502,'Không lưu được danh mục lên GitHub. Kiểm tra token, quyền ghi hoặc branch.')
        self.sha=r.json()['content']['sha']

    def refresh(self):
        with self.lock:
            raw=self._read_raw()
            content=yaml.safe_load(raw) or {}
            if not isinstance(content,dict) or not isinstance(content.get('items',[]),list):
                raise RuntimeError('Invalid catalog.yaml')
            items=content.get('items',[])
            if len(items)>MAX_ITEMS:raise RuntimeError('Catalog exceeds maximum entry count.')
            ids=set()
            for it in items:
                if not isinstance(it,dict) or not ID_RE.fullmatch(str(it.get('id',''))):
                    raise RuntimeError('Invalid item ID in catalog.yaml')
                if it['id'] in ids:raise RuntimeError('Duplicate ID in catalog.yaml')
                ids.add(it['id'])
                require_github_pages(it.get('page_url',''),self.cfg)
                parse_keywords(it.get('tags',[]))
            self._items=enrich(items)

    def all(self):
        with self.lock:
            return [x.copy() for x in self._items]

    def get(self,item_id:str):
        with self.lock:
            return next((x.copy() for x in self._items if x['id']==item_id),None)

    def _persist(self,items:list[dict],message:str):
        # Preserve teacher-supplied structured fields on all catalog CRUD writes.
        # Without this, adding a single URL would delete existing layout/relations.
        compact=[]
        for d in items:
            keep=('id','page_url','title','description','tags','category','components',
                  'layout','relations','source','verified','created_at','updated_at')
            compact.append({k:d[k] for k in keep if k in d})
        text=yaml.safe_dump({'schema_version':1,'items':compact},allow_unicode=True,
                            sort_keys=False,width=110)
        self._write_raw(text,message)
        self._items=enrich(compact)

    def create(self,url:str,keywords:str):
        with self.lock:
            new=make_item(url,keywords,self.cfg)
            if len(self._items)>=MAX_ITEMS:raise HTTPException(422,'Kho học liệu đã đạt giới hạn.')
            if any(x['page_url'].rstrip('/')==new['page_url'].rstrip('/') for x in self._items):
                raise HTTPException(409,'Đường dẫn này đã có trong kho học liệu.')
            self._persist(self._items+[new],f'Add Web UI link {new["id"]}')
            return self.get(new['id'])

    def update(self,item_id:str,url:str,keywords:str):
        with self.lock:
            old=self.get(item_id)
            if not old:raise HTTPException(404,'Không tìm thấy học liệu.')
            updated=make_item(url,keywords,self.cfg,item_id=item_id)
            updated['created_at']=old['created_at']
            if any(x['id']!=item_id and x['page_url'].rstrip('/')==updated['page_url'].rstrip('/') for x in self._items):
                raise HTTPException(409,'Đường dẫn này đã có trong kho học liệu.')
            self._persist([updated if x['id']==item_id else x for x in self._items],f'Update Web UI link {item_id}')
            return self.get(item_id)

    def remove(self,item_id:str):
        with self.lock:
            if not self.get(item_id):raise HTTPException(404,'Không tìm thấy học liệu.')
            self._persist([x for x in self._items if x['id']!=item_id],f'Remove Web UI link {item_id}')

    def export_yaml(self):
        with self.lock:
            compact=[{k:x[k] for k in ('id','page_url','title','description','tags','source','created_at','updated_at') if k in x} for x in self._items]
            return yaml.safe_dump({'schema_version':1,'items':compact},allow_unicode=True,sort_keys=False)

    def export_markdown(self,item_id:str) -> str:
        d=self.get(item_id)
        if not d:raise HTTPException(404,'Không tìm thấy học liệu.')
        data={k:d.get(k) for k in ['id','title','page_url','category','tags','components','links','source']}
        return '---\n'+yaml.safe_dump(data,allow_unicode=True,sort_keys=False)+'---\n\n'+d.get('description','')+'\n'
