"""Regression checks for the 150-Web-UI educational catalog extension."""
from __future__ import annotations
import json
import re
from collections import Counter
from pathlib import Path
import yaml

ROOT=Path(__file__).resolve().parents[1]
GROUPS=('ECO','EDU','BUS','NEW','LAN','DAS')

def test_exact_150_samples_and_original_72_untouched():
    pages=ROOT/'docs/pages'
    previews=ROOT/'docs/previews'
    pids={p.stem for p in pages.glob('WEB-*.html')}
    vids={p.stem for p in previews.glob('WEB-*.webp')}
    assert len(pids)==len(vids)==150
    assert pids==vids
    for p in GROUPS:
        assert {f'WEB-{p}-{i:03d}' for i in range(1,26)}.issubset(pids)
        for i in range(1,13):
            assert (pages/f'WEB-{p}-{i:03d}.html').exists()


def test_yaml_150_live_urls_and_relations():
    entries=yaml.safe_load((ROOT/'data/catalog.yaml').read_text(encoding='utf-8'))['items']
    assert len(entries)==150
    assert Counter(x['id'].split('-')[1] for x in entries)=={k:25 for k in GROUPS}
    ext=[e for e in entries if int(e['id'].split('-')[-1])>=13]
    assert len(ext)==78
    assert len({e['title'] for e in ext})==78
    for entry in entries:
        assert entry['page_url']==f"https://hcmue.github.io/lokg-web-gallery/pages/{entry['id']}.html"
        assert entry['tags']
        assert (ROOT/'docs/pages'/(entry['id']+'.html')).is_file()
    for item in ext:
        assert item['category'] and item['components'] and item['layout']
        assert item['source']=='synthetic_gallery_extension_150'
        assert item['verified'] is False
        for rel in item['relations']:
            assert rel['subject'] in item['components'] and rel['object'] in item['components']
            assert rel['predicate'] in ('left_of','right_of','above','below','near','inside')


def test_new_html_has_no_unexpanded_templates():
    for path in (ROOT/'docs/pages').glob('WEB-*.html'):
        if int(path.stem.split('-')[-1])<13:continue
        content=path.read_text(encoding='utf-8')
        assert '<main' in content and '</main>' in content
        assert '<title>' in content and 'sample-150.css' in content
        assert not re.search(r'\{(?:product_cards|eyebrow|panel_art|title|chart|buttons|table|tiles)\b',content)


def test_fallback_catalog_matches_yaml():
    entries=yaml.safe_load((ROOT/'data/catalog.yaml').read_text(encoding='utf-8'))['items']
    fallback=json.loads((ROOT/'docs/gallery-fallback.json').read_text(encoding='utf-8'))
    assert len(fallback)==150
    assert {e['id'] for e in entries}=={e['id'] for e in fallback}
    assert all((ROOT/'docs'/f['local_preview']).exists() for f in fallback)


def test_guide_and_home_link():
    guide=(ROOT/'docs/huong-dan.html').read_text(encoding='utf-8')
    homepage=(ROOT/'docs/index.html').read_text(encoding='utf-8')
    assert 'id="sinh-vien"' in guide and 'id="giang-vien"' in guide
    assert '150' in guide and 'huong-dan.html' in homepage
    assert 'resourcesCount">150' in homepage
    assert (ROOT/'docs/assets/guide.css').is_file()


def test_relation_query_and_catalog_crud_preserve_annotations(tmp_path):
    from dataclasses import replace
    from app.config import get_settings
    from app.catalog import Catalog
    from app.lokg_engine import parse_explicit_relations
    assert ('sidebar','left_of','grid') in parse_explicit_relations('sidebar ben trai luoi san pham')
    assert ('filter','inside','sidebar') in parse_explicit_relations('bo loc trong thanh ben')
    assert ('filter','left_of','grid') not in parse_explicit_relations('bo loc phia tren luoi')
    src=ROOT/'data/catalog.yaml'
    path=tmp_path/'catalog.yaml'
    path.write_bytes(src.read_bytes())
    cfg=replace(get_settings(),catalog_backend='local',catalog_path=path,
                allowed_page_hosts='hcmue.github.io')
    store=Catalog(cfg)
    assert len(store.all())==150
    original=store.get('WEB-ECO-014')
    assert original['layout']=='catalog-side' and original['relations']
    store.create('https://hcmue.github.io/lokg-web-gallery/pages/WEB-TEST-001.html','ecommerce,navbar')
    reloaded=Catalog(cfg)
    preserved=reloaded.get('WEB-ECO-014')
    assert preserved['layout']==original['layout']
    assert preserved['relations']==original['relations']
    assert preserved['components']==original['components']
