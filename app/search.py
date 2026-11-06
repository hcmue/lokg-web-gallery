"""CPU-friendly search over teacher-supplied link keywords and LOKG graph core."""
from __future__ import annotations
import math
import threading
from collections import Counter
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from .lokg_engine import LOKGRetriever
from .search_aliases import normalize, tokens, detect


def item_output(row:dict,score:float=0,detail:dict|None=None,engine='lokg'):
    data={k:row.get(k) for k in ('id','title','page_url','description','category','tags','components','created_at','updated_at','links')}
    data.update(score=round(float(score),4),breakdown=detail or {},engine=engine)
    return data

STOPWORDS={'giao','dien','web','mau','trang','co','voi','va','theo','cho','cua','phia'}

class SearchIndex:
    def __init__(self,items:list[dict]):
        self.lock=threading.RLock()
        self.rebuild(items)

    def rebuild(self,items:list[dict]):
        with self.lock:
            self.records=sorted(items,key=lambda x:x['id'])
            self.doc_texts=[' '.join([x.get('title',''),' '.join(x.get('tags',[])),x.get('description',''),
                                      x.get('category',''),' '.join(x.get('components',[]))]) for x in self.records]
            self.tokens=[tokens(t) for t in self.doc_texts]
            self.lengths=[len(t) for t in self.tokens]
            self.av_len=max(1,sum(self.lengths)/max(1,len(self.lengths)))
            self.tf=[Counter(t) for t in self.tokens]
            self.df=Counter()
            for t in self.tokens:self.df.update(set(t))
            self.vectorizer=TfidfVectorizer(analyzer='char_wb',ngram_range=(3,5),sublinear_tf=True)
            self.vectors=self.vectorizer.fit_transform([normalize(t) or 'empty' for t in self.doc_texts]) if self.records else None
            self.lokg=LOKGRetriever(self.records)

    def _bm25(self,q:str):
        N=len(self.records)
        result=[]
        for i,tf in enumerate(self.tf):
            s=0
            for term in set(tokens(q))-STOPWORDS:
                freq=tf[term]
                df=self.df.get(term,0)
                if not freq:continue
                idf=math.log(1+(N-df+.5)/(df+.5))
                s+=idf*freq*2.2/(freq+1.2*(.25+.75*self.lengths[i]/self.av_len))
            result.append(s)
        return result

    def search(self,query:str,mode:str='lokg',limit:int=24,offset:int=0):
        q=query.strip()
        with self.lock:
            if mode not in ('lokg','bm25','vector'):
                raise ValueError('Chế độ tìm kiếm không hợp lệ.')
            if len(q)>300:raise ValueError('Truy vấn tối đa 300 ký tự.')
            if not q:
                out=sorted(self.records,key=lambda r:(r.get('created_at',''),r['id']),reverse=True)
                return [item_output(d,engine='browse') for d in out[offset:offset+limit]],len(out)
            if mode=='lokg':
                # Do not return every graph-adjacent page for an unrelated query.
                # At least one explicit metadata concept/token must be recognizable.
                meaningful=set(tokens(q))-STOPWORDS
                cats,comps,_=detect(q)
                observed=any(meaningful.intersection(set(tok)) for tok in self.tokens)
                observed=observed or any(cats.intersection({row.get('category')}) or
                        comps.intersection(set(row.get('components',[]))) for row in self.records)
                if not observed:
                    return [],0
                ranked=self.lokg.rank(q)
                max_score=max((v['score'] for v in ranked.values()),default=0)
                cutoff=max(.10,.30*max_score)
                results=[]
                for d in self.records:
                    r=ranked.get(d['id'])
                    if r and r['score']>=cutoff:
                        results.append(item_output(d,r['score'],r['breakdown'],'lokg'))
            elif mode=='bm25':
                scores=self._bm25(q)
                results=[item_output(d,s,{'bm25':round(s,4)},mode) for d,s in zip(self.records,scores) if s>0]
            else:
                scores=cosine_similarity(self.vectorizer.transform([normalize(q)]),self.vectors).ravel() if self.vectors is not None else []
                results=[item_output(d,s,{'text_vector':round(float(s),4)},mode) for d,s in zip(self.records,scores) if s>0]
            results.sort(key=lambda x:(-x['score'],x['id']))
            return results[offset:offset+limit],len(results)
