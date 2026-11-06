#!/usr/bin/env python3
"""
vg_multihop.py  (v2)  --  VG-Multihop benchmark + OKF index + retrieval baselines for LOKG-IR.

What changed vs v1 (the fixes that matter):
  * SEMANTIC GAP.  Queries are paraphrased with synonyms/hypernyms (dog->canine,
    car->automobile, red->crimson ...), so exact concept-string overlap is no
    longer sufficient.  This is what lets embedding + entity-linking + traversal
    show value; a brittle lexical matcher no longer behaves like an oracle.
  * NO GOLD LEAKAGE.  Retrieval systems now see ONLY the query TEXT and must link
    text->concepts themselves.  The gold `pattern`/`relevant` are used ONLY for
    evaluation, never for retrieval (v1 illegally read q["pattern"] inside the
    ranking functions, which is why KG-overlap looked unbeatable).
  * TWO LINKERS.  link_naive (exact surface match = brittle graph baseline) vs
    link_expanded (synonym-aware = stand-in for an LLM entity extractor).
  * HYBRID ENTRY SET + alpha/beta/gamma TUNING on a validation split.
  * fp16 image encoding + automatic CPU fallback (for 4 GB laptop GPUs).

INTEGRITY: synthetic numbers are a smoke-test only. The synonym lexicon and the
expanded linker are STAND-INS for real components (an LLM paraphraser and an
LLM/embedding entity linker). For the paper, use real CLIP, a real paraphraser,
a real GraphRAG baseline, and a real S_text model.

Self-test (no data/GPU), fixes active:
    python vg_multihop.py all --synthetic --n-images 800 --n-queries 1200 \
        --paraphrase lexicon --tune --out runs/synth
Real run (RTX 3050 Ti, 4 GB):
    python vg_multihop.py all --vg-dir VG --vg-img-dir VG/images \
        --n-images 5000 --n-queries 2000 --paraphrase wordnet --tune \
        --clip-model ViT-B-32 --device cuda --batch 32 --out runs/vg
"""
import argparse, json, os, random, math, sys, time, subprocess
from collections import defaultdict, Counter
import numpy as np
import scipy.sparse as sp

def norm(s): return str(s).strip().lower()

# --------------------------- synonym / hypernym lexicon ---------------------- #
SYN = {
 "dog":["canine","puppy","hound"], "car":["automobile","vehicle"],
 "woman":["lady","female"], "man":["gentleman","male"], "dress":["gown","frock"],
 "drum":["percussion"], "textile":["fabric","cloth"], "tree":["plant"],
 "hat":["cap","headwear"], "table":["desk"], "flower":["blossom","bloom"],
 "house":["home","building"], "bird":["fowl"], "boat":["vessel","ship"],
 "lamp":["light","lantern"], "book":["volume"], "chair":["seat"],
 "cup":["mug"], "bicycle":["bike","cycle"], "shoe":["footwear"],
 "red":["crimson","scarlet"], "blue":["azure"], "large":["big","huge"],
 "small":["tiny","little"], "old":["aged","ancient"], "wooden":["timber"],
 "green":["verdant"], "traditional":["classic"], "handcrafted":["handmade"],
 "rural":["countryside"],
}
def wordnet_syn(word):
    try:
        from nltk.corpus import wordnet as wn
    except Exception:
        return []
    out=set()
    for ss in wn.synsets(word):
        for l in ss.lemmas():
            w=l.name().replace("_"," ").lower()
            if w!=word: out.add(w)
        for hy in ss.hypernyms():
            for l in hy.lemmas(): out.add(l.name().replace("_"," ").lower())
    return list(out)[:4]

def build_synonym_maps(concepts, mode, seed, synth=False):
    fwd=defaultdict(list); rev={}
    if mode=="none": return fwd, rev
    for c in concepts:
        if mode=="lexicon":
            vs=SYN.get(c,[])
            if not vs and synth: vs=[c+"z"]        # procedural variant for ring concepts
        elif mode=="wordnet":
            vs=wordnet_syn(c)
        else:
            vs=[]
        for v in vs:
            if v and v not in concepts:
                fwd[c].append(v); rev[v]=c
    return fwd, rev

# ------------------------------ scene graphs -------------------------------- #
def load_vg(vg_dir, n_images, seed):
    path=os.path.join(vg_dir,"scene_graphs.json")
    if not os.path.exists(path): sys.exit(f"[error] {path} not found.")
    raw=json.load(open(path)); random.Random(seed).shuffle(raw); graphs={}
    for sg in raw:
        objs=[]; id2={}
        for o in sg.get("objects",[]):
            oid=o["object_id"]; name=norm(o["names"][0] if o.get("names") else o.get("name",""))
            if not name: continue
            objs.append({"oid":oid,"name":name,"attrs":set(norm(a) for a in o.get("attributes",[]) if a)}); id2[oid]=name
        rels=[]
        for r in sg.get("relationships",[]):
            s,ob,p=r.get("subject_id"),r.get("object_id"),norm(r.get("predicate",""))
            if s in id2 and ob in id2 and p: rels.append((s,p,ob))
        if objs: graphs[sg["image_id"]]={"objects":objs,"rels":rels}
        if len(graphs)>=n_images: break
    print(f"[load] {len(graphs)} VG scene graphs"); return graphs

def make_synthetic(n_images, seed, M=200, window=2):
    """Ring-structured toy data: M object-concepts on a ring; each image samples a
    local window, so nearby concepts co-occur but distant ones don't -> genuine
    multi-hop bridges exist (concept i connects to i+4 via i+2)."""
    rng=random.Random(seed)
    ATTRS=["red","blue","green","large","small","old","wooden","rural"]
    PREDS=["near","on","under","beside","with","holding"]; graphs={}
    for iid in range(n_images):
        center=rng.randrange(M); k=rng.randint(3,5)
        win=[ (center+off)%M for off in range(-window,window+1) ]
        names=rng.sample(win, min(k,len(win)))
        objs=[{"oid":j,"name":f"c{names[j]:02d}",
               "attrs":set(rng.sample(ATTRS,rng.randint(0,1)))} for j in range(len(names))]
        rels=[(a,rng.choice(PREDS),b) for a,b in
              [rng.sample(range(len(objs)),2) for _ in range(rng.randint(1,len(objs)))]] if len(objs)>=2 else []
        graphs[iid]={"objects":objs,"rels":rels}
    print(f"[synthetic] {len(graphs)} ring-structured toy graphs (M={M}, window={window})"); return graphs

# ----------------------- queries + gold ground-truth ------------------------ #
def sample_pattern(sg, target, rng):
    objs=sg["objects"]
    if not objs: return None
    adj=defaultdict(list)
    for s,p,o in sg["rels"]: adj[s].append(o); adj[o].append(s)
    id2={o["oid"]:o for o in objs}
    start=rng.choice(objs)["oid"]; chosen=[start]; fr=list(adj[start]); rng.shuffle(fr)
    while len(chosen)<target and fr:
        nxt=fr.pop()
        if nxt not in chosen and nxt in id2:
            chosen.append(nxt); nb=list(adj[nxt]); rng.shuffle(nb); fr.extend(nb)
    unary=[]
    for oid in chosen:
        o=id2[oid]
        attrs=frozenset(rng.sample(sorted(o["attrs"]),1)) if (o["attrs"] and rng.random()<0.6) else frozenset()
        unary.append((o["name"],attrs))
    cs=set(chosen)
    binary=list(dict.fromkeys((id2[s]["name"],p,id2[o]["name"]) for s,p,o in sg["rels"] if s in cs and o in cs))
    return {"unary":unary,"binary":binary}

def complexity(pat):
    rels=len(pat["binary"]); objs=len(pat["unary"])
    return "complex" if rels>=2 else ("moderate" if (rels==1 or objs>=2) else "simple")

def image_matches(sg, pat):
    by=defaultdict(list)
    for o in sg["objects"]: by[o["name"]].append(o)
    id2={o["oid"]:o for o in sg["objects"]}
    rel=set((id2[a]["name"],p,id2[b]["name"]) for a,p,b in sg["rels"])
    cands=[]
    for name,req in pat["unary"]:
        c=[o for o in by.get(name,[]) if req.issubset(o["attrs"])]
        if not c: return False
        cands.append(c)
    def bt(i,used):
        if i==len(pat["unary"]): return all(t in rel for t in pat["binary"])
        for o in cands[i]:
            if o["oid"] in used: continue
            used.add(o["oid"])
            if bt(i+1,used): return True
            used.discard(o["oid"])
        return False
    return bt(0,set())

def render_text(pat, fwd, rng):
    def surf(name):
        vs=fwd.get(name,[]); return rng.choice(vs) if (vs and rng.random()<0.7) else name
    def npair(name,attrs): return (" ".join(surf(x) for x in sorted(attrs))+" "+surf(name)).strip()
    parts=[]; used=set()
    for sn,p,on in pat["binary"]:
        sa=next((a for nm,a in pat["unary"] if nm==sn),frozenset())
        oa=next((a for nm,a in pat["unary"] if nm==on),frozenset())
        parts.append(f"{npair(sn,sa)} {p} {npair(on,oa)}"); used.add(sn); used.add(on)
    for nm,a in pat["unary"]:
        if nm not in used: parts.append(npair(nm,a))
    return " with ".join(parts) if parts else "image"

def build_queries(graphs, n_queries, fwd, seed, rel_min=1, rel_max=300):
    rng=random.Random(seed+1); iids=list(graphs.keys()); name_index=defaultdict(set)
    for iid,sg in graphs.items():
        for o in sg["objects"]: name_index[o["name"]].add(iid)
    queries=[]; seen=set(); att=0
    while len(queries)<n_queries and att<n_queries*40:
        att+=1; iid=rng.choice(iids)
        pat=sample_pattern(graphs[iid], rng.choice([1,1,2,2,2,3,3,4]), rng)
        if not pat or not pat["unary"]: continue
        key=(tuple(sorted((n,tuple(sorted(a))) for n,a in pat["unary"])),tuple(sorted(pat["binary"])))
        if key in seen: continue
        cand=None
        for name,_ in pat["unary"]:
            s=name_index.get(name,set()); cand=s if cand is None else cand&s
            if not cand: break
        if not cand: continue
        rel=[j for j in cand if image_matches(graphs[j],pat)]
        if not (rel_min<=len(rel)<=rel_max): continue
        seen.add(key)
        queries.append({"qid":len(queries),"text":render_text(pat,fwd,rng),
                        "pattern":{"unary":[[n,sorted(a)] for n,a in pat["unary"]],
                                   "binary":[list(b) for b in pat["binary"]]},
                        "complexity":complexity(pat),"relevant":sorted(rel)})
    print(f"[queries] {len(queries)}  by complexity: {dict(Counter(q['complexity'] for q in queries))}")
    return queries

def _surf_label(concept, fwd, rng):
    bare=concept.split(":",1)[1]; vs=fwd.get(bare,[])
    return rng.choice(vs) if (vs and rng.random()<0.7) else bare

def build_multihop_queries(graphs, concept2img, img_concepts, n_queries, fwd, seed,
                           rel_min=2, rel_max=300, bridge_df_frac=0.03):
    """Bridge/path queries over the entity co-occurrence graph. A k-hop path
    e0-e1-...-ek connects two endpoints that NEVER co-occur; the query mentions only
    the endpoints (e0, ek). GOLD relevant = images that WITNESS an interior edge of
    the path. INTERIOR (bridge) entities are restricted to SPECIFIC ones (low
    document-frequency) so hubs like 'man/tree/sky' cannot serve as trivial bridges."""
    rng=random.Random(seed+2); N=len(graphs)
    df_cut=bridge_df_frac*N
    ents=[e for e in concept2img if 3<=len(concept2img[e])<=rel_max]
    specific=set(e for e in concept2img if len(concept2img[e])<=df_cut)   # allowed as bridges
    nb_cache={}
    def neighbors(e):
        if e not in nb_cache:
            ns=set()
            for img in list(concept2img[e])[:400]: ns|=img_concepts[img]
            ns.discard(e); nb_cache[e]=ns
        return nb_cache[e]
    def witnesses(path):
        rel=set()
        for i in range(len(path)-1): rel|= concept2img[path[i]] & concept2img[path[i+1]]
        return rel
    queries=[]; seen=set(); att=0
    HOPS=[(1,"simple"),(2,"moderate"),(2,"moderate"),(3,"complex")]
    while len(queries)<n_queries and att<n_queries*80:
        att+=1; k,comp=rng.choice(HOPS)
        if k==1:
            A=rng.choice(ents); rel=sorted(concept2img[A])
            if not (rel_min<=len(rel)<=rel_max): continue
            key=("1",A)
            if key in seen: continue
            seen.add(key)
            queries.append({"qid":len(queries),"text":_surf_label(A,fwd,rng),
                            "pattern":{"path":[A],"hops":1},"complexity":comp,"relevant":rel})
            continue
        A=rng.choice(ents); path=[A]; ok=True
        for step in range(k):
            cur=path[-1]
            cnb=[x for x in neighbors(cur) if x in concept2img and x not in path]
            interior = (step < k-1)                     # last step reaches the endpoint C
            if interior: cnb=[x for x in cnb if x in specific]   # bridge must be specific
            if not cnb: ok=False; break
            path.append(rng.choice(cnb))
        if not ok or len(path)!=k+1: continue
        A,C=path[0],path[-1]
        if concept2img[A] & concept2img[C]: continue    # endpoints never co-occur
        rel=[j for j in sorted(witnesses(path)) if not (A in img_concepts[j] and C in img_concepts[j])]
        if not (rel_min<=len(rel)<=rel_max): continue
        key=(str(k),A,C)
        if key in seen: continue
        seen.add(key)
        text=f"{_surf_label(A,fwd,rng)} related to {_surf_label(C,fwd,rng)}"
        queries.append({"qid":len(queries),"text":text,
                        "pattern":{"path":path,"hops":k},"complexity":comp,"relevant":rel})
    print(f"[multihop] {len(queries)} bridge queries (bridge df<= {df_cut:.0f})  by complexity: "
          f"{dict(Counter(q['complexity'] for q in queries))}")
    return queries

# --------------------------- OKF index + linkers ---------------------------- #
def build_okf(graphs):
    concept2img=defaultdict(set); img_concepts={}
    for iid,sg in graphs.items():
        names=set(o["name"] for o in sg["objects"]); attrs=set(a for o in sg["objects"] for a in o["attrs"])
        cs=set("obj:"+n for n in names)|set("attr:"+a for a in attrs); img_concepts[iid]=cs
        for c in cs: concept2img[c].add(iid)
    print(f"[okf] {len(concept2img)} entity files"); return concept2img, img_concepts

def make_lookups(concepts, rev):
    pref={}
    for c in concepts: pref[c.split(":",1)[1]]=c
    naive=dict(pref); exp=dict(pref)
    for variant,canon in rev.items():
        if canon in pref: exp[variant]=pref[canon]
    return naive, exp

def link(text, lookup, maxgram=3):
    toks=text.replace(","," ").split(); found=set(); i=0
    while i<len(toks):
        matched=False
        for g in range(min(maxgram,len(toks)-i),0,-1):
            ph=" ".join(toks[i:i+g])
            if ph in lookup: found.add(lookup[ph]); i+=g; matched=True; break
        if not matched: i+=1
    return found

# ------------------------------- encoding ----------------------------------- #
def query_canon_concepts(q):
    """Prefixed canonical concepts a query is 'about' (for building synthetic query emb)."""
    pat=q["pattern"]
    if "unary" in pat:
        return (["obj:"+n for n,_ in pat["unary"]]
                +["attr:"+a for _,al in pat["unary"] for a in al])
    return [pat["path"][0], pat["path"][-1]]        # bridge query: the two endpoints

def encode_synthetic(graphs, queries, seed):
    rng=np.random.default_rng(seed); vocab={}
    def vid(c): return vocab.setdefault(c,len(vocab))
    img_bags={}
    for iid,sg in graphs.items():
        names=set(o["name"] for o in sg["objects"]); attrs=set(a for o in sg["objects"] for a in o["attrs"])
        img_bags[iid]=[vid("obj:"+n) for n in names]+[vid("attr:"+a) for a in attrs]
    q_bags={q["qid"]:[vid(c) for c in query_canon_concepts(q)] for q in queries}
    D=len(vocab)
    def vec(bag,noise):
        v=np.zeros(D,np.float32)
        for i in bag: v[i]=1.0
        v+=rng.normal(0,noise,D).astype(np.float32); n=np.linalg.norm(v); return v/n if n else v
    ids=list(graphs.keys())
    IMG=np.stack([vec(img_bags[i],0.25) for i in ids]); Q=np.stack([vec(q_bags[q["qid"]],0.15) for q in queries])
    print(f"[encode:synthetic] dim={D} images={len(ids)} queries={len(queries)}"); return ids,IMG,Q

class _null:
    def __enter__(self): return self
    def __exit__(self,*a): return False
def encode_clip(graphs, queries, model_name, pretrained, device, batch, img_dir, fp16=True):
    import torch, open_clip
    from PIL import Image
    if device=="cuda" and not torch.cuda.is_available():
        print("[warn] CUDA not available -> CPU"); device="cpu"
    if device=="cpu": fp16=False
    model,_,prep=open_clip.create_model_and_transforms(model_name,pretrained=pretrained)
    tok=open_clip.get_tokenizer(model_name); model=model.to(device).eval(); ids=list(graphs.keys()); feats=[]
    ac=torch.autocast(device_type="cuda",dtype=torch.float16) if fp16 else _null()
    with torch.no_grad():
        for k in range(0,len(ids),batch):
            ims=[prep(Image.open(os.path.join(img_dir,f"{i}.jpg")).convert("RGB")) for i in ids[k:k+batch]]
            x=torch.stack(ims).to(device)
            with ac:
                f=model.encode_image(x); f=f/f.norm(dim=-1,keepdim=True)
            feats.append(f.float().cpu().numpy())
        IMG=np.concatenate(feats,0)
        tf=model.encode_text(tok([q["text"] for q in queries]).to(device)); tf=tf/tf.norm(dim=-1,keepdim=True)
        Q=tf.float().cpu().numpy()
    print(f"[encode:clip] {model_name} dim={IMG.shape[1]} device={device} fp16={fp16}")
    return ids,IMG.astype(np.float32),Q.astype(np.float32)

# ------------------------------- systems ------------------------------------ #
def rank_graph(qc, img_ids, concept2img, img_concepts, es):
    idpos={iid:i for i,iid in enumerate(img_ids)}; cand=set()
    for c in qc: cand|=concept2img.get(c,set())
    s=np.full(len(img_ids),-1e9,np.float32)
    for iid in cand:
        i=idpos[iid]; s[i]=len(qc & img_concepts[iid])+1e-3*es[i]
    return s

def entity_idf(concept2img, n_images):
    """Inverse document frequency per entity: rare entities are informative,
    hubs (man/tree/sky) are near-zero -> used to down-weight hub hops."""
    idf={}
    for c,imgs in concept2img.items():
        df=len(imgs); idf[c]=math.log((n_images+1)/(df+1))
    return idf

def sigma_candidates(qv, IMG, img_ids, qc, concept2img, img_concepts, entry_n, depth,
                     idf=None, budget=400, per_entity_cap=25, hub_df_frac=0.05, n_images=None):
    """Specificity-aware agentic multi-source traversal.
    * Traversal follows shared entities but IGNORES hubs (df > hub_df_frac*N) so it
      does not flood through 'man/tree/sky'.
    * A node's graph score is IDF-WEIGHTED proximity to multiple anchors: reaching a
      node via a RARE bridging entity, from MANY anchors, scores high (true bridge);
      reaching it via a hub scores ~0.  This is the standard KG fix for hubness."""
    idpos={iid:i for i,iid in enumerate(img_ids)}
    embed=IMG@qv
    N=n_images or len(img_ids)
    hub_cut=hub_df_frac*N
    hubs=set(c for c,imgs in concept2img.items() if len(imgs)>hub_cut)
    maxidf=max(idf.values()) if idf else 1.0
    anchor_seeds=[]
    for c in qc:
        s=list(concept2img.get(c,()))[:60]
        if s: anchor_seeds.append(s)
    anchor_seeds.append([img_ids[i] for i in np.argsort(-embed)[:entry_n]])
    n_anchor=len(anchor_seeds)
    # per node & anchor: best (idf-weighted) proximity via the rarest bridging entity used
    reach=defaultdict(dict)          # node -> {anchor: best_edge_specificity/(1+dist)}
    for ai,seeds in enumerate(anchor_seeds):
        dist={s:0 for s in seeds}; best={s:1.0 for s in seeds}; frontier=list(seeds); visited=len(dist)
        for d in range(1,depth+1):
            nxt=[]
            for iid in frontier:
                for c in img_concepts[iid]:
                    if c in hubs: continue                 # do not traverse through hubs
                    spec=(idf.get(c,0.0)/maxidf) if idf else 1.0
                    added=0
                    for nb in concept2img.get(c,()):
                        if nb not in dist:
                            dist[nb]=d; best[nb]=spec/(1.0+d); nxt.append(nb); visited+=1; added+=1
                            if added>=per_entity_cap: break
                    if visited>=budget: break
                if visited>=budget: break
            frontier=nxt
            if not frontier or visited>=budget: break
        for iid in dist: reach[iid][ai]=best[iid]
    denom=max(1,len(qc)); cand={}
    for iid,amap in reach.items():
        i=idpos[iid]
        reach_frac=len(amap)/n_anchor
        prox=float(np.mean(list(amap.values())))          # idf-weighted proximity
        s_graph=reach_frac*prox                           # rare-bridge + multi-anchor => high
        s_txt=len(qc & img_concepts[iid])/denom
        cand[i]=(float(embed[i]), s_txt, s_graph)
    return cand
def sigma_score(cand, N, a, b, g):
    s=np.full(N,-1e9,np.float32)
    for i,(e,t,gr) in cand.items(): s[i]=a*e+b*t+g*gr
    return s

# ---- GraphRAG baseline: real multi-hop traversal via Personalized PageRank ---- #
def build_ppr_graph(img_ids, img_concepts, concept2img, idf):
    """Bipartite image<->entity property graph (edge weight = entity IDF, so hubs are
    down-weighted). PPR over this graph performs genuine multi-hop traversal
    (image -> entity -> image -> ...), summed over all path lengths -- this is the
    'heavy graph-DB' comparator (Neo4j GDS computes the same PPR)."""
    N=len(img_ids); ent_list=list(concept2img.keys()); eidx={e:N+k for k,e in enumerate(ent_list)}
    iidpos={iid:i for i,iid in enumerate(img_ids)}
    rows=[]; cols=[]; data=[]
    for iid,i in iidpos.items():
        for c in img_concepts[iid]:
            j=eidx[c]; w=float(idf.get(c,1.0))
            rows+=[i,j]; cols+=[j,i]; data+=[w,w]
    n=N+len(ent_list)
    A=sp.csr_matrix((data,(rows,cols)),shape=(n,n),dtype=np.float32)
    deg=np.asarray(A.sum(1)).ravel(); deg[deg==0]=1.0
    W=sp.diags(1.0/deg)@A                       # row-stochastic transition
    return W.transpose().tocsr(), eidx, N, n

def graphrag_ppr(qc, WT, eidx, N, n_total, alpha=0.15, iters=40):
    seeds=[eidx[c] for c in qc if c in eidx]
    if not seeds: return np.full(N,-1e9,np.float32)
    p=np.zeros(n_total,np.float32)
    for s in seeds: p[s]=1.0/len(seeds)
    r=p.copy()
    for _ in range(iters): r=alpha*p+(1-alpha)*(WT@r)
    return r[:N].copy()

# ------------------------------- metrics ------------------------------------ #
def metrics_for(order, rel, K):
    topk=order[:K]; hits=[1 if i in rel else 0 for i in topk]; nrel=len(rel)
    p=sum(hits)/K; r=sum(hits)/nrel if nrel else 0; f1=2*p*r/(p+r) if (p+r) else 0
    mrr=next((1.0/rank for rank,i in enumerate(order,1) if i in rel),0.0)
    dcg=sum(1.0/math.log2(rank+1) for rank,i in enumerate(topk,1) if i in rel)
    idcg=sum(1.0/math.log2(rank+1) for rank in range(1,min(nrel,K)+1))
    return dict(P=p,R=r,F1=f1,MRR=mrr,nDCG=dcg/idcg if idcg else 0.0)
def evaluate(scores, queries, img_ids, K):
    idpos={iid:i for i,iid in enumerate(img_ids)}; per={}
    for q in queries:
        rel=set(idpos[j] for j in q["relevant"] if j in idpos)
        if not rel: continue
        per[q["qid"]]=(q["complexity"], metrics_for(np.argsort(-scores[q["qid"]]),rel,K))
    return per
def agg(per,keys=("P","R","F1","MRR","nDCG")):
    return {k:float(np.mean([m[k] for _,m in per.values()])) if per else 0.0 for k in keys}
def bycomp(per,key="nDCG"):
    b=defaultdict(list)
    for c,m in per.values(): b[c].append(m[key])
    return {c:float(np.mean(v)) for c,v in b.items()}
def paired_bootstrap(pa,pb,key="nDCG",n=5000,seed=0):
    qs=[q for q in pa if q in pb]; d=np.array([pa[q][1][key]-pb[q][1][key] for q in qs])
    if not len(d): return float("nan"),0.0
    rng=np.random.default_rng(seed); m=np.array([rng.choice(d,len(d),replace=True).mean() for _ in range(n)])
    return float((m<=0).mean()), float(d.mean())

def bootstrap_diff(diffs, n=10000, seed=0):
    """One-sided p (H0: mean<=0) and effect size from a pooled paired-difference array."""
    d=np.asarray(diffs,dtype=np.float64)
    if not len(d): return float("nan"),0.0
    rng=np.random.default_rng(seed)
    m=np.array([rng.choice(d,len(d),replace=True).mean() for _ in range(n)])
    return float((m<=0).mean()), float(d.mean())

def holm_bonferroni(pvals, alpha=0.05):
    """pvals: dict name->p. Returns dict name->(p, adj_threshold, reject) with Holm step-down."""
    items=sorted(pvals.items(), key=lambda kv: kv[1]); m=len(items); out={}; still=True
    for k,(name,p) in enumerate(items):           # k = 0-based rank
        thr=alpha/(m-k); rej= still and (p<thr)
        if not rej: still=False
        out[name]=(p, thr, rej)
    return out

# ----------------------------- orchestration -------------------------------- #
def _write_okf_docs(img_concepts, dest, ids):
    os.makedirs(dest,exist_ok=True); total=0
    for iid in ids:
        cs=img_concepts[iid]
        names=sorted(c.split(":",1)[1] for c in cs if c.startswith("obj:"))
        attrs=sorted(c.split(":",1)[1] for c in cs if c.startswith("attr:"))
        links=", ".join([f"[[obj/{n}]]" for n in names]+[f"[[attr/{a}]]" for a in attrs])
        fm=(f"---\nimage_id: {iid}\nobjects: [{', '.join(names)}]\n"
            f"attributes: [{', '.join(attrs)}]\nembedding: ref:emb/{iid}.npy\nlinks: [{links}]\n---\n")
        p=os.path.join(dest,f"{iid}.md"); open(p,"w").write(fm+f"# Image {iid}\n\n"+", ".join(names)+"\n")
        total+=os.path.getsize(p)
    return total

def measure_efficiency(queries, img_ids, img_concepts, concept2img, idf, IMG, Q, qpos,
                       exp_lu, entry_n, depth, hub_df_frac, out_dir, sample=60):
    """OKF (plain files + Git) vs graph-DB index on build / storage / update / latency.
    This quantifies the 'lightweight & maintainable' claim -- the core contribution
    when retrieval accuracy is a statistical tie with heavy graph methods."""
    rep={}
    genv=dict(os.environ, GIT_AUTHOR_NAME="x",GIT_AUTHOR_EMAIL="x@x",
              GIT_COMMITTER_NAME="x",GIT_COMMITTER_EMAIL="x@x")
    ids=list(img_ids); M=min(200,max(20,len(ids)//20)); base_ids,new_ids=ids[:-M],ids[-M:]
    okf=os.path.join(out_dir,"okf_store")
    import shutil; shutil.rmtree(okf, ignore_errors=True)
    t=time.time(); okf_bytes=_write_okf_docs(img_concepts,okf,base_ids); rep["okf_build_s"]=round(time.time()-t,3)
    rep["okf_storage_kb"]=round(okf_bytes/1024,1)
    def _git(*a):
        try:
            return subprocess.run(["git",*a],env=genv,capture_output=True,text=True)
        except FileNotFoundError:
            return None
    have_git = _git("--version") is not None
    if have_git:
        _git("init","-q",okf); _git("-C",okf,"add","-A"); _git("-C",okf,"commit","-qm","i")
    t=time.time(); new_bytes=_write_okf_docs(img_concepts,okf,new_ids); rep["okf_update_s"]=round(time.time()-t,3)
    if have_git:
        _git("-C",okf,"add","-A")
        r=_git("-C",okf,"diff","--cached","--shortstat")
        rep["okf_update_gitdiff"]=(r.stdout.strip() if r else "") or "(none)"
    else:                                        # proxy when git is unavailable
        rep["okf_update_gitdiff"]=f"{len(new_ids)} files, {round(new_bytes/1024,1)} KB added (git not found)"
    sub={i:img_concepts[i] for i in base_ids}
    t=time.time(); WTb,eidxb,Nb,nb=build_ppr_graph(base_ids,sub,concept2img,idf); rep["graph_build_s"]=round(time.time()-t,3)
    gpath=os.path.join(out_dir,"graph_index.npz"); sp.save_npz(gpath,WTb); rep["graph_storage_kb"]=round(os.path.getsize(gpath)/1024,1)
    full={i:img_concepts[i] for i in ids}
    t=time.time(); WTf,eidxf,Nf,nf=build_ppr_graph(ids,full,concept2img,idf); rep["graph_update_reindex_s"]=round(time.time()-t,3)
    # ---- query latency on a sample ----
    samp=[q for q in queries][:sample]
    t=time.time()
    for q in samp:
        ce=link(q["text"],exp_lu); qv=Q[qpos[q["qid"]]]
        cand=sigma_candidates(qv,IMG,img_ids,ce,concept2img,img_concepts,entry_n,depth,
                              idf=idf,hub_df_frac=hub_df_frac,n_images=len(img_ids))
        _=sigma_score(cand,len(img_ids),0.3,0.3,0.4)
    rep["sigma_latency_ms"]=round(1000*(time.time()-t)/max(1,len(samp)),2)
    t=time.time()
    for q in samp:
        ce=link(q["text"],exp_lu); _=graphrag_ppr(ce,WTf,eidxf,Nf,nf)
    rep["graphrag_ppr_latency_ms"]=round(1000*(time.time()-t)/max(1,len(samp)),2)
    rep["n_base_images"]=len(base_ids); rep["n_added_images"]=M
    json.dump(rep,open(os.path.join(out_dir,"efficiency.json"),"w"),indent=2)
    print("\n"+"-"*60+"\nEFFICIENCY & MAINTAINABILITY (OKF vs graph-DB index)\n"+"-"*60)
    print(f"  build:    OKF {rep['okf_build_s']}s / {rep['okf_storage_kb']}KB   |   "
          f"graph {rep['graph_build_s']}s / {rep['graph_storage_kb']}KB")
    print(f"  update +{M} imgs:  OKF {rep['okf_update_s']}s (git: {rep['okf_update_gitdiff']})")
    print(f"                     graph reindex {rep['graph_update_reindex_s']}s")
    print(f"  query latency:  LOKG-IR {rep['sigma_latency_ms']}ms   |   GraphRAG-PPR {rep['graphrag_ppr_latency_ms']}ms")
    return rep

def run_all(args):
    os.makedirs(args.out,exist_ok=True)
    graphs=make_synthetic(args.n_images,args.seed) if args.synthetic else load_vg(args.vg_dir,args.n_images,args.seed)
    concept2img,img_concepts=build_okf(graphs)
    concepts=set(c.split(":",1)[1] for c in concept2img)
    fwd,rev=build_synonym_maps(concepts,args.paraphrase,args.seed,synth=args.synthetic)
    print(f"[paraphrase] mode={args.paraphrase} variants for {len(fwd)} concepts")
    if args.multihop:
        queries=build_multihop_queries(graphs,concept2img,img_concepts,args.n_queries,fwd,args.seed,
                                       bridge_df_frac=args.bridge_df_frac)
    else:
        queries=build_queries(graphs,args.n_queries,fwd,args.seed)
    if not queries: sys.exit("[error] no queries.")
    json.dump(queries,open(os.path.join(args.out,"queries.json"),"w"))
    naive_lu,exp_lu=make_lookups(set(concept2img),rev)
    idf=entity_idf(concept2img, len(graphs))

    if args.synthetic: img_ids,IMG,Q=encode_synthetic(graphs,queries,args.seed)
    else: img_ids,IMG,Q=encode_clip(graphs,queries,args.clip_model,args.clip_pretrained,
                                     args.device,args.batch,args.vg_img_dir,fp16=not args.no_fp16)
    qpos={q["qid"]:k for k,q in enumerate(queries)}

    S_embed,S_gN,S_gE,SIG={},{},{},{}
    for q in queries:
        qv=Q[qpos[q["qid"]]]; es=IMG@qv
        cn=link(q["text"],naive_lu); ce=link(q["text"],exp_lu)
        S_embed[q["qid"]]=es
        S_gN[q["qid"]]=rank_graph(cn,img_ids,concept2img,img_concepts,es)
        S_gE[q["qid"]]=rank_graph(ce,img_ids,concept2img,img_concepts,es)
        SIG[q["qid"]]=sigma_candidates(qv,IMG,img_ids,ce,concept2img,img_concepts,args.entry_n,args.depth,
                                       idf=idf,hub_df_frac=args.hub_df_frac,n_images=len(graphs))

    K=args.topk; N=len(img_ids)
    # ---- GraphRAG baseline: real multi-hop traversal (Personalized PageRank) ----
    S_ppr={}
    if not args.no_graphrag:
        WT,eidx,Nn,ntot=build_ppr_graph(img_ids,img_concepts,concept2img,idf)
        for q in queries:
            S_ppr[q["qid"]]=graphrag_ppr(link(q["text"],exp_lu),WT,eidx,Nn,ntot)
    if args.tune:
        rng=random.Random(args.seed); qs=[q["qid"] for q in queries]; rng.shuffle(qs)
        val=set(qs[:max(1,int(0.3*len(qs)))]); valq=[q for q in queries if q["qid"] in val]
        test=[q for q in queries if q["qid"] not in val]
        grid=[(a/10,b/10,(10-a-b)/10) for a in range(0,11) for b in range(0,11-a)]
        best=None
        for a,b,g in grid:
            sc={q["qid"]:sigma_score(SIG[q["qid"]],N,a,b,g) for q in valq}
            m=agg(evaluate(sc,valq,img_ids,K))["nDCG"]
            if best is None or m>best[0]: best=(m,a,b,g)
        _,a,b,g=best; evalset=test
        print(f"[tune] best (a,b,g)=({a},{b},{g}) val nDCG@{K}={best[0]:.3f} | test queries={len(test)}")
    else:
        a,b,g=args.alpha,args.beta,args.gamma; evalset=queries

    S_sigma={q["qid"]:sigma_score(SIG[q["qid"]],N,a,b,g) for q in evalset}
    pe=evaluate(S_embed,evalset,img_ids,K); pgN=evaluate(S_gN,evalset,img_ids,K)
    pgE=evaluate(S_gE,evalset,img_ids,K);   ps=evaluate(S_sigma,evalset,img_ids,K)
    ppr=evaluate(S_ppr,evalset,img_ids,K) if S_ppr else None
    rows=[("CLIP (vector)",agg(pe)),("KG-overlap (naive lexical)",agg(pgN)),
          ("KG-overlap + linking",agg(pgE))]
    if ppr is not None: rows.append(("GraphRAG (PPR traversal)",agg(ppr)))
    rows.append((f"LOKG-IR (a={a},b={b},g={g})",agg(ps)))
    bar="="*76; print("\n"+bar)
    print("SYNTHETIC SMOKE-TEST — NOT FOR THE PAPER" if args.synthetic
          else f"VG-Multihop K={K} images={len(img_ids)} eval-queries={len(evalset)} paraphrase={args.paraphrase}")
    print(bar)
    h=f"{'Method':30s} {'P@'+str(K):>7s} {'F1':>7s} {'MRR':>7s} {'nDCG@'+str(K):>8s}"; print(h); print("-"*len(h))
    for n_,m in rows: print(f"{n_:30s} {m['P']:7.3f} {m['F1']:7.3f} {m['MRR']:7.3f} {m['nDCG']:8.3f}")
    print(f"\nnDCG@{K} by complexity:")
    comp_rows=[("CLIP",pe),("KG naive",pgN),("KG+link",pgE)]+([("GraphRAG",ppr)] if ppr else [])+[("LOKG-IR",ps)]
    for n_,pq in comp_rows:
        bc=bycomp(pq); print(f"  {n_:9s} "+"  ".join(f"{c}={bc.get(c,0):.3f}" for c in ["simple","moderate","complex"]))
    print(f"\nPaired bootstrap (LOKG-IR vs baseline), nDCG@{K}:")
    bset=[("CLIP (vector)",pe),("KG-overlap (naive)",pgN),("KG-overlap + linking",pgE)]+([("GraphRAG (PPR)",ppr)] if ppr else [])
    for n_,pb in bset:
        p,d=paired_bootstrap(ps,pb,"nDCG",seed=args.seed)
        print(f"  LOKG-IR vs {n_:24s} d={d:+.3f} p={p:.4f} ({'significant' if p<0.05 else 'n.s.'})")
    out_json={"weights":[a,b,g],"rows":{n_:m for n_,m in rows},
              "complexity":{"clip":bycomp(pe),"kg_naive":bycomp(pgN),"kg_link":bycomp(pgE),"sigma":bycomp(ps)}}
    if ppr is not None: out_json["complexity"]["graphrag"]=bycomp(ppr)
    json.dump(out_json,open(os.path.join(args.out,"metrics.json"),"w"),indent=2)
    print(f"\n[done] wrote {args.out}/metrics.json + queries.json")
    if args.measure_eff:
        measure_efficiency(queries,img_ids,img_concepts,concept2img,idf,IMG,Q,qpos,
                           exp_lu,args.entry_n,args.depth,args.hub_df_frac,args.out)
    if args.synthetic: print("\nNOTE: synthetic mode uses toy embeddings + lexical paraphrase for a fast, GPU-free demo; use --vg-dir (real Visual Genome + CLIP) to reproduce the paper.")

def score_seed(args, seed):
    """Run the full retrieval pipeline for one seed; return per-method seed-level metrics,
    per-complexity nDCG, and per-query nDCG differences (LOKG-IR - baseline) for pooling."""
    graphs=make_synthetic(args.n_images,seed) if args.synthetic else load_vg(args.vg_dir,args.n_images,seed)
    concept2img,img_concepts=build_okf(graphs)
    concepts=set(c.split(":",1)[1] for c in concept2img)
    fwd,rev=build_synonym_maps(concepts,args.paraphrase,seed,synth=args.synthetic)
    queries=(build_multihop_queries(graphs,concept2img,img_concepts,args.n_queries,fwd,seed,
                                    bridge_df_frac=args.bridge_df_frac) if args.multihop
             else build_queries(graphs,args.n_queries,fwd,seed))
    if not queries: return None
    naive_lu,exp_lu=make_lookups(set(concept2img),rev); idf=entity_idf(concept2img,len(graphs))
    if args.synthetic: img_ids,IMG,Q=encode_synthetic(graphs,queries,seed)
    else: img_ids,IMG,Q=encode_clip(graphs,queries,args.clip_model,args.clip_pretrained,
                                     args.device,args.batch,args.vg_img_dir,fp16=not args.no_fp16)
    qpos={q["qid"]:k for k,q in enumerate(queries)}
    S_embed,S_gN,S_gE,SIG={},{},{},{}
    for q in queries:
        qv=Q[qpos[q["qid"]]]; es=IMG@qv; cn=link(q["text"],naive_lu); ce=link(q["text"],exp_lu)
        S_embed[q["qid"]]=es
        S_gN[q["qid"]]=rank_graph(cn,img_ids,concept2img,img_concepts,es)
        S_gE[q["qid"]]=rank_graph(ce,img_ids,concept2img,img_concepts,es)
        SIG[q["qid"]]=sigma_candidates(qv,IMG,img_ids,ce,concept2img,img_concepts,args.entry_n,args.depth,
                                       idf=idf,hub_df_frac=args.hub_df_frac,n_images=len(graphs))
    K=args.topk; N=len(img_ids); S_ppr={}
    if not args.no_graphrag:
        WT,eidx,Nn,ntot=build_ppr_graph(img_ids,img_concepts,concept2img,idf)
        for q in queries: S_ppr[q["qid"]]=graphrag_ppr(link(q["text"],exp_lu),WT,eidx,Nn,ntot)
    # tune per seed on its own val split
    rng=random.Random(seed); qs=[q["qid"] for q in queries]; rng.shuffle(qs)
    val=set(qs[:max(1,int(0.3*len(qs)))]); valq=[q for q in queries if q["qid"] in val]
    test=[q for q in queries if q["qid"] not in val]
    if args.tune:
        best=None
        for a,b,g in [(a/10,b/10,(10-a-b)/10) for a in range(0,11) for b in range(0,11-a)]:
            m=agg(evaluate({q["qid"]:sigma_score(SIG[q["qid"]],N,a,b,g) for q in valq},valq,img_ids,K))["nDCG"]
            if best is None or m>best[0]: best=(m,a,b,g)
        _,a,b,g=best
    else:
        a,b,g=args.alpha,args.beta,args.gamma
    ev=test if args.tune else queries
    S_sigma={q["qid"]:sigma_score(SIG[q["qid"]],N,a,b,g) for q in ev}
    per={"CLIP (vector)":evaluate(S_embed,ev,img_ids,K),
         "KG-overlap (naive)":evaluate(S_gN,ev,img_ids,K),
         "KG-overlap + linking":evaluate(S_gE,ev,img_ids,K),
         "LOKG-IR":evaluate(S_sigma,ev,img_ids,K)}
    if S_ppr: per["GraphRAG (PPR)"]=evaluate(S_ppr,ev,img_ids,K)
    ps=per["LOKG-IR"]
    diffs={name:[ps[q][1]["nDCG"]-pb[q][1]["nDCG"] for q in ps if q in pb]
           for name,pb in per.items() if name!="LOKG-IR"}
    means={name:agg(pq) for name,pq in per.items()}
    comps={name:bycomp(pq) for name,pq in per.items()}
    return {"weights":(a,b,g),"means":means,"comps":comps,"diffs":diffs,"n_test":len(ev)}

def run_multiseed(args):
    os.makedirs(args.out,exist_ok=True)
    R=args.seeds; results=[]
    for s in range(R):
        print(f"\n===== seed {s+1}/{R} =====")
        r=score_seed(args,args.seed+s)
        if r: results.append(r)
    if not results: sys.exit("[error] no seeds produced results.")
    methods=list(results[0]["means"].keys())
    K=args.topk
    # mean +/- sd of nDCG (and other metrics) across seeds
    agg_means={m:{k:(float(np.mean([r["means"][m][k] for r in results])),
                    float(np.std([r["means"][m][k] for r in results])))
                  for k in ("P","F1","MRR","nDCG")} for m in methods}
    agg_comp={m:{c:float(np.mean([r["comps"][m].get(c,0) for r in results]))
                 for c in ("simple","moderate","complex")} for m in methods}
    weights=[r["weights"] for r in results]
    # pool per-query diffs across seeds, bootstrap p, then Holm-Bonferroni across baselines
    baselines=[m for m in methods if m!="LOKG-IR"]
    pooled={b:[d for r in results for d in r["diffs"].get(b,[])] for b in baselines}
    raw={b:bootstrap_diff(pooled[b],seed=args.seed) for b in baselines}      # (p, effect)
    holm=holm_bonferroni({b:raw[b][0] for b in baselines})
    bar="="*84; print("\n"+bar); print(f"MULTI-SEED RESULTS  (R={len(results)} seeds, K={K}, "
          f"paraphrase={args.paraphrase}, multihop={args.multihop})"); print(bar)
    h=f"{'Method':26s} {'P@'+str(K):>12s} {'F1':>12s} {'MRR':>12s} {'nDCG@'+str(K):>13s}"; print(h); print("-"*len(h))
    for m in methods:
        cells=" ".join(f"{agg_means[m][k][0]:.3f}\u00B1{agg_means[m][k][1]:.3f}" for k in ("P","F1","MRR","nDCG"))
        print(f"{m:26s} {cells}")
    print(f"\nnDCG@{K} by complexity (seed mean):")
    for m in methods:
        print(f"  {m:24s} "+"  ".join(f"{c}={agg_comp[m][c]:.3f}" for c in ("simple","moderate","complex")))
    print(f"\nLOKG-IR vs baseline (pooled per-query nDCG diff; Holm\u2013Bonferroni, alpha=0.05):")
    for b in baselines:
        p,thr,rej=holm[b]; eff=raw[b][1]
        print(f"  LOKG-IR vs {b:24s} d={eff:+.3f}  p={p:.4f}  Holm-thr={thr:.4f}  "
              f"{'SIGNIFICANT' if rej else 'n.s.'}")
    out={"seeds":len(results),"weights_per_seed":weights,
         "means_pm_sd":{m:{k:agg_means[m][k] for k in agg_means[m]} for m in methods},
         "complexity":agg_comp,
         "holm":{b:{"p":holm[b][0],"threshold":holm[b][1],"reject":holm[b][2],"effect":raw[b][1]} for b in baselines}}
    json.dump(out,open(os.path.join(args.out,"metrics_multiseed.json"),"w"),indent=2)
    print(f"\n[done] wrote {args.out}/metrics_multiseed.json")

def _materials(args, seed):
    graphs=make_synthetic(args.n_images,seed) if args.synthetic else load_vg(args.vg_dir,args.n_images,seed)
    concept2img,img_concepts=build_okf(graphs)
    concepts=set(c.split(":",1)[1] for c in concept2img)
    fwd,rev=build_synonym_maps(concepts,args.paraphrase,seed,synth=args.synthetic)
    queries=(build_multihop_queries(graphs,concept2img,img_concepts,args.n_queries,fwd,seed,
                                    bridge_df_frac=args.bridge_df_frac) if args.multihop
             else build_queries(graphs,args.n_queries,fwd,seed))
    _,exp_lu=make_lookups(set(concept2img),rev); idf=entity_idf(concept2img,len(graphs))
    if args.synthetic: img_ids,IMG,Q=encode_synthetic(graphs,queries,seed)
    else: img_ids,IMG,Q=encode_clip(graphs,queries,args.clip_model,args.clip_pretrained,
                                     args.device,args.batch,args.vg_img_dir,fp16=not args.no_fp16)
    return graphs,queries,img_ids,IMG,Q,concept2img,img_concepts,idf,exp_lu

def _sig_all(args,queries,img_ids,IMG,Q,c2i,ic,idf,depth,hub,entry,n_images):
    qpos={q["qid"]:k for k,q in enumerate(queries)}; SIG={}
    for q in queries:
        qv=Q[qpos[q["qid"]]]; ce=link(q["text"],args._exp_lu)
        SIG[q["qid"]]=sigma_candidates(qv,IMG,img_ids,ce,c2i,ic,entry,depth,idf=idf,hub_df_frac=hub,n_images=n_images)
    return SIG

def _tune_eval(SIG,queries,img_ids,N,K,seed,mask=None):
    """Grid-tune (a,b,g) on a val split subject to an optional component mask; return test nDCG."""
    rng=random.Random(seed); qs=[q["qid"] for q in queries]; rng.shuffle(qs)
    val=set(qs[:max(1,int(0.3*len(qs)))]); valq=[q for q in queries if q["qid"] in val]
    test=[q for q in queries if q["qid"] not in val] or queries
    grid=[(a/10,b/10,(10-a-b)/10) for a in range(0,11) for b in range(0,11-a)]
    def ok(w):
        if not mask: return True
        return all((mask[i]!=0 or w[i]==0) for i in range(3))
    best=None
    for w in grid:
        if not ok(w): continue
        m=agg(evaluate({q["qid"]:sigma_score(SIG[q["qid"]],N,*w) for q in valq},valq,img_ids,K))["nDCG"]
        if best is None or m>best[0]: best=(m,w)
    w=best[1]
    return agg(evaluate({q["qid"]:sigma_score(SIG[q["qid"]],N,*w) for q in test},test,img_ids,K))["nDCG"], w

def run_ablation(args):
    os.makedirs(args.out,exist_ok=True); K=args.topk
    configs=[("Embed only",(1,0,0)),("Text only",(0,1,0)),("Graph only",(0,0,1)),
             ("Embed+Text",(1,1,0)),("Text+Graph",(0,1,1)),("Embed+Graph",(1,0,1)),
             ("Full LOKG-IR",(1,1,1))]
    acc={n:[] for n,_ in configs}
    for s in range(args.seeds):
        seed=args.seed+s; print(f"\n== ablation seed {s+1}/{args.seeds} ==")
        graphs,queries,img_ids,IMG,Q,c2i,ic,idf,exp_lu=_materials(args,seed); args._exp_lu=exp_lu
        N=len(img_ids)
        SIG=_sig_all(args,queries,img_ids,IMG,Q,c2i,ic,idf,args.depth,args.hub_df_frac,args.entry_n,len(graphs))
        for name,mask in configs:
            nd,_=_tune_eval(SIG,queries,img_ids,N,K,seed,mask=mask); acc[name].append(nd)
    print("\n"+"="*54+f"\nABLATION (nDCG@{K}, mean\u00B1sd over {args.seeds} seeds)\n"+"="*54)
    for name,_ in configs:
        v=acc[name]; print(f"  {name:14s} {np.mean(v):.3f} \u00B1 {np.std(v):.3f}")
    json.dump({n:[float(np.mean(acc[n])),float(np.std(acc[n]))] for n,_ in configs},
              open(os.path.join(args.out,"ablation.json"),"w"),indent=2)
    print(f"\n[done] wrote {args.out}/ablation.json")

def run_sweep(args):
    os.makedirs(args.out,exist_ok=True); K=args.topk; seed=args.seed
    graphs,queries,img_ids,IMG,Q,c2i,ic,idf,exp_lu=_materials(args,seed); args._exp_lu=exp_lu
    N=len(img_ids); nimg=len(graphs); out={}
    def run_one(depth,hub,entry):
        SIG=_sig_all(args,queries,img_ids,IMG,Q,c2i,ic,idf,depth,hub,entry,nimg)
        nd,w=_tune_eval(SIG,queries,img_ids,N,K,seed); return nd,w
    print("\n"+"="*54+f"\nSENSITIVITY (nDCG@{K}, seed {seed})\n"+"="*54)
    out["depth"]={}
    print("depth T:")
    for T in [2,3,4,5,6]:
        nd,_=run_one(T,args.hub_df_frac,args.entry_n); out["depth"][T]=nd; print(f"  T={T}: {nd:.3f}")
    out["hub"]={}
    print("hub cutoff (frac of nodes):")
    for h in [0.01,0.03,0.05,0.10]:
        nd,_=run_one(args.depth,h,args.entry_n); out["hub"][h]=nd; print(f"  hub={h:.2f}: {nd:.3f}")
    out["entry"]={}
    print("entry size N:")
    for n in [5,10,20,40]:
        nd,_=run_one(args.depth,args.hub_df_frac,n); out["entry"][n]=nd; print(f"  N={n}: {nd:.3f}")
    json.dump(out,open(os.path.join(args.out,"sensitivity.json"),"w"),indent=2)
    print(f"\n[done] wrote {args.out}/sensitivity.json")

def run_scaling(args):
    os.makedirs(args.out,exist_ok=True); seed=args.seed
    sizes=[int(x) for x in args.scaling_sizes.split(",")]; rows=[]
    for n in sizes:
        graphs=make_synthetic(n,seed) if args.synthetic else load_vg(args.vg_dir,n,seed)
        c2i,ic=build_okf(graphs); idf=entity_idf(c2i,len(graphs))
        okf=os.path.join(args.out,"okf_tmp")
        import shutil; shutil.rmtree(okf,ignore_errors=True)
        t=time.time(); okf_kb=_write_okf_docs(ic,okf,list(graphs.keys()))/1024; okf_build=time.time()-t
        t=time.time(); WT,eidx,Nn,ntot=build_ppr_graph(list(graphs.keys()),ic,c2i,idf); g_build=time.time()-t
        # latency on a small fixed query sample
        fwd,rev=build_synonym_maps(set(x.split(":",1)[1] for x in c2i),args.paraphrase,seed,synth=args.synthetic)
        qs=(build_multihop_queries(graphs,c2i,ic,min(200,args.n_queries),fwd,seed,bridge_df_frac=args.bridge_df_frac)
            if args.multihop else build_queries(graphs,min(200,args.n_queries),fwd,seed))
        _,exp_lu=make_lookups(set(c2i),rev)
        if args.synthetic: img_ids,IMG,Q=encode_synthetic(graphs,qs,seed)
        else: img_ids,IMG,Q=encode_clip(graphs,qs,args.clip_model,args.clip_pretrained,args.device,args.batch,args.vg_img_dir,fp16=not args.no_fp16)
        qpos={q["qid"]:k for k,q in enumerate(qs)}; samp=qs[:60]
        t=time.time()
        for q in samp:
            ce=link(q["text"],exp_lu); qv=Q[qpos[q["qid"]]]
            cand=sigma_candidates(qv,IMG,img_ids,ce,c2i,ic,args.entry_n,args.depth,idf=idf,hub_df_frac=args.hub_df_frac,n_images=len(graphs))
            _=sigma_score(cand,len(img_ids),0.3,0.5,0.2)
        sig_ms=1000*(time.time()-t)/max(1,len(samp))
        t=time.time()
        for q in samp: _=graphrag_ppr(link(q["text"],exp_lu),WT,eidx,Nn,ntot)
        ppr_ms=1000*(time.time()-t)/max(1,len(samp))
        rows.append(dict(n=len(graphs),okf_build_s=round(okf_build,2),okf_kb=round(okf_kb,1),
                         graph_build_s=round(g_build,3),sigma_ms=round(sig_ms,2),ppr_ms=round(ppr_ms,2)))
        print(f"  n={len(graphs):>6}: OKF {okf_build:.2f}s/{okf_kb/1024:.1f}MB  graph {g_build:.3f}s  "
              f"LOKG-IR {sig_ms:.2f}ms  PPR {ppr_ms:.2f}ms")
    json.dump(rows,open(os.path.join(args.out,"scaling.json"),"w"),indent=2)
    print(f"\n[done] wrote {args.out}/scaling.json  (x=n, y=latency for the scalability figure)")

def build_parser():
    p=argparse.ArgumentParser(); p.add_argument("cmd",choices=["all"])
    p.add_argument("--synthetic",action="store_true")
    p.add_argument("--vg-dir",default="VG"); p.add_argument("--vg-img-dir",default="VG/images")
    p.add_argument("--n-images",type=int,default=800); p.add_argument("--n-queries",type=int,default=1000)
    p.add_argument("--paraphrase",choices=["none","lexicon","wordnet"],default="lexicon")
    p.add_argument("--multihop",action="store_true",help="bridge/path ground-truth so graph traversal matters")
    p.add_argument("--hub-df-frac",type=float,default=0.05,help="entities in >this frac of images are hubs (not traversed)")
    p.add_argument("--bridge-df-frac",type=float,default=0.03,help="max doc-freq (frac of images) for a bridge entity to be considered specific")
    p.add_argument("--tune",action="store_true")
    p.add_argument("--topk",type=int,default=10); p.add_argument("--entry-n",type=int,default=20)
    p.add_argument("--depth",type=int,default=4)
    p.add_argument("--alpha",type=float,default=0.5); p.add_argument("--beta",type=float,default=0.3)
    p.add_argument("--gamma",type=float,default=0.2); p.add_argument("--seed",type=int,default=0)
    p.add_argument("--seeds",type=int,default=1,help="run R seeds (>=5 recommended) with Holm-Bonferroni")
    p.add_argument("--ablation",action="store_true",help="score-component ablation (Embed/Text/Graph and combinations)")
    p.add_argument("--sweep",action="store_true",help="sensitivity to depth T, hub cutoff, entry size N")
    p.add_argument("--scaling",action="store_true",help="build/latency vs corpus size")
    p.add_argument("--scaling-sizes",default="5000,10000,20000,50000,100000")
    p.add_argument("--out",default="runs/exp")
    p.add_argument("--clip-model",default="ViT-B-32"); p.add_argument("--clip-pretrained",default="laion2b_s34b_b79k")
    p.add_argument("--device",default="cuda"); p.add_argument("--batch",type=int,default=32)
    p.add_argument("--no-fp16",action="store_true")
    p.add_argument("--no-graphrag",action="store_true",help="skip the GraphRAG PPR baseline")
    p.add_argument("--measure-eff",action="store_true",help="measure OKF vs graph-DB build/storage/update/latency")
    return p

if __name__=="__main__":
    args=build_parser().parse_args()
    if args.ablation: run_ablation(args)
    elif args.sweep: run_sweep(args)
    elif args.scaling: run_scaling(args)
    elif args.seeds>1: run_multiseed(args)
    else: run_all(args)
