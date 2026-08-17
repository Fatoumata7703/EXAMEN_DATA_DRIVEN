from __future__ import annotations
import hashlib, json
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np, pandas as pd
from src.config.settings import PROJECT_ROOT

ROOT=PROJECT_ROOT/"data"/"processed"/"final"; OUT=PROJECT_ROOT/"models"/"advanced"/"recommendation_ranking"; SEED=42

def stats(f):
    co=defaultdict(Counter); pop=Counter(); cats=defaultdict(Counter)
    for _,g in f.groupby('order_id'):
        items=list(dict.fromkeys(g.produit_key)); pop.update(items)
        for x in items: co[x].update(y for y in items if y!=x)
        for c,gg in g.groupby('categorie'): cats[c].update(gg.produit_key)
    return co,pop,cats

def ranked(ctx, cat, co, pop, cats, mode):
    s=Counter()
    if mode in ('cooccurrence','bm25','association','rrf'):
        for x in ctx:
            for y,v in co.get(x,{}).items():
                if y not in ctx:
                    z=float(v)
                    if mode=='bm25': z=z/(1+np.log1p(pop[y]))
                    if mode=='association': z=z/max(pop[y],1)
                    s[y]+=z
    if mode in ('category','rrf'):
        for y,v in cats.get(cat,{}).items():
            if y not in ctx: s[y]+=0.25*v if mode=='rrf' else v
    if mode=='global': s=Counter({y:float(v) for y,v in pop.items() if y not in ctx})
    if mode=='reference':
        # Historical complement reference is represented by category popularity
        # on this same leave-one-item-out population.
        for y,v in cats.get(cat,{}).items():
            if y not in ctx: s[y]+=v
    if not s: s=Counter({y:float(v) for y,v in pop.items() if y not in ctx})
    return sorted(s,key=lambda y:(-s[y],y))[:50]

def one_metrics(rows, k):
    vals=[]
    for _,g in rows.groupby(['order_id','target']):
        rel={x:int(y) for x,y in zip(g.item,g.label)}; ranked_items=list(g.sort_values('rank').item)
        top=ranked_items[:k]; hit=int(any(rel.get(x,0) for x in top)); pos=next((i for i,x in enumerate(ranked_items) if rel.get(x,0)),None)
        dcg=sum(rel.get(x,0)/np.log2(i+2) for i,x in enumerate(top)); vals.append((hit,dcg,1/(pos+1) if pos is not None else 0))
    a=np.asarray(vals) if vals else np.zeros((1,3)); return float(a[:,0].mean()),float(a[:,1].mean()),float(a[:,2].mean())

def main():
    o=pd.read_parquet(ROOT/'order_baskets.parquet'); o.date_commande=pd.to_datetime(o.date_commande); m=o.groupby('order_id').filter(lambda x:x.produit_key.nunique()>=2)
    dates=m.groupby('order_id').date_commande.min().sort_values(); chunks=np.array_split(dates.index.to_numpy(),4)
    out=[]; metric=[]; units=[]
    modes=['reference','global','category','cooccurrence','bm25','association','rrf']
    for w in (2,3,4):
        ids=set(chunks[w-1].tolist()); test=m[m.order_id.isin(ids)]; train=m[m.date_commande.lt(test.date_commande.min())]; co,pop,cats=stats(train)
        for oid,g in test.groupby('order_id'):
            items=list(dict.fromkeys(g.produit_key))
            # One deterministic masked target per order (the first item in
            # stable product order) keeps the end-to-end unit at command level.
            for target in [sorted(items)[0]]:
                ctx=set(items)-{target}; cat=str(g.loc[g.produit_key.eq(target),'categorie'].iloc[0]); union=ranked(ctx,cat,co,pop,cats,'rrf')
                for mode in modes:
                    rr=union if mode=='rrf' else ranked(ctx,cat,co,pop,cats,mode)
                    for rank,item in enumerate(rr[:20],1):
                        out.append({'order_id':oid,'window':w,'target':target,'context_items':json.dumps(sorted(ctx)),'candidate_set':json.dumps(union),'model':mode,'item':item,'rank':rank,'label':int(item==target),'score':1/rank})
                units.append({'order_id':oid,'window':w,'target':target})
    pred=pd.DataFrame(out); pred.to_parquet(OUT/'complement_topk_predictions.parquet',index=False)
    for (w,model),g in pred.groupby(['window','model']):
        rec5,nd5,_=one_metrics(g[g['rank']<=5],5); rec10,nd10,map10=one_metrics(g[g['rank']<=10],10); rec20,nd20,_=one_metrics(g[g['rank']<=20],20)
        n=int(g[['order_id','target']].drop_duplicates().shape[0]); unique=int(g[g['rank']<=10].item.nunique()); div=float(g[g['rank']<=10].groupby('order_id').item.nunique().mean());
        metric.append({'window':w,'model':model,'n_targets':n,'recall@5':rec5,'recall@10':rec10,'recall@20':rec20,'ndcg@5':nd5,'ndcg@10':nd10,'ndcg@20':nd20,'map@10':map10,'mrr':one_metrics(g[g['rank']<=10],10)[2],'hitrate@10':rec10,'coverage_catalogue':unique/300.0,'diversity':div})
    md=pd.DataFrame(metric); md.to_csv(OUT/'complement_end_to_end_metrics.csv',index=False)
    # Stratified bootstrap of RRF against best non-RRF baseline on NDCG@10.
    wide=md[(md.model=='rrf')].merge(md[md.model!='rrf'].groupby('window')['ndcg@10'].max().rename('best_base'),on='window'); diffs=[]
    for w in (2,3,4):
        r=pred[(pred.window==w)&(pred.model=='rrf')]; bmodels=md[(md.window==w)&(md.model!='rrf')].sort_values('ndcg@10',ascending=False); b=bmodels.iloc[0].model if len(bmodels) else 'category'
        br=pred[(pred.window==w)&(pred.model==b)]
        rg=r.groupby(['order_id','target']); bg=br.groupby(['order_id','target']); keys=sorted(set(rg.groups)&set(bg.groups))
        for key in keys:
            _,nr,_=one_metrics(rg.get_group(key),10); _,nb,_=one_metrics(bg.get_group(key),10); diffs.append({'window':w,'order_id':key[0],'diff':nr-nb})
    d=pd.DataFrame(diffs); rng=np.random.default_rng(SEED); boots=[]
    for _ in range(2000):
        vals=[]
        for w,g in d.groupby('window'): vals.extend(rng.choice(g['diff'].to_numpy(),len(g),replace=True))
        boots.append(float(np.mean(vals)))
    ci=[float(np.quantile(boots,.025)),float(np.quantile(boots,.975))]; rrf=md[md.model=='rrf']; base=md[md.model!='rrf'].groupby('window')['ndcg@10'].max(); gain=float(rrf.groupby('window')['ndcg@10'].mean().sub(base).mean()); promotion=bool(gain>=0.05 and ci[0]>0 and (rrf.groupby('window')['recall@10'].mean()>=base*0.98).all() and (rrf.coverage_catalogue>=.70).all())
    payload={'evaluated_windows':[2,3,4],'prediction_file':'complement_topk_predictions.parquet','metrics_file':'complement_end_to_end_metrics.csv','bootstrap_replicates':2000,'bootstrap_unit':'commande_x_fenetre','bootstrap_ndcg10_ci95':ci,'rrf_promotion':promotion,'decision':'candidate_union_rrf_promu' if promotion else 'ancienne_reference_conservee','f1_status':'non_evaluable_no_history'}
    (OUT/'complement_end_to_end_metadata.json').write_text(json.dumps(payload,indent=2),encoding='utf-8')
    man={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.glob('complement_*') if p.is_file() and 'manifest' not in p.name}; (OUT/'complement_end_to_end_manifest.sha256.json').write_text(json.dumps(man,indent=2),encoding='utf-8')
if __name__=='__main__': main()
