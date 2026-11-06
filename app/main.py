"""LOKG-IR links-only educational catalog; GitHub Pages UI + Render FastAPI."""
from __future__ import annotations
import os,time
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request, Depends, HTTPException, Query
from fastapi.responses import FileResponse, PlainTextResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from .config import get_settings, ROOT
from .catalog import Catalog
from .search import SearchIndex, item_output
from .auth import Auth,COOKIE,TTL
from .analytics import Analytics

cfg=get_settings()

@asynccontextmanager
async def lifespan(app:FastAPI):
    if cfg.production:
        if len(cfg.admin_password)<16 or len(cfg.session_secret)<32:
            raise RuntimeError('APP_ENV=production requires strong ADMIN_PASSWORD and SESSION_SECRET.')
        if cfg.catalog_backend!='github':
            raise RuntimeError('Render Free needs CATALOG_BACKEND=github; local files will be lost on restart.')
    if cfg.analytics_enabled and len(cfg.analytics_secret)<32:
        raise RuntimeError('ANALYTICS_ENABLED requires a stable ANALYTICS_SECRET of at least 32 characters')
    if cfg.catalog_backend=='github':
        if not cfg.github_repository or '/' not in cfg.github_repository or not cfg.github_token:
            raise RuntimeError('Set GITHUB_REPOSITORY and GITHUB_TOKEN for GitHub catalog persistence.')
    app.state.catalog=Catalog(cfg)
    app.state.index=SearchIndex(app.state.catalog.all())
    app.state.auth=Auth(cfg)
    app.state.analytics=Analytics(cfg)
    yield

app=FastAPI(title='LOKG-IR | Thư viện giao diện Web',version='3.1.0',
            docs_url='/api/docs',redoc_url=None,lifespan=lifespan)
# GitHub Pages and Render have different origins. Only grant cross-origin browser
# access to the explicitly configured HCMUE Pages origin (no admin credentials).
app.add_middleware(
    CORSMiddleware,
    allow_origins=[cfg.public_frontend_origin],
    allow_methods=['GET', 'POST'],
    allow_headers=['Content-Type'],
    allow_credentials=False,
    max_age=3600,
)
app.mount('/static',StaticFiles(directory=ROOT/'app'/'static'),name='static')

@app.middleware('http')
async def set_security_headers(request:Request,call_next):
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='strict-origin-when-cross-origin'
    response.headers['X-Frame-Options']='DENY'
    response.headers['Content-Security-Policy']=(
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data: https://*.github.io; connect-src 'self'; "
        "object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
    if request.url.path.startswith(('/api/admin','/api/auth')):
        response.headers['Cache-Control']='no-store'
    return response

@app.get('/',include_in_schema=False)
def home():return FileResponse(ROOT/'app'/'static'/'student.html',media_type='text/html')

@app.get('/admin',include_in_schema=False)
def teacher():return FileResponse(ROOT/'app'/'static'/'admin.html',media_type='text/html')

def store(request:Request):return request.app.state.catalog

def index(request:Request):return request.app.state.index

def analytics(request:Request):return request.app.state.analytics

def admin(request:Request):return request.app.state.auth.require(request)

@app.get('/api/health')
def health(catalog:Catalog=Depends(store),idx:SearchIndex=Depends(index)):
    return {'ok':True,'items':len(catalog.all()),'backend':cfg.catalog_backend,'analytics_enabled':cfg.analytics_enabled,'engine':'lokg-miwai-core-keyword-adaptation'}

@app.get('/api/meta')
def meta(catalog:Catalog=Depends(store),idx:SearchIndex=Depends(index)):
    return {'total':len(catalog.all()),'engine':'LOKG-IR MIWAI core with teacher-entered keywords',
            'modes':[{'id':'lokg','label':'LOKG-IR (mặc định)'},
                     {'id':'bm25','label':'BM25 từ khóa'},{'id':'vector','label':'TF-IDF văn bản'}],
            'notes':'Hệ thống không phân tích trực tiếp hình ảnh hoặc HTML ở URL.'}

@app.get('/api/lokg/status')
def lokg_status(idx:SearchIndex=Depends(index)):
    return idx.lokg.status()

@app.get('/api/search')
def search(request:Request,query:str=Query('',max_length=300),mode:str='lokg',
           limit:int=Query(24,ge=1,le=60),offset:int=Query(0,ge=0),
           idx:SearchIndex=Depends(index),stats:Analytics=Depends(analytics)):
    started=time.perf_counter()
    try:rows,total=idx.search(query,mode,limit,offset)
    except ValueError as e:raise HTTPException(422,str(e))
    latency=round((time.perf_counter()-started)*1000,2)
    try:stats.record_search(request,query,mode,total,latency,offset)
    except Exception:
        import logging
        logging.getLogger(__name__).exception('Analytics search write failed')
    return {'query':query,'mode':mode,'count':len(rows),'total':total,'offset':offset,
            'latency_ms':latency,'results':rows}

@app.get('/api/items/{item_id}')
def get_item(item_id:str,catalog:Catalog=Depends(store)):
    item=catalog.get(item_id)
    if not item:raise HTTPException(404,'Không tìm thấy học liệu.')
    return item_output(item)

@app.get('/api/items/{item_id}/markdown',response_class=PlainTextResponse)
def markdown(item_id:str,catalog:Catalog=Depends(store)):
    return catalog.export_markdown(item_id)

class LoginBody(BaseModel):
    password:str=Field(min_length=1,max_length=500)

@app.post('/api/auth/login')
def login(body:LoginBody,request:Request):
    token=request.app.state.auth.login(body.password,request.client.host if request.client else 'unknown')
    resp=JSONResponse({'ok':True})
    resp.set_cookie(COOKIE,token,max_age=TTL,httponly=True,secure=cfg.production,samesite='strict',path='/')
    return resp

@app.post('/api/auth/logout')
def logout():
    resp=JSONResponse({'ok':True})
    resp.delete_cookie(COOKIE,path='/')
    return resp

class LinkBody(BaseModel):
    page_url:str=Field(min_length=10,max_length=1000)
    keywords:str=Field(min_length=2,max_length=2000)

@app.get('/api/admin/me')
def admin_me(_:bool=Depends(admin)):
    return {'authenticated':True,'role':'teacher'}

@app.get('/api/admin/items')
def list_items(_:bool=Depends(admin),catalog:Catalog=Depends(store)):
    return {'items':[item_output(x) for x in sorted(catalog.all(),key=lambda r:r['created_at'],reverse=True)]}

@app.post('/api/admin/items',status_code=201)
def add_item(body:LinkBody,_:bool=Depends(admin),catalog:Catalog=Depends(store),idx:SearchIndex=Depends(index)):
    obj=catalog.create(body.page_url,body.keywords)
    idx.rebuild(catalog.all())
    return {'ok':True,'item':item_output(obj)}

@app.put('/api/admin/items/{item_id}')
def update_item(item_id:str,body:LinkBody,_:bool=Depends(admin),catalog:Catalog=Depends(store),idx:SearchIndex=Depends(index)):
    obj=catalog.update(item_id,body.page_url,body.keywords)
    idx.rebuild(catalog.all())
    return {'ok':True,'item':item_output(obj)}

@app.delete('/api/admin/items/{item_id}')
def delete_item(item_id:str,_:bool=Depends(admin),catalog:Catalog=Depends(store),idx:SearchIndex=Depends(index)):
    catalog.remove(item_id)
    idx.rebuild(catalog.all())
    return {'ok':True}

@app.post('/api/admin/refresh')
def reload_catalog(_:bool=Depends(admin),catalog:Catalog=Depends(store),idx:SearchIndex=Depends(index)):
    catalog.refresh()
    idx.rebuild(catalog.all())
    return {'ok':True,'count':len(catalog.all())}

@app.get('/api/admin/export',response_class=PlainTextResponse)
def export_yaml(_:bool=Depends(admin),catalog:Catalog=Depends(store)):
    return PlainTextResponse(catalog.export_yaml(),media_type='text/yaml; charset=utf-8',
                             headers={'Content-Disposition':'attachment; filename="lokg-catalog.yaml"'})


# Privacy-minimized usage statistics. Visits are registered by frontend JS, not bot/API health checks.
def check_public_event_origin(request:Request):
    """Permit analytics POSTs only from this Render service or the Pages frontend.

    CORS is a browser boundary, not an authentication/rate-limit mechanism; this
    validation prevents ordinary cross-site form/JS events. No secret in JS.
    """
    from urllib.parse import urlparse
    origin=request.headers.get('origin','').rstrip('/')
    same_origin=False
    if origin:
        parsed=urlparse(origin)
        same_origin=(parsed.scheme in ('http','https')
                     and parsed.netloc==request.headers.get('host',''))
        if not (same_origin or origin==cfg.public_frontend_origin):
            raise HTTPException(403,'Không cho phép ghi sự kiện từ nguồn khác.')
    fetch_site=request.headers.get('sec-fetch-site','')
    if fetch_site in ('cross-site','same-site') and origin!=cfg.public_frontend_origin:
        raise HTTPException(403,'Không cho phép ghi sự kiện từ trang ngoài.')

class VisitBody(BaseModel):
    # Anonymous random browser ID generated on GitHub Pages; HMAC-hashed by day.
    # Never use student account IDs, emails, IPs or any personal identifier.
    visitor_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')

@app.post('/api/analytics/visit')
def analytics_visit(request:Request,body:VisitBody|None=None,stats:Analytics=Depends(analytics)):
    check_public_event_origin(request)
    response=JSONResponse({'ok':True,'enabled':stats.enabled})
    if not stats.enabled:return response
    if request.headers.get('origin','').rstrip('/')==cfg.public_frontend_origin:
        # Do NOT set third-party cookies: they are unreliable from GitHub Pages.
        visitor_id=body.visitor_id if body is not None else None
    else:
        visitor_id=stats.set_visitor_cookie(request,response)
    stats.record_visit(visitor_id)
    response.headers['Cache-Control']='no-store'
    return response

class ClickBody(BaseModel):
    item_id:str=Field(min_length=1,max_length=64)

@app.post('/api/analytics/click')
def analytics_click(body:ClickBody,request:Request,stats:Analytics=Depends(analytics),catalog:Catalog=Depends(store)):
    check_public_event_origin(request)
    if not catalog.get(body.item_id):raise HTTPException(404,'Học liệu không tồn tại.')
    try:stats.record_click(request,body.item_id)
    except Exception:
        import logging
        logging.getLogger(__name__).exception('Analytics click write failed')
    return {'ok':True,'enabled':stats.enabled}

@app.get('/api/stats/public')
def analytics_public(stats:Analytics=Depends(analytics)):
    return JSONResponse(stats.public(),headers={'Cache-Control':'no-store'})

@app.get('/api/admin/stats')
def analytics_admin(days:int=Query(30,ge=1,le=90),_:bool=Depends(admin),stats:Analytics=Depends(analytics)):
    return JSONResponse(stats.admin_report(days),headers={'Cache-Control':'no-store'})

@app.get('/api/admin/stats.csv')
def analytics_admin_csv(days:int=Query(30,ge=1,le=90),_:bool=Depends(admin),stats:Analytics=Depends(analytics)):
    return Response(stats.report_csv(days),media_type='text/csv; charset=utf-8',
        headers={'Content-Disposition':'attachment; filename="lokg-usage-stats.csv"','Cache-Control':'no-store'})

@app.get('/privacy',include_in_schema=False)
def privacy():
    return FileResponse(ROOT/'app'/'static'/'privacy.html',media_type='text/html')
