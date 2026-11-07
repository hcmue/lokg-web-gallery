"""LOKG-IR MIWAI retrieval-core adapter for the Web Design teaching collection.

REUSED FROM USER-SUPPLIED UPSTREAM, UNMODIFIED:
    build_okf, entity_idf, make_lookups, link, sigma_candidates, sigma_score.

EDUCATIONAL ADAPTATION (not claimed to reproduce Visual Genome/CLIP results):
    teacher YAML => scene-like components/attributes => OKF concept incidence;
    links => pair-specific bridge concepts;
    bilingual UI query => query concepts and directed relation triples;
    lightweight normalized TF-IDF character vectors in place of CLIP image embeddings.

This is a genuinely invoked upstream LOKG-IR graph traversal and scoring core,
not an alias for BM25 or the earlier OKF graph-overlap reranker.
"""
from __future__ import annotations

import re
from typing import Any

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from .vendor_lokg.vg_multihop import (
    build_okf, entity_idf, make_lookups, link,
    sigma_candidates, sigma_score,
)
from .search_aliases import detect, normalize, COMPONENT_ALIASES, RELATION_ALIASES


# Explicit demonstration defaults; not the manuscript's tuned weights.
ALPHA_EMBED = .50
BETA_TEXT = .35
GAMMA_GRAPH = .15
ENTRY_N = 20
DEPTH = 4
BUDGET = 400
PER_ENTITY_CAP = 25
HUB_DF_FRAC = .05


def safe_token(value: Any) -> str:
    return normalize(str(value)).replace(' ', '_')[:90]





def record_scene(record: dict) -> dict:
    """From teacher-authored YAML to original benchmark's scene-like input.

    Not an automatic visual detector. All concepts stem from manually supplied
    metadata, consistent with the evidence/annotation protocol.
    """
    objects = set()
    attrs = set()
    for component in record.get('components', []) or []:
        label = safe_token(component)
        if label:
            objects.add(label)
    category = safe_token(record.get('category', ''))
    if category:
        attrs.add('category__' + category)
    layout = safe_token(record.get('layout', ''))
    if layout:
        attrs.add('layout__' + layout)
    for tag in record.get('tags', []) or []:
        t = safe_token(tag)
        if t:
            attrs.add('tag__' + t)
    for rel in record.get('relations', []) or []:
        subject, predicate, target = rel.get('subject',''),rel.get('predicate',''),rel.get('object','')
        for entity in (subject,target):
            v = safe_token(entity)
            if v:objects.add(v)
        if subject and predicate and target:
            attrs.add('predicate__' + safe_token(predicate))
            # The upstream OKF index only reads object/attribute incidences,
            # not sg['rels']. Reify each *teacher-verified* directed relation
            # as a distinct attribute concept; do not claim HTML vision parsing.
            attrs.add('relation__' + safe_token(subject) + '__' + safe_token(predicate)
                      + '__' + safe_token(target))
    # The upstream build_okf expects a list of objects with attribute sets.
    objlist=[{'oid':j+1,'name':value,'attrs':set()} for j,value in enumerate(sorted(objects))]
    if attrs:
        # Add attributes under a neutral metadata node, making them indexable.
        objlist.append({'oid':len(objlist)+1, 'name':'web_page', 'attrs':attrs})
    if not objlist:
        objlist=[{'oid':1,'name':'web_page','attrs':set()}]
    return {'objects':objlist, 'rels':[]}


def parse_explicit_relations(query: str) -> set[tuple[str,str,str]]:
    """Recognize short expressions 'sidebar ben trai grid', not arbitrary VLM spatial facts.

    Only clear subject <relation> object order is accepted.  A relation tag
    is indexed only when a teacher actually annotated it in the YAML record.
    """
    q=normalize(query)
    entities=[]
    relations=[]
    for name,aliases in COMPONENT_ALIASES.items():
        for term in aliases:
            term=normalize(term)
            if not term:continue
            for match in re.finditer(r'(?<![a-z0-9])'+re.escape(term)+r'(?![a-z0-9])',q):
                entities.append((match.start(),match.end(),name))
    for name,aliases in RELATION_ALIASES.items():
        for term in aliases:
            term=normalize(term)
            if not term:continue
            for match in re.finditer(r'(?<![a-z0-9])'+re.escape(term)+r'(?![a-z0-9])',q):
                relations.append((match.start(),match.end(),name))
    result=set()
    for start,end,predicate in relations:
        before=[e for e in entities if e[1]<=start and start-e[1]<=32]
        after=[e for e in entities if e[0]>=end and e[0]-end<=32]
        if before and after:
            left=max(before,key=lambda e:e[1])
            right=min(after,key=lambda e:e[0])
            if left[2]!=right[2]:result.add((left[2],predicate,right[2]))
    return result


class LOKGRetriever:
    """Read-only LOKG graph index rebuilt after teacher CRUD operations."""

    def __init__(self, records:list[dict]):
        self.records=sorted(records,key=lambda x:x['id'])
        self.ids=[r['id'] for r in self.records]
        self.documents=[]
        graphs={}
        self.nodes={}
        for item in self.records:
            iid=item['id']
            sg=record_scene(item)
            graphs[iid]=sg
            self.documents.append(' '.join([
                item.get('title',''),item.get('description',''),item.get('category',''),
                item.get('layout',''), ' '.join(item.get('components',[]) or []),
                ' '.join(item.get('tags',[]) or []),
                ' '.join(' '.join([str(r.get('subject','')),str(r.get('predicate','')),str(r.get('object',''))])
                         for r in item.get('relations',[]) or []),
            ]))
        if graphs:
            c2i,ic=build_okf(graphs)  # EXACT upstream MIWAI implementation
            # Express Markdown wiki-links as bridge entities shared by both nodes.
            for item in self.records:
                for target in item.get('links',[]) or []:
                    if target in ic and target!=item['id']:
                        bridge='attr:link__'+'__'.join(sorted([safe_token(item['id']),safe_token(target)]))
                        for eid in (item['id'],target):
                            ic[eid].add(bridge)
                            c2i[bridge].add(eid)
            self.concept2img=c2i
            self.img_concepts=ic
            self.idf=entity_idf(c2i,len(self.ids))   # EXACT upstream
            lookups,_expanded=make_lookups(c2i.keys(),{})  # EXACT upstream, returns (naive, expanded)
            self.lookup={k:v for k,v in lookups.items() if v.startswith('obj:')}
            self.vectorizer=TfidfVectorizer(analyzer='char_wb',ngram_range=(3,5),sublinear_tf=True)
            self.IMG=self.vectorizer.fit_transform([normalize(d) or 'empty' for d in self.documents]).astype(np.float32).toarray()
        else:
            self.concept2img={};self.img_concepts={};self.idf={};self.lookup={}
            self.vectorizer=None
            self.IMG=np.zeros((0,1),dtype=np.float32)

    def query_concepts(self, query:str) -> set[str]:
        cats,comps,preds=detect(query)
        qc=set()
        for c in cats:qc.add('attr:category__'+safe_token(c))
        for c in comps:qc.add('obj:'+safe_token(c))
        for p in preds:qc.add('attr:predicate__'+safe_token(p))
        for subject,predicate,obj in parse_explicit_relations(query):
            concept='attr:relation__'+safe_token(subject)+'__'+safe_token(predicate)+'__'+safe_token(obj)
            if concept in self.concept2img:
                qc.add(concept)
        # Match teacher-entered tags as graph concepts. This is explicit textual
        # metadata, not automatic visual/spatial reasoning from the URL.
        normalized=' '+normalize(query)+' '
        for item in self.records:
            for tag in item.get('tags',[]):
                needle=normalize(tag)
                if needle and (' '+needle+' ') in normalized:
                    token='attr:tag__'+safe_token(tag)
                    if token in self.concept2img:
                        qc.add(token)
        # This is the original benchmark's string-to-concept linker. It
        # recognizes exact component labels not already picked up by aliases.
        qc.update(link(normalize(query),self.lookup))
        return qc

    def rank(self, query:str) -> dict[str,dict[str,Any]]:
        if not self.ids or not query.strip():return {}
        text=normalize(query)
        qv=self.vectorizer.transform([text or 'empty']).astype(np.float32).toarray()[0]
        qc=self.query_concepts(query)
        candidates=sigma_candidates(  # EXACT upstream MIWAI bounded traversal
            qv,self.IMG,self.ids,qc,self.concept2img,self.img_concepts,
            entry_n=ENTRY_N,depth=DEPTH,idf=self.idf,budget=BUDGET,
            per_entity_cap=PER_ENTITY_CAP,hub_df_frac=HUB_DF_FRAC,
            n_images=len(self.ids),
        )
        scores=sigma_score(candidates,len(self.ids),ALPHA_EMBED,BETA_TEXT,GAMMA_GRAPH)
        out={}
        for i,(embedding,text_overlap,proximity) in candidates.items():
            score=float(scores[i])
            if score<=0:continue
            iid=self.ids[i]
            out[iid]={
                'score':round(score,6),
                'breakdown':{
                    'embedding':round(float(embedding),6),
                    'entity_text':round(float(text_overlap),6),
                    'graph_proximity':round(float(proximity),6),
                },
            }
        return out

    def concepts(self,item_id:str) -> list[str]:
        return sorted(self.img_concepts.get(item_id,set()))

    def status(self) -> dict:
        return {'engine':'lokg-miwai-core','images':len(self.ids),
                'concepts':len(self.concept2img),
                'incidences':sum(len(x) for x in self.img_concepts.values()),
                'encoding':'char_tfidf (CPU-friendly text vectors; NOT CLIP image features)',
                'source_functions':['build_okf','make_lookups','link','entity_idf','sigma_candidates','sigma_score'],
                'parameters':{'entry_n':ENTRY_N,'depth':DEPTH,'budget':BUDGET,
                              'per_entity_cap':PER_ENTITY_CAP,'hub_df_frac':HUB_DF_FRAC,
                              'weights':{'embedding':ALPHA_EMBED,'entity_text':BETA_TEXT,'graph_proximity':GAMMA_GRAPH}},
                'note':'Teacher-entered URL, keywords and optional annotated layout/relations; no spatial relations are extracted automatically from HTML or images.'}
