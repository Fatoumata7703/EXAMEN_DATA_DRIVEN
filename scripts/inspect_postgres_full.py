"""Inspection PostgreSQL directe — transaction READ ONLY, SELECT uniquement.

    python scripts/inspect_postgres_full.py [--deep]

Sécurité :

* la chaîne de connexion est lue **uniquement** depuis l'environnement
  (cf. `src.config.settings.CONNECTION_STRING_ENV_NAMES`) ; sa valeur n'est
  jamais journalisée, affichée ni écrite dans un rapport ;
* la session est ouverte en ``BEGIN READ ONLY`` avec ``statement_timeout``,
  ``lock_timeout`` et ``idle_in_transaction_session_timeout``, puis close par
  ``ROLLBACK`` ;
* toute requête est passée au filtre :func:`assert_read_only` ; aucune
  instruction d'écriture ne peut être émise ;
* les messages d'erreur sont expurgés avant affichage.

Sorties : ``reports/08_inspection_postgres.md`` et ``.json``.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config.settings import (  # noqa: E402
    PROJECT_ROOT,
    get_credentials,
    resolve_reachable_url,
)
from src.data.connection import assert_read_only  # noqa: E402

OUT = io.StringIO()

# Schémas internes à Supabase/PostgreSQL : leur contenu n'est pas parcouru.
SYSTEM_SCHEMAS = {
    "pg_catalog",
    "information_schema",
    "pg_toast",
    "pg_temp_1",
    "pg_toast_temp_1",
}
SUPABASE_INTERNAL = {
    "auth",
    "extensions",
    "graphql",
    "graphql_public",
    "pgbouncer",
    "realtime",
    "supabase_functions",
    "supabase_migrations",
    "vault",
    "pgsodium",
    "pgsodium_masks",
    "net",
    "cron",
}

# Objets et colonnes recherchés pour les sources manquantes.
OBJECT_PATTERNS = [
    "stock", "inventory", "inventaire", "availability", "disponib", "rupture",
    "quality", "qualite", "quarantine", "quarantaine", "reject", "rejet",
    "raw", "bronze", "silver", "gold", "staging", "great_expectation", "dbt",
    "audit", "log", "ingestion", "lineage",
]
COLUMN_PATTERNS = [
    "stock_level", "stock", "launch_date", "date_lancement", "order_id",
    "commande_id", "session_id", "event_timestamp", "referral_source",
    "initial_stock", "signup_date", "popularity", "unit_price", "discount_pct",
    "metadata", "payload", "properties", "attributes", "context", "details",
]


def say(text: str = "") -> None:
    print(text)
    OUT.write(text + "\n")


def redact(message: str) -> str:
    """Expurge toute trace d'identifiant d'un message d'erreur."""
    text = str(message)
    text = re.sub(r"postgres(ql)?://[^\s\"']+", "postgresql://<expurgé>", text)
    text = re.sub(r'password=[^\s"\']+', "password=<expurgé>", text, flags=re.I)
    text = re.sub(r"(?i)\b[\w.-]+\.supabase\.(co|com|net)\b", "<hôte-expurgé>", text)
    return text[:400]


def jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    return obj


class ReadOnlyInspector:
    """Exécute des SELECT dans une transaction explicitement en lecture seule."""

    def __init__(self, url: str) -> None:
        import psycopg2

        self._conn = psycopg2.connect(url, connect_timeout=20)
        self._conn.set_session(readonly=True, autocommit=False)
        self._settings_applied: list[str] = []
        self._settings_refused: list[str] = []
        with self._conn.cursor() as cur:
            for statement, label in (
                ("SET LOCAL statement_timeout = '60s'", "statement_timeout"),
                ("SET LOCAL lock_timeout = '5s'", "lock_timeout"),
                (
                    "SET LOCAL idle_in_transaction_session_timeout = '120s'",
                    "idle_in_transaction_session_timeout",
                ),
            ):
                try:
                    cur.execute(statement)
                    self._settings_applied.append(label)
                except Exception as exc:  # noqa: BLE001
                    self._conn.rollback()
                    self._settings_refused.append(f"{label} ({redact(exc)})")

    def query(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        assert_read_only(sql)
        with self._conn.cursor() as cur:
            cur.execute(sql, params)
            if cur.description is None:
                return []
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def try_query(self, sql: str, params: tuple = ()) -> tuple[list[dict], str | None]:
        try:
            return self.query(sql, params), None
        except Exception as exc:  # noqa: BLE001
            self._conn.rollback()
            return [], redact(exc)

    def close(self) -> None:
        try:
            self._conn.rollback()  # aucune écriture : on annule explicitement
        finally:
            self._conn.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--deep", action="store_true", help="Comptages exacts sur les tables métier.")
    args = parser.parse_args()

    creds = get_credentials()
    if not creds.database_url:
        say("[ÉCHEC] Aucune chaîne de connexion trouvée dans l'environnement.")
        say("        Variables acceptées : DATABASE_URL, SUPABASE_CONNECTION_STRING,")
        say("        SUPABASE_DB_URL, POSTGRES_URL, PG_CONNECTION_STRING.")
        return 1

    say("=" * 78)
    say("INSPECTION POSTGRESQL DIRECTE — TRANSACTION READ ONLY")
    say("=" * 78)
    say(f"  chaîne de connexion lue depuis : ${creds.database_url_source}")
    say("  (valeur jamais affichée, journalisée ni écrite)")

    try:
        url, mode = resolve_reachable_url(creds.database_url)
        say(f"  mode de connexion              : {mode}")
        pg = ReadOnlyInspector(url)
    except Exception as exc:  # noqa: BLE001
        say(f"\n[ÉCHEC CONNEXION] {redact(exc)}")
        return 1

    results: dict[str, Any] = {}
    try:
        say(f"  session read-only      : ACTIVE")
        say(f"  réglages appliqués     : {pg._settings_applied or 'aucun'}")
        if pg._settings_refused:
            say(f"  réglages refusés       : {pg._settings_refused}")

        # ---------------------------------------------------------- 1
        say("")
        say("=" * 78)
        say("1. CONTEXTE DE CONNEXION")
        say("=" * 78)
        ctx, err = pg.try_query(
            """
            SELECT version() AS version,
                   current_database() AS base,
                   current_user AS role_courant,
                   current_schema() AS schema_courant,
                   current_setting('search_path') AS search_path,
                   current_setting('transaction_read_only') AS lecture_seule,
                   inet_server_port() AS port
            """
        )
        if ctx:
            row = ctx[0]
            version = str(row["version"]).split(" on ")[0]
            say(f"  version PostgreSQL   : {version}")
            say(f"  base courante        : {row['base']}")
            say(f"  rôle courant         : {row['role_courant']}")
            say(f"  current_schema()     : {row['schema_courant']}")
            say(f"  search_path          : {row['search_path']}")
            say(f"  transaction_read_only: {row['lecture_seule']}")
            port = row["port"]
            say(f"  port                 : {port} "
                f"({'pooler' if port in (6543,) else 'connexion directe'})")
            results["contexte"] = {
                "version": version,
                "role": row["role_courant"],
                "schema_courant": row["schema_courant"],
                "read_only": row["lecture_seule"],
                "port": port,
            }
        else:
            say(f"  [erreur] {err}")

        roles, _ = pg.try_query(
            """
            SELECT r.rolname AS role, r.rolsuper AS superuser, r.rolbypassrls AS bypass_rls,
                   ARRAY(SELECT b.rolname FROM pg_auth_members m
                         JOIN pg_roles b ON b.oid = m.roleid
                         WHERE m.member = r.oid) AS membre_de
            FROM pg_roles r WHERE r.rolname = current_user
            """
        )
        if roles:
            r = roles[0]
            say(f"  superuser            : {r['superuser']}")
            say(f"  contourne les RLS    : {r['bypass_rls']}")
            say(f"  membre des rôles     : {r['membre_de']}")
            results["role"] = jsonable(r)

        cat, _ = pg.try_query("SELECT count(*) AS n FROM pg_class")
        say(f"  lecture des catalogues : {'OUI' if cat else 'NON'} "
            f"({cat[0]['n'] if cat else 0} objets visibles)")

        # ---------------------------------------------------------- 2
        say("")
        say("=" * 78)
        say("2. INVENTAIRE DES SCHÉMAS")
        say("=" * 78)
        schemas, err = pg.try_query(
            """
            SELECT n.nspname AS schema,
                   pg_catalog.has_schema_privilege(current_user, n.nspname, 'USAGE') AS usage_ok,
                   (SELECT count(*) FROM pg_class c
                     WHERE c.relnamespace = n.oid AND c.relkind IN ('r','p','v','m','f')) AS objets
            FROM pg_namespace n
            ORDER BY n.nspname
            """
        )
        metier: list[str] = []
        say(f"  {'schéma':<26} {'catégorie':<20} {'USAGE':<7} {'objets':>7}")
        for s in schemas:
            name = s["schema"]
            if name in SYSTEM_SCHEMAS or name.startswith("pg_"):
                cat_lbl = "système"
            elif name in SUPABASE_INTERNAL:
                cat_lbl = "interne Supabase"
            elif name == "storage":
                cat_lbl = "Supabase Storage"
            else:
                cat_lbl = "APPLICATIF"
                metier.append(name)
            if cat_lbl != "système":
                say(f"  {name:<26} {cat_lbl:<20} {str(s['usage_ok']):<7} {s['objets']:>7}")
        say("")
        say(f"  -> schémas applicatifs : {metier or 'aucun'}")
        results["schemas"] = {
            "applicatifs": metier,
            "tous": [
                {"schema": s["schema"], "usage": s["usage_ok"], "objets": s["objets"]}
                for s in schemas
            ],
        }

        # ---------------------------------------------------------- 3
        say("")
        say("=" * 78)
        say("3. RECHERCHE DES SOURCES MANQUANTES (tous schémas non système)")
        say("=" * 78)
        like = " OR ".join([f"lower(c.relname) LIKE '%%{p}%%'" for p in OBJECT_PATTERNS])
        objs, err = pg.try_query(
            f"""
            SELECT n.nspname AS schema, c.relname AS objet,
                   CASE c.relkind WHEN 'r' THEN 'table' WHEN 'p' THEN 'table partitionnée'
                        WHEN 'v' THEN 'vue' WHEN 'm' THEN 'vue matérialisée'
                        WHEN 'f' THEN 'foreign table' ELSE c.relkind::text END AS type,
                   c.reltuples::bigint AS lignes_estimees
            FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relkind IN ('r','p','v','m','f')
              AND n.nspname NOT IN ('pg_catalog','information_schema')
              AND n.nspname NOT LIKE 'pg_%%'
              AND ({like})
            ORDER BY n.nspname, c.relname
            """
        )
        say(f"  Objets dont le nom évoque une source recherchée : {len(objs)}")
        for o in objs:
            say(f"    {o['schema']}.{o['objet']:<34} {o['type']:<20} ~{o['lignes_estimees']:,} lignes")
        results["objets_recherches"] = jsonable(objs)

        col_like = " OR ".join([f"lower(a.attname) LIKE '%%{p}%%'" for p in COLUMN_PATTERNS])
        cols, err = pg.try_query(
            f"""
            SELECT n.nspname AS schema, c.relname AS objet, a.attname AS colonne,
                   format_type(a.atttypid, a.atttypmod) AS type
            FROM pg_attribute a
            JOIN pg_class c ON c.oid = a.attrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE a.attnum > 0 AND NOT a.attisdropped
              AND c.relkind IN ('r','p','v','m','f')
              AND n.nspname NOT IN ('pg_catalog','information_schema')
              AND n.nspname NOT LIKE 'pg_%%'
              AND ({col_like})
            ORDER BY n.nspname, c.relname, a.attname
            """
        )
        say("")
        say(f"  Colonnes dont le nom évoque une variable recherchée : {len(cols)}")
        for c in cols:
            say(f"    {c['schema']}.{c['objet']}.{c['colonne']:<24} {c['type']}")
        results["colonnes_recherchees"] = jsonable(cols)

        # ---------------------------------------------------------- 4
        say("")
        say("=" * 78)
        say("4. OBJETS DES SCHÉMAS APPLICATIFS")
        say("=" * 78)
        for schema in metier:
            rows, err = pg.try_query(
                """
                SELECT c.relname AS objet,
                       CASE c.relkind WHEN 'r' THEN 'table' WHEN 'p' THEN 'partitionnée'
                            WHEN 'v' THEN 'vue' WHEN 'm' THEN 'matérialisée'
                            WHEN 'f' THEN 'foreign table' END AS type,
                       c.reltuples::bigint AS lignes_estimees,
                       c.relrowsecurity AS rls,
                       pg_catalog.has_table_privilege(current_user, c.oid, 'SELECT') AS select_ok,
                       obj_description(c.oid) AS commentaire,
                       (SELECT count(*) FROM pg_attribute a
                         WHERE a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped) AS n_colonnes
                FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = %s AND c.relkind IN ('r','p','v','m','f')
                ORDER BY c.relname
                """,
                (schema,),
            )
            say(f"\n  --- schéma `{schema}` : {len(rows)} objet(s) ---")
            say(f"    {'objet':<26} {'type':<14} {'est.':>10} {'RLS':<6} {'SELECT':<7} commentaire")
            for r in rows:
                say(f"    {r['objet']:<26} {r['type']:<14} {r['lignes_estimees']:>10,} "
                    f"{str(r['rls']):<6} {str(r['select_ok']):<7} {r['commentaire'] or ''}")
            results.setdefault("objets_par_schema", {})[schema] = jsonable(rows)

        # ---------------------------------------------------------- 5
        say("")
        say("=" * 78)
        say("5. CONTRAINTES DÉCLARÉES (schémas applicatifs)")
        say("=" * 78)
        if metier:
            cons, err = pg.try_query(
                """
                SELECT n.nspname AS schema, c.relname AS objet, con.conname AS contrainte,
                       CASE con.contype WHEN 'p' THEN 'PRIMARY KEY' WHEN 'f' THEN 'FOREIGN KEY'
                            WHEN 'u' THEN 'UNIQUE' WHEN 'c' THEN 'CHECK' END AS type,
                       pg_get_constraintdef(con.oid) AS definition
                FROM pg_constraint con
                JOIN pg_class c ON c.oid = con.conrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = ANY(%s)
                ORDER BY c.relname, con.contype
                """,
                (metier,),
            )
            for r in cons:
                say(f"  {r['objet']:<24} {r['type']:<12} {r['definition']}")
            results["contraintes"] = jsonable(cons)
            if not cons:
                say("  (aucune contrainte déclarée)")

        # ---------------------------------------------------------- 6
        say("")
        say("=" * 78)
        say("6. FONCTIONS MÉTIER")
        say("=" * 78)
        if metier:
            funcs, err = pg.try_query(
                """
                SELECT n.nspname AS schema, p.proname AS fonction,
                       pg_get_function_arguments(p.oid) AS arguments,
                       pg_get_function_result(p.oid) AS retour,
                       CASE p.provolatile WHEN 'i' THEN 'immutable' WHEN 's' THEN 'stable'
                            WHEN 'v' THEN 'volatile' END AS volatilite,
                       p.prosecdef AS security_definer
                FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
                WHERE n.nspname = ANY(%s)
                ORDER BY n.nspname, p.proname
                """,
                (metier,),
            )
            say(f"  {len(funcs)} fonction(s) dans les schémas applicatifs")
            for f in funcs:
                say(f"    {f['schema']}.{f['fonction']}({f['arguments']}) -> {f['retour']} "
                    f"[{f['volatilite']}, definer={f['security_definer']}]")
            say("  (aucune n'est exécutée : caractère lecture seule non garanti)")
            results["fonctions"] = jsonable(funcs)

        # ---------------------------------------------------------- 7
        say("")
        say("=" * 78)
        say("7. SUPABASE STORAGE (métadonnées)")
        say("=" * 78)
        buckets, err = pg.try_query(
            "SELECT id, name, public, created_at FROM storage.buckets ORDER BY name"
        )
        if err:
            say(f"  storage.buckets : inaccessible avec le rôle PostgreSQL courant")
            say(f"    motif : {err}")
            results["storage"] = {"statut": "inaccessible", "motif": err}
        else:
            say(f"  buckets visibles : {len(buckets)}")
            for b in buckets:
                say(f"    - {b['name']} (public={b['public']})")
            objects, oerr = pg.try_query(
                """
                SELECT bucket_id,
                       count(*) AS n_objets,
                       min(split_part(name, '/', 1)) AS premier_prefixe
                FROM storage.objects GROUP BY bucket_id ORDER BY bucket_id
                """
            )
            if oerr:
                say(f"  storage.objects : {oerr}")
            else:
                say(f"  objets : {sum(o['n_objets'] for o in objects) if objects else 0}")
                for o in objects:
                    say(f"    - {o['bucket_id']} : {o['n_objets']} objet(s), "
                        f"préfixe `{o['premier_prefixe']}`")
            results["storage"] = {
                "statut": "lisible",
                "n_buckets": len(buckets),
                "buckets": [b["name"] for b in buckets],
                "objets": jsonable(objects),
            }

        # ---------------------------------------------------------- 8
        say("")
        say("=" * 78)
        say("8. STATUT DÉFINITIF DES SOURCES BLOQUANTES")
        say("=" * 78)
        cibles = {
            "stock_daily (table)": ("objet", ["stock_daily", "stock", "inventory", "inventaire"]),
            "launch_date (colonne)": ("colonne", ["launch_date", "date_lancement"]),
            "order_id (colonne)": ("colonne", ["order_id", "commande_id"]),
            "session_id (colonne)": ("colonne", ["session_id"]),
            "event_timestamp (colonne)": ("colonne", ["event_timestamp"]),
            "referral_source (colonne)": ("colonne", ["referral_source"]),
            "initial_stock (colonne)": ("colonne", ["initial_stock"]),
            "signup_date (colonne)": ("colonne", ["signup_date"]),
            "popularity_score (colonne)": ("colonne", ["popularity"]),
            "quarantaine / rejets": ("objet", ["quarantine", "quarantaine", "reject", "rejet"]),
            "zones raw/bronze/silver/gold": ("objet", ["raw", "bronze", "silver", "gold", "staging"]),
        }
        say(f"  {'source recherchée':<32} {'statut':<24} localisation")
        statuts = {}
        for label, (kind, motifs) in cibles.items():
            pool = objs if kind == "objet" else cols
            key = "objet" if kind == "objet" else "colonne"
            trouves = [
                o for o in pool if any(m in str(o[key]).lower() for m in motifs)
            ]
            if trouves:
                loc = ", ".join(
                    f"{t['schema']}.{t['objet']}" + (f".{t['colonne']}" if kind == "colonne" else "")
                    for t in trouves[:3]
                )
                statut = "PRÉSENT ET LISIBLE"
            else:
                loc, statut = "—", "ABSENT DE L'INSTANCE"
            say(f"  {label:<32} {statut:<24} {loc}")
            statuts[label] = {"statut": statut, "localisation": loc}
        results["statuts_sources"] = statuts

        # ---------------------------------------------------------- 9
        say("")
        say("=" * 78)
        say("9. SCHÉMA PUBLIC — CONTRÔLE SQL DIRECT")
        say("=" * 78)
        tables, _ = pg.try_query(
            """
            SELECT c.relname AS objet, c.reltuples::bigint AS estime,
                   c.relrowsecurity AS rls,
                   pg_catalog.has_table_privilege(current_user, c.oid, 'SELECT') AS select_ok
            FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relkind = 'r' ORDER BY c.relname
            """
        )
        say(f"  {'table':<24} {'estimé':>10} {'exact':>10} {'RLS':<6} SELECT")
        exact_counts = {}
        for t in tables:
            name = t["objet"]
            exact = "—"
            if args.deep or t["estime"] < 1_000_000:
                rows, cerr = pg.try_query(f'SELECT count(*) AS n FROM public."{name}"')
                if rows:
                    exact = f"{rows[0]['n']:,}"
                    exact_counts[name] = rows[0]["n"]
            say(f"  {name:<24} {t['estime']:>10,} {exact:>10} {str(t['rls']):<6} {t['select_ok']}")
        results["public_counts"] = exact_counts

        pol, perr = pg.try_query(
            """
            SELECT schemaname AS schema, tablename AS table, policyname AS politique, cmd
            FROM pg_policies WHERE schemaname = 'public' ORDER BY tablename
            """
        )
        say("")
        if perr:
            say(f"  politiques RLS : illisibles ({perr})")
        else:
            say(f"  politiques RLS sur `public` : {len(pol)}")
            for p in pol:
                say(f"    {p['table']}.{p['politique']} ({p['cmd']})")
        results["rls_policies"] = jsonable(pol)

        say("")
        say("=" * 78)
        say("FIN — ROLLBACK de la transaction (aucune écriture émise)")
        say("=" * 78)
    finally:
        pg.close()

    reports = PROJECT_ROOT / "reports"
    (reports / "08_inspection_postgres.md").write_text(
        "# 08 — Inspection PostgreSQL directe\n\n"
        "_Sortie de `python scripts/inspect_postgres_full.py`. "
        "Transaction READ ONLY, SELECT uniquement, identifiants jamais exposés._\n\n```\n"
        + OUT.getvalue()
        + "```\n",
        encoding="utf-8",
    )
    (reports / "08_inspection_postgres.json").write_text(
        json.dumps(jsonable(results), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
