"""GitHub Pages -> Render cross-origin integration tests."""
from __future__ import annotations
import importlib
from fastapi.testclient import TestClient


def test_static_page_and_config():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    docs=root/'docs'
    assert (docs/'index.html').exists()
    assert (docs/'config.js').exists()
    assert (docs/'assets'/'app.js').exists()
    assert (docs/'assets'/'styles.css').exists()
    assert len(list((docs/'pages').glob('*.html')))==72


def test_cors_and_cross_origin_analytics(tmp_path,monkeypatch):
    monkeypatch.setenv('APP_ENV','development')
    monkeypatch.setenv('CATALOG_BACKEND','local')
    monkeypatch.setenv('CATALOG_PATH',str(tmp_path/'cat.yaml'))
    monkeypatch.setenv('ANALYTICS_ENABLED','true')
    monkeypatch.setenv('DATABASE_URL',f'sqlite:///{tmp_path}/usage.db')
    monkeypatch.setenv('ANALYTICS_SECRET','cross-origin-example-secret-1234567890')
    monkeypatch.setenv('PUBLIC_FRONTEND_ORIGIN','https://hcmue.github.io')
    import app.main as m
    importlib.reload(m)
    good={'Origin':'https://hcmue.github.io','Sec-Fetch-Site':'cross-site'}
    token='a'*32
    with TestClient(m.app) as client:
        preflight=client.options('/api/analytics/visit', headers={
            'Origin':'https://hcmue.github.io',
            'Access-Control-Request-Method':'POST',
            'Access-Control-Request-Headers':'content-type'
        })
        assert preflight.status_code==200
        assert preflight.headers['access-control-allow-origin']=='https://hcmue.github.io'
        v=client.post('/api/analytics/visit',headers=good,json={'visitor_id':token})
        assert v.status_code==200,v.text
        assert 'set-cookie' not in v.headers
        assert v.headers['access-control-allow-origin']=='https://hcmue.github.io'
        assert client.post('/api/analytics/visit',headers=good,json={'visitor_id':token}).status_code==200
        assert client.get('/api/stats/public').json()['visits']==1
        r=client.get('/api/search?query=test',headers=good)
        assert r.headers['access-control-allow-origin']=='https://hcmue.github.io'
        bad=client.post('/api/analytics/visit', headers={'Origin':'https://evil.test'},json={'visitor_id':token})
        assert bad.status_code==403
        assert 'access-control-allow-origin' not in bad.headers
        assert client.get('/api/admin/items',headers=good).status_code==401
