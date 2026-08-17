"""Pricing final observationnel: validation temporelle et simulateur gardé."""
from __future__ import annotations
import hashlib,json
from pathlib import Path
import joblib,numpy as np,pandas as pd
from lightgbm import LGBMRegressor
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import PoissonRegressor,TweedieRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder,StandardScaler
from src.config.settings import PROJECT_ROOT

DATA=PROJECT_ROOT/'data/processed/final/product_day_discount_pricing.parquet'
OUT=PROJECT_ROOT/'models/pricing';REPORT=PROJECT_ROOT/'reports/final';SEED=42;FLOOR=.05
CAT=['produit_key','categorie','marque'];NUM=['remise_pct','prix_base_xof','cout_xof','n_lignes']
def pipe(reg):return Pipeline([('prep',ColumnTransformer([('cat',OneHotEncoder(handle_unknown='ignore'),CAT),('num',StandardScaler(),NUM)])),('model',reg)])
def score(y,p):
    p=np.maximum(0,p);den=max(y.sum(),1);return {'wape':float(np.abs(p-y).sum()/den),'bias':float((p-y).sum()/den),'poisson_deviance_proxy':float(np.mean((p-y)**2/(p+1)))}
def main():
    OUT.mkdir(parents=True,exist_ok=True);REPORT.mkdir(parents=True,exist_ok=True)
    d=pd.read_parquet(DATA);d['ds']=pd.to_datetime(d.ds);d['dow']=d.ds.dt.dayofweek;d['month']=d.ds.dt.month
    results=[];last_models={}
    for wi,days in enumerate((180,120,60),1):
        start=d.ds.max()-pd.Timedelta(days=days-1);end=start+pd.Timedelta(days=59)
        tr=d[d.ds<start];te=d[d.ds.between(start,end)]
        # Descriptif intra-produit, strictement calculé sur le train.
        desc=tr.groupby(['produit_key','remise_pct']).quantite.mean();fallback=tr.groupby('produit_key').quantite.mean()
        pdsc=np.array([desc.get((r.produit_key,r.remise_pct),fallback.get(r.produit_key,tr.quantite.mean())) for r in te.itertuples()])
        results.append({'window':wi,'model':'descriptif_intra_produit',**score(te.quantite.to_numpy(),pdsc)})
        models={
          'GLM_Poisson':pipe(PoissonRegressor(alpha=.1,max_iter=300)),
          'GLM_Tweedie':pipe(TweedieRegressor(power=1.3,alpha=.1,link='log',max_iter=300)),
          'panel_effets_fixes':pipe(PoissonRegressor(alpha=.01,max_iter=400)),
        }
        for name,m in models.items():
            m.fit(tr[CAT+NUM],tr.quantite);pred=m.predict(te[CAT+NUM]);results.append({'window':wi,'model':name,**score(te.quantite.to_numpy(),pred)});last_models[name]=m
        # Pooling hiérarchique catégorie×remise avec shrinkage vers catégorie.
        gm=tr.groupby(['categorie','remise_pct']).quantite.agg(['mean','count']);base=tr.groupby('categorie').quantite.mean()
        hp=np.array([((gm.loc[(r.categorie,r.remise_pct),'mean']*gm.loc[(r.categorie,r.remise_pct),'count']+base[r.categorie]*20)/(gm.loc[(r.categorie,r.remise_pct),'count']+20)) if (r.categorie,r.remise_pct) in gm.index else base[r.categorie] for r in te.itertuples()])
        results.append({'window':wi,'model':'hierarchique_categorie',**score(te.quantite.to_numpy(),hp)})
        lgb=LGBMRegressor(objective='tweedie',tweedie_variance_power=1.3,n_estimators=250,learning_rate=.04,num_leaves=31,min_child_samples=40,random_state=SEED,n_jobs=2,verbosity=-1)
        xtr=pd.get_dummies(tr[CAT+NUM],columns=CAT,dtype=float);xte=pd.get_dummies(te[CAT+NUM],columns=CAT,dtype=float).reindex(columns=xtr.columns,fill_value=0)
        lgb.fit(xtr,tr.quantite);pred=lgb.predict(xte);cal=tr.quantite.mean()/max(lgb.predict(xtr).mean(),1e-9);pred*=cal
        results.append({'window':wi,'model':'LightGBM_calibre',**score(te.quantite.to_numpy(),pred)});last_models['LightGBM_calibre']=(lgb,list(xtr.columns),cal)
    r=pd.DataFrame(results);summary=r.groupby('model').agg(wape=('wape','mean'),std=('wape','std'),bias=('bias','mean')).reset_index().sort_values(['wape','std']);selected=summary.iloc[0].model
    # Simulateur descriptif, uniquement remises observées et marge sûre.
    supports=d.groupby(['produit_key','remise_pct']).agg(q=('quantite','mean'),n=('quantite','size')).reset_index();catresp=d.groupby(['categorie','remise_pct']).quantite.mean()
    products=d.sort_values('ds').groupby('produit_key').tail(1);rows=[]
    for p in products.itertuples():
        sup=supports[supports.produit_key.eq(p.produit_key)];cands=[]
        for x in sup.itertuples():
            price=p.prix_base_xof*(1-x.remise_pct/100);q=x.q if x.n>=10 else catresp.get((p.categorie,x.remise_pct),x.q)
            margin=(price-p.cout_xof)*q;ok=price>=p.cout_xof and (price-p.cout_xof)/price>=FLOOR
            if ok:cands.append((margin,x.remise_pct,price,q,x.n))
        best=max(cands) if cands else ((p.prix_base_xof-p.cout_xof),0,p.prix_base_xof,1,0)
        rows.append({'produit_key':p.produit_key,'suggested_discount_pct':best[1],'simulated_price_xof':best[2],'predicted_quantity':best[3],'predicted_margin_xof':best[0],'historical_support':best[4],'margin_floor':FLOOR,'automatic_application_allowed':False,'human_validation_required':True,'causal_effect_estimated':False})
    sim=pd.DataFrame(rows);sim.to_csv(OUT/'promotion_simulator.csv',index=False)
    joblib.dump(last_models,OUT/'candidate_models.joblib')
    meta={'selected':selected,'summary':summary.to_dict('records'),'catalog_price_varies':False,'scope':'commandes confirmees','causal':False,'automatic_application_allowed':False,'human_validation_required':True,'margin_floor':FLOOR}
    (OUT/'metadata.json').write_text(json.dumps(meta,indent=2,ensure_ascii=False),encoding='utf-8')
    manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.iterdir() if p.is_file()};(OUT/'manifest.sha256.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    lines=['# 03 — Pricing final','',f'**Méthode prédictive retenue : `{selected}`.**','',summary.to_markdown(index=False),'','## Verdict métier','',
      'Le prix catalogue reste fixe pour les 300 produits. Il est interdit de présenter ce résultat comme un prix optimal continu ou un effet causal. Le livrable est un simulateur observationnel de promotions et marge.','',
      f'Garde-fous : prix jamais sous coût, marge minimale {FLOOR:.0%}, remise limitée au support historique, validation humaine obligatoire, application automatique interdite.','',
      'Commande : `python -m src.pipelines.final_pricing`.']
    (REPORT/'03_pricing.md').write_text('\n'.join(lines)+'\n',encoding='utf-8');print(json.dumps({'selected':selected,'summary':summary.to_dict('records')},default=str))
if __name__=='__main__':main()
