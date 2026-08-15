**Résultats V1 — Forecasting, Pricing, Recommandation** 📊

Les trois premiers modules du projet data sont figés et documentés (5 000 clients, 300 produits, 85 419 ventes sur 546 jours, données auditées avant modélisation). Voici où on en est.

**Forecasting** — AutoETS, fiable pour la planification cumulée à 30 jours (WAPE 27,7 %) et 7 jours (WAPE 46,2 %). La précision au jour le jour reste faible (WAPE ~109 %) : à utiliser pour du volume agrégé, pas pour prédire une vente précise un jour donné.

**Pricing** — simulateur exploratoire sous garde-fous (marge minimale 5 %, aucune remise sous le coût). 288 simulations produites, dont 240 recommandent 0 % de remise : les promotions historiques ne compensent généralement pas la perte de marge. Résultats observationnels, pas causaux — **pas un moteur de prix optimal**.

**Recommandation** — baseline « produits populaires » retenue, personnalisation testée puis désactivée (aucun gain suffisant). Recall@10 7,6 %, couverture catalogue seulement 5,4 %. Utilisable comme bloc générique, **pas comme recommandation personnalisée**.

Aucun déploiement, aucune écriture Supabase, 156 tests automatisés passés, aucun secret publié.

📁 Dépôt complet : https://github.com/younesda/EXAMEN_DATA_DRIVEN

**5 décisions à valider avec l'équipe :**
1. Usage du forecasting pour la planification mensuelle
2. Positionnement exploratoire (non déployable) du pricing
3. Choix métier recommandation : découverte (exclut les rachats) ou réapprovisionnement (les autorise) ?
4. Accord sur les objectifs V2 (seuils détaillés dans la synthèse complète)
5. Confirmation : pas de déploiement avant validation métier

Synthèse complète en pièce jointe pour le détail. 🙏
