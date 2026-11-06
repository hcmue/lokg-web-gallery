from __future__ import annotations
import importlib
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('APP_ENV','development')
    monkeypatch.setenv('CATALOG_BACKEND','local')
    monkeypatch.setenv('CATALOG_PATH',str(tmp_path/'catalog.yaml'))
    monkeypatch.setenv('ADMIN_PASSWORD','TestOnlyStrongPassword12345!')
    monkeypatch.setenv('SESSION_SECRET','TestOnlySecretKeyWithMoreThan32Characters!!!!')
    import app.main as main
    importlib.reload(main)
    with TestClient(main.app) as test:
        yield test, tmp_path/'catalog.yaml'

def login(client):
    response=client.post('/api/auth/login',json={'password':'TestOnlyStrongPassword12345!'})
    assert response.status_code==200

def item(url='https://example.github.io/web-ui/pages/sample-01.html', keywords='thương mại điện tử, navbar, sản phẩm, grid'):
    return {'page_url':url,'keywords':keywords}

def test_root_and_health(client):
    api,_=client
    assert api.get('/').status_code==200
    assert api.get('/admin').status_code==200
    assert api.get('/api/health').json()['items']==0
    assert api.get('/api/search').json()['total']==0

def test_admin_auth_required(client):
    api,_=client
    assert api.post('/api/admin/items',json=item()).status_code==401
    assert api.get('/api/admin/items').status_code==401
    assert api.get('/api/admin/export').status_code==401
    assert api.get('/api/auth/login').status_code==405
    assert api.post('/api/auth/login',json={'password':'wrong'}).status_code==401

def test_create_search_yaml_and_index(client):
    api,path=client;login(api)
    r=api.post('/api/admin/items',json=item())
    assert r.status_code==201,r.text
    saved=r.json()['item'];item_id=saved['id']
    assert path.is_file()
    text=path.read_text(encoding='utf-8')
    assert 'page_url:' in text and 'thương mại điện tử' in text
    q=api.get('/api/search',params={'query':'thương mại điện tử navbar','mode':'lokg'}).json()
    assert q['total']==1 and q['results'][0]['id']==item_id
    assert api.get('/api/items/'+item_id).json()['page_url']==item()['page_url']
    md=api.get('/api/items/'+item_id+'/markdown').text
    assert md.startswith('---\n') and 'tags:' in md
    status=api.get('/api/lokg/status').json()
    assert status['images']==1 and status['concepts']>1
    for mode in ('bm25','vector'):
        assert api.get('/api/search',params={'query':'navbar','mode':mode}).json()['total']==1

def test_update_delete_reindex(client):
    api,_=client;login(api)
    item_id=api.post('/api/admin/items',json=item()).json()['item']['id']
    replacement=item(url='https://example.github.io/web-ui/pages/sample-02.html',keywords='giáo dục, khóa học, sidebar')
    assert api.put('/api/admin/items/'+item_id,json=replacement).status_code==200
    assert api.get('/api/search',params={'query':'giáo dục khóa học','mode':'lokg'}).json()['total']==1
    assert api.get('/api/search',params={'query':'thương mại điện tử','mode':'bm25'}).json()['total']==0
    assert api.delete('/api/admin/items/'+item_id).status_code==200
    assert api.get('/api/health').json()['items']==0
    assert api.get('/api/search',params={'query':'khóa học'}).json()['total']==0

def test_validation_duplicate(client):
    api,_=client;login(api)
    assert api.post('/api/admin/items',json=item('http://example.github.io/demo')).status_code==422
    assert api.post('/api/admin/items',json=item('https://example.com/demo')).status_code==422
    assert api.post('/api/admin/items',json=item('https://localhost/internal')).status_code==422
    assert api.post('/api/admin/items',json=item('https://example.github.io/web-ui/pages/test.html',keywords='')).status_code==422
    assert api.post('/api/admin/items',json=item()).status_code==201
    assert api.post('/api/admin/items',json=item()).status_code==409
    assert api.get('/api/search',params={'mode':'invalid'}).status_code==422

def test_export_reload(client):
    api,path=client;login(api)
    api.post('/api/admin/items',json=item())
    exported=api.get('/api/admin/export')
    assert exported.status_code==200 and 'items:' in exported.text
    assert 'attachment;' in exported.headers['content-disposition']
    count=api.post('/api/admin/refresh').json()['count']
    assert count==1

def test_graph_bridge_links(client):
    api,_=client;login(api)
    for ix in range(2):
        payload=item(f'https://example.github.io/gallery/pages/WEB-ECO-00{ix+1}.html',
                     'thương mại điện tử, navbar, bộ lọc, product grid')
        assert api.post('/api/admin/items',json=payload).status_code==201
    rows=api.get('/api/admin/items').json()['items']
    assert len(rows)==2 and any(row['links'] for row in rows)
    q=api.get('/api/search',params={'query':'navbar bộ lọc','mode':'lokg'}).json()
    assert q['total']==2

def test_gallery_files():
    root=Path(__file__).resolve().parents[1]
    html=list((root/'docs'/'pages').glob('*.html'))
    previews=list((root/'docs'/'previews').glob('*.webp'))
    assert len(html)==len(previews)==72
    assert {x.stem for x in html}=={x.stem for x in previews}
