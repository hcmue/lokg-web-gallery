"""Verify local SQLite tracking, privacy and administrative report endpoints."""
from __future__ import annotations
import importlib
from datetime import date, datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import insert, select, func

from app.analytics import events, cleaned_query, to_sqlalchemy_url

@pytest.fixture
def client_with_stats(tmp_path, monkeypatch):
    monkeypatch.setenv('APP_ENV','development')
    monkeypatch.setenv('CATALOG_BACKEND','local')
    monkeypatch.setenv('CATALOG_PATH',str(tmp_path/'catalog.yaml'))
    monkeypatch.setenv('ADMIN_PASSWORD','TestOnlyStrongPassword12345!')
    monkeypatch.setenv('SESSION_SECRET','TestOnlySecretKeyWithMoreThan32Characters!!!!')
    monkeypatch.setenv('ANALYTICS_ENABLED','true')
    monkeypatch.setenv('DATABASE_URL',f'sqlite:///{tmp_path}/analytics.db')
    monkeypatch.setenv('ANALYTICS_SECRET','AnalyticsTestSecretKeyMoreThan32Characters!!')
    monkeypatch.setenv('ANALYTICS_RETENTION_DAYS','90')
    monkeypatch.setenv('ANALYTICS_STORE_QUERIES','true')
    import app.main as main
    importlib.reload(main)
    with TestClient(main.app) as client:
        yield client,main.app

def login(client):
    assert client.post('/api/auth/login',json={'password':'TestOnlyStrongPassword12345!'}).status_code==200

def test_public_counter_and_browser_dedup(client_with_stats):
    client,_=client_with_stats
    assert client.get('/api/stats/public').json()['visits']==0
    assert client.get('/').status_code==200  # Backend root alone does not count a visit
    assert client.get('/api/stats/public').json()['visits']==0
    res=client.post('/api/analytics/visit')
    assert res.status_code==200
    assert 'httponly' in res.headers['set-cookie'].lower()
    assert client.get('/api/stats/public').json()['visits']==1
    assert client.get('/api/stats/public').json()['unique_browsers_today']==1
    assert client.post('/api/analytics/visit').status_code==200
    assert client.get('/api/stats/public').json()['visits']==1  # 30 sec de-dup
    with TestClient(client.app) as fresh:
        assert fresh.post('/api/analytics/visit').status_code==200
        assert fresh.get('/api/stats/public').json()['visits']==2
        assert fresh.get('/api/stats/public').json()['unique_browsers_today']==2


def test_search_tracking_clicks_admin_csv(client_with_stats):
    client,app=client_with_stats
    assert client.get('/api/admin/stats').status_code==401
    client.post('/api/analytics/visit')
    login(client)
    body={'page_url':'https://example.github.io/gallery/pages/sample-1.html','keywords':'navbar, cửa hàng, lưới sản phẩm'}
    r=client.post('/api/admin/items',json=body)
    assert r.status_code==201,r.text
    item_id=r.json()['item']['id']
    assert client.get('/api/search',params={'query':'navbar','mode':'lokg'}).status_code==200
    assert client.get('/api/search',params={'query':'navbar','mode':'bm25','offset':1}).status_code==200
    assert client.get('/api/search').status_code==200
    assert client.get('/api/search',params={'query':'zzzkjdoas','mode':'lokg'}).status_code==200
    assert client.post('/api/analytics/click',json={'item_id':item_id}).status_code==200
    assert client.post('/api/analytics/click',json={'item_id':'NOPE'}).status_code==404
    report=client.get('/api/admin/stats?days=7').json()
    assert report['enabled'] is True
    assert report['summary']['visits']==1
    assert report['summary']['searches']==2
    assert report['summary']['clicks']==1
    assert report['summary']['no_results']==1
    assert any(q['query']=='navbar' for q in report['top_queries'])
    csv=client.get('/api/admin/stats.csv?days=7')
    assert csv.status_code==200
    assert 'text/csv' in csv.headers['content-type']
    assert 'date_utc' in csv.text
    assert client.get('/privacy').status_code==200
    with app.state.analytics.engine.connect() as conn:
        rows=conn.execute(select(events)).mappings().all()
        assert len(rows)==4
        assert all('ip' not in e.keys() and 'user_agent' not in e.keys() for e in rows)


def test_retention_prune(client_with_stats):
    _,app=client_with_stats
    db=app.state.analytics
    old=datetime.now(timezone.utc)-timedelta(days=93)
    with db.engine.begin() as conn:
        conn.execute(insert(events).values(kind='visit',created_at=old,event_date=old.date()))
    db.prune_old(force=True)
    with db.engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(events))==0


def test_mask_pii_and_database_url():
    s=cleaned_query('trang demo test@gmail.com có số 0901234567')
    assert 'test@gmail.com' not in s
    assert '0901234567' not in s
    assert '[email]' in s and '[phone]' in s
    assert to_sqlalchemy_url('postgresql://u:p@host/db')=='postgresql+psycopg://u:p@host/db'


def test_disabled_when_unconfigured(tmp_path,monkeypatch):
    monkeypatch.setenv('APP_ENV','development')
    monkeypatch.setenv('CATALOG_BACKEND','local')
    monkeypatch.setenv('CATALOG_PATH',str(tmp_path/'local.yaml'))
    monkeypatch.setenv('ANALYTICS_ENABLED','false')
    import app.main as main
    importlib.reload(main)
    with TestClient(main.app) as client:
        assert client.post('/api/analytics/visit').json()['enabled']==False
        assert client.get('/api/stats/public').json()['enabled']==False
        assert client.get('/api/search',params={'query':'demo'}).status_code==200

def test_cross_site_analytics_blocked(client_with_stats):
    client,_=client_with_stats
    assert client.post('/api/analytics/visit',headers={'Origin':'https://some-foreign-site.test'}).status_code==403
    assert client.post('/api/analytics/visit',headers={'Sec-Fetch-Site':'cross-site'}).status_code==403
    assert client.get('/api/stats/public').json()['visits']==0


def test_persist_analytics_between_new_instances(client_with_stats):
    client,app=client_with_stats
    client.post('/api/analytics/visit')
    from app.analytics import Analytics
    independent=Analytics(app.state.analytics.cfg)
    assert independent.public()['visits']==1
    independent.engine.dispose()
