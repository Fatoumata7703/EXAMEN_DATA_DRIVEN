"""
Suite great_expectations — contrôle qualité formel des tables source, en complément
des règles codées directement dans pipeline/transforms.py (fonction
run_dq_checkpoint). Positionnée entre les zones Bronze et Silver du pipeline.

La syntaxe suit l'API Fluent de great_expectations 1.x. Chaque règle a été validée
au préalable en pandas pur (voir dry_run_check.py) pour confirmer que les colonnes et
les seuils correspondent aux données réellement produites par le pipeline.

Une ExpectationSuite et un Checkpoint sont créés par table (et non une suite unique
partagée) : chaque table ayant des colonnes différentes, une suite partagée ferait
échouer chaque table sur les règles définies pour les autres.

Usage :
    pip install great_expectations
    python run_data_quality.py
Génère un site Data Docs HTML dans gx/uncommitted/data_docs/local_site/index.html,
consultable dans un navigateur.
"""

from pathlib import Path
import os

import pandas as pd
import great_expectations as gx

SOURCE_DIR = Path(os.environ.get(
    "SOURCE_DIR", str(Path(__file__).resolve().parent.parent / "02_jeu_de_donnees" / "donnees")
))


def load_source_tables() -> dict[str, pd.DataFrame]:
    """Charge les 6 tables source telles qu'elles arrivent en sortie de Bronze
    (typées, dédupliquées)."""
    def read(fname, base=SOURCE_DIR):
        df = pd.read_csv(base / fname, compression="gzip" if fname.endswith(".gz") else None)
        return df.drop_duplicates()

    return {
        "dim_products": read("dim_products.csv"),
        "dim_customers": read("dim_customers.csv"),
        "promotions": read("promotions.csv"),
        "fact_transactions": read("fact_transactions.csv.gz"),
        "stock_daily": read("stock_daily.csv.gz"),
        "web_events": read("web_events.csv.gz"),
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
            E.ExpectColumnValuesToBeInSet(column="product_id", value_set=valid_product_ids),
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
