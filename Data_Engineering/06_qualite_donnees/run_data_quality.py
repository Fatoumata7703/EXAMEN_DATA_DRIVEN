"""
Suite great_expectations — remplace run_dq_checkpoint() codée à la main dans
pipeline/transforms.py, sans changer la structure du pipeline : ce gate reste appelé
entre Bronze et Silver.

IMPORTANT — limite honnête de cette livraison :
Ce script n'a PAS pu être exécuté dans l'environnement de développement (pas d'accès
réseau pour installer great_expectations). La syntaxe est vérifiée contre la
documentation officielle GX 1.x (API "Fluent", docs.greatexpectations.io/docs/core/),
et chaque règle a été testée en pandas pur sur les vraies données (voir
dry_run_check.py) pour confirmer que les seuils sont corrects. Mais l'exécution réelle
de CE script GX n'a pas été validée de bout en bout. Lance-le chez toi et montre-moi la
première erreur si erreur il y a — on la corrige immédiatement plutôt que de deviner.

Une suite ExpectationSuite ET un Checkpoint sont créés PAR TABLE (pas une suite unique
partagée) : chaque table a des colonnes différentes, une suite partagée ferait échouer
chaque table sur les règles des 5 autres.

Usage :
    pip install great_expectations
    python run_data_quality.py
Génère un site Data Docs HTML dans gx/uncommitted/data_docs/local_site/index.html
"""

from pathlib import Path
import sys

import pandas as pd
import great_expectations as gx

sys.path.insert(0, "/home/claude/airflow_project")
from pipeline.transforms import SOURCE_DIR  # noqa: E402

V3_DIR = Path("/home/claude/enrichissement_v3")  # à adapter au chemin réel chez toi


def load_source_tables() -> dict[str, pd.DataFrame]:
    """Charge les 6 tables telles qu'elles arrivent en sortie de Bronze (typées,
    dédupliquées). dim_products/dim_customers/promotions n'ont pas changé depuis la
    v1 ; fact_transactions et stock_daily viennent en revanche de la régénération v3
    (paniers réels + corrections d'audit) — PAS des fichiers originaux, qui sont
    désormais obsolètes."""
    def read(fname, base=SOURCE_DIR):
        df = pd.read_csv(base / fname, compression="gzip" if fname.endswith(".gz") else None)
        return df.drop_duplicates()

    return {
        "dim_products": read("dim_products.csv"),
        "dim_customers": read("dim_customers.csv"),
        "promotions": read("promotions.csv"),
        "fact_transactions": read("fact_transactions_v3.csv.gz", base=V3_DIR),
        "stock_daily": read("stock_daily_v3.csv.gz", base=V3_DIR),
        "web_events": read("fact_evenements_web_v3.csv.gz", base=V3_DIR),
    }


def build_expectations(table: str, valid_product_ids: list) -> list:
    """Retourne la liste des objets Expectation GX pour une table donnée.
    Reproduit exactement les règles précédemment codées à la main dans
    run_dq_checkpoint(), plus quelques règles de structure supplémentaires."""
    E = gx.expectations

    if table == "dim_products":
        return [
            E.ExpectColumnValuesToNotBeNull(column="product_id"),
            E.ExpectColumnValuesToBeUnique(column="product_id"),
            E.ExpectColumnValuesToNotBeNull(column="category"),
            # casse incohérente = catégorie entièrement en majuscules (proxy de l'anomalie connue)
            E.ExpectColumnValuesToNotMatchRegex(column="category", regex=r"^[A-Z\s&\-]+$"),
        ]

    if table == "dim_customers":
        return [
            E.ExpectColumnValuesToNotBeNull(column="customer_id"),
            E.ExpectColumnValuesToBeUnique(column="customer_id"),
            # valeurs manquantes tolérées (signalées, pas bloquantes) tant que < 10%
            E.ExpectColumnValuesToNotBeNull(column="region", mostly=0.90),
            E.ExpectColumnValuesToNotBeNull(column="age_bracket", mostly=0.90),
        ]

    if table == "promotions":
        return [
            E.ExpectColumnValuesToNotBeNull(column="promotion_id"),
            E.ExpectColumnValuesToBeUnique(column="promotion_id"),
            E.ExpectColumnValuesToBeBetween(column="discount_pct", min_value=0, max_value=100),
        ]

    if table == "fact_transactions":
        return [
            E.ExpectColumnValuesToNotBeNull(column="ligne_id_origine"),
            E.ExpectColumnValuesToBeUnique(column="ligne_id_origine"),  # identifiant de LIGNE, pas de commande
            E.ExpectColumnValuesToNotBeNull(column="order_id"),  # plus unique par ligne : un panier partage son order_id
            E.ExpectColumnValuesToBeInSet(column="order_status", value_set=["confirmee", "annulee", "retournee"]),
            E.ExpectColumnValuesToNotBeNull(column="customer_id"),
            E.ExpectColumnValuesToNotBeNull(column="product_id"),
            E.ExpectColumnValuesToBeBetween(column="quantity", min_value=1),
            E.ExpectColumnValuesToBeInSet(column="product_id", value_set=valid_product_ids),
        ]

    if table == "stock_daily":
        return [
            E.ExpectColumnValuesToNotBeNull(column="product_id"),
            E.ExpectColumnValuesToNotBeNull(column="date"),
            E.ExpectColumnValuesToBeBetween(column="stock_level", min_value=0),
            E.ExpectColumnValuesToBeBetween(column="quantite_vendue", min_value=0),
            E.ExpectColumnValuesToBeBetween(column="quantite_reapprovisionnee", min_value=0),
        ]

    if table == "web_events":
        return [
            E.ExpectColumnValuesToNotBeNull(column="event_id"),
            E.ExpectColumnValuesToBeUnique(column="event_id"),
            E.ExpectColumnValuesToBeInSet(column="event_type", value_set=["view", "add_to_cart", "purchase"]),
            E.ExpectColumnValuesToBeInSet(column="produit_key", value_set=valid_product_ids),  # nom v3 : produit_key, pas product_id
        ]

    raise ValueError(f"Pas de règles définies pour la table {table}")


def main():
    dfs = load_source_tables()
    valid_product_ids = dfs["dim_products"]["product_id"].tolist()

    context = gx.get_context(mode="file", project_root_dir=str(Path(__file__).parent / "gx"))
    data_source = context.data_sources.add_pandas("pandas_source")

    print("=== Résultats de validation ===\n")
    all_passed = True

    for table, df in dfs.items():
        asset = data_source.add_dataframe_asset(name=table)
        batch_def = asset.add_batch_definition_whole_dataframe(f"{table}_batch")

        suite = context.suites.add(gx.core.expectation_suite.ExpectationSuite(name=f"{table}_suite"))
        for expectation in build_expectations(table, valid_product_ids):
            suite.add_expectation(expectation)

        validation_def = context.validation_definitions.add(
            gx.core.validation_definition.ValidationDefinition(
                name=f"{table}_validation", data=batch_def, suite=suite,
            )
        )

        checkpoint = context.checkpoints.add(
            gx.Checkpoint(
                name=f"{table}_checkpoint",
                validation_definitions=[validation_def],
                actions=[gx.checkpoint.actions.UpdateDataDocsAction(name="update_all_data_docs")],
                result_format={"result_format": "COMPLETE"},
            )
        )

        result = checkpoint.run(batch_parameters={"dataframe": df})

        table_success = result.success
        n_rules = 0
        n_failed = 0
        failed_details = []
        for validation_result_dict in result.run_results.values():
            validation_result = validation_result_dict["validation_result"]
            n_rules += len(validation_result.results)
            for r in validation_result.results:
                if not r.success:
                    n_failed += 1
                    col = r.expectation_config.kwargs.get("column", "?")
                    n_unexpected = r.result.get("unexpected_count", "?")
                    failed_details.append(f"    - {r.expectation_config.type} sur {col} : {n_unexpected} lignes en anomalie")

        status = "OK" if table_success else "ANOMALIES DÉTECTÉES"
        print(f"[{table}] {status} — {n_rules} règles vérifiées, {n_failed} en échec")
        for line in failed_details:
            print(line)

        if not table_success:
            all_passed = False

    context.build_data_docs()
    print("\nData Docs générés : gx/uncommitted/data_docs/local_site/index.html")
    print(f"\nRésultat global : {'TOUT PASSE' if all_passed else 'DES ANOMALIES ONT ÉTÉ DÉTECTÉES (comportement attendu — voir HANDOFF_DATA_SCIENTIST.md pour la liste connue)'}")


if __name__ == "__main__":
    main()
