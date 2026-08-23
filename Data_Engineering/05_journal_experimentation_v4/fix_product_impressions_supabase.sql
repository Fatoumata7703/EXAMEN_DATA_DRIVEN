-- Correctif product_impressions (bug P-12 confirmé par l'audit DS, cause racine :
-- unité microseconde vs nanoseconde dans le calcul du cumul strictement antérieur)
--
-- La structure de la table ne change pas, seules les VALEURS de product_impressions
-- changent. Le plus simple et le plus sûr : vider et réimporter.

truncate table fact_experimentation_prix;

-- Puis : Table Editor -> fact_experimentation_prix -> Import data from CSV
-- avec fact_experimentation_prix_v4.csv (fichier corrigé, nouvelle empreinte
-- b65a40e97fa1e3d35b78c2558af52283302bd93185e034d0e6fcfdad8bef9163)

-- Vérification post-import : doit retourner 0 lignes après le correctif pour les
-- produits qui ONT des expositions (seuls les produits jamais exposés doivent
-- rester à product_impressions constant = 0, ce qui est normal)
select fp.produit_key, count(distinct fp.product_impressions) as valeurs_distinctes
from fact_experimentation_prix fp
where exists (select 1 from fact_exposition_reco fer where fer.produit_key = fp.produit_key)
group by fp.produit_key
having count(distinct fp.product_impressions) = 1;
-- attendu : 0 ligne (tout produit qui a été exposé au moins une fois doit montrer
-- une variation de product_impressions au fil du temps)
