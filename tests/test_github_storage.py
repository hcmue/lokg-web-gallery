"""No actual GitHub credentials or live network required for persistence tests."""
import base64, yaml
from pathlib import Path
from dataclasses import replace
from app.config import get_settings
from app.catalog import Catalog


def test_mock_github_contents_api(monkeypatch,tmp_path):
    config=replace(get_settings(),catalog_backend='github',github_repository='example/lokg-gallery',github_token='fake-test-token',github_catalog_path='data/catalog.yaml')
    raw='schema_version: 1\nitems: []\n'
    sha='sha-0'
    calls=[]
    class Response:
        def __init__(self,status,body):self.status_code=status;self._body=body
        def json(self):return self._body
    def fake_get(url,params,headers,timeout):
        assert 'api.github.com' in url
        assert headers['Authorization']=='Bearer fake-test-token'
        return Response(200,{'encoding':'base64','content':base64.b64encode(raw.encode()).decode(),'sha':sha})
    def fake_put(url,json,headers,timeout):
        nonlocal raw,sha
        assert json['sha']==sha and json['branch']=='main'
        raw=base64.b64decode(json['content']).decode()
        calls.append(json['message'])
        sha='sha-'+str(len(calls))
        return Response(200,{'content':{'sha':sha}})
    monkeypatch.setattr('app.catalog.httpx.get',fake_get)
    monkeypatch.setattr('app.catalog.httpx.put',fake_put)
    store=Catalog(config)
    saved=store.create('https://sample.github.io/gallery/pages/a.html','thương mại điện tử, navbar, product grid')
    assert 'Add Web UI link' in calls[0]
    assert len(store.all())==1
    reloaded=Catalog(config)
    assert reloaded.get(saved['id'])['page_url'].endswith('/a.html')
    store.update(saved['id'],'https://sample.github.io/gallery/pages/b.html','dashboard, sidebar')
    reloaded=Catalog(config)
    assert reloaded.get(saved['id'])['tags']==['dashboard','sidebar']
    store.remove(saved['id'])
    assert len(Catalog(config).all())==0
    assert len(calls)==3
