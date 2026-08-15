"""Proposition automatique du mapping « colonne réelle -> rôle métier ».

Le projet interdit de *supposer* les noms de colonnes. Ce module ne devine donc
rien en aveugle : il classe les colonnes **réellement présentes** dans le schéma
selon des motifs lexicaux (français et anglais) et leur type, puis produit une
proposition **explicitement marquée comme telle**, à valider par un humain dans
``config/config.yaml`` (section ``schema_mapping``).

Toute valeur renseignée dans le YAML est prioritaire sur l'heuristique.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

import pandas as pd

from src.data.schema_inspector import SchemaSnapshot, TableSchema
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)

# Motifs par rôle : (regex, score). Le score départage les candidats multiples.
ROLE_PATTERNS: dict[str, list[tuple[str, int]]] = {
    "date": [
        (r"^(date|ds|jour|day)$", 100),
        (r"date_(vente|commande|transaction|achat|operation)", 95),
        (r"(vente|commande|transaction|achat)_date", 95),
        (r"^date_id$|^id_date$|^date_key$|^date_sk$", 80),
        (r"date", 60),
        (r"(timestamp|datetime|created_at|horodat)", 40),
    ],
    "quantity": [
        (r"^(quantite|quantity|qte|qty)$", 100),
        (r"quantite_(vendue|nette|commandee)", 98),
        (r"(quantite|quantity|qte|qty)", 80),
        (r"^(nb|nombre)_(unites|articles|produits|pieces)$", 70),
        (r"^volume$", 50),
    ],
    "amount": [
        (r"^(montant|chiffre_affaires|ca|revenue|total|montant_total)$", 100),
        (r"montant_(total|ttc|ht|net|ligne)", 95),
        (r"(chiffre.?affaires|turnover|revenue|sales_amount)", 90),
        (r"^total_(ligne|ttc|ht)$", 85),
        (r"montant", 70),
    ],
    "unit_price": [
        (r"^(prix_unitaire|unit_price|pu)$", 100),
        (r"prix_(unitaire|vente|catalogue|liste)", 95),
        (r"^(prix|price)$", 85),
        (r"(prix|price)", 60),
    ],
    "discount": [
        (r"^(remise|discount|reduction|rabais)$", 100),
        (r"(taux|pct|pourcentage)_(remise|reduction|discount)", 98),
        (r"montant_(remise|reduction)", 95),
        (r"(remise|discount|reduction|rabais)", 75),
    ],
    "status": [
        (r"^(statut|status|etat|state)$", 100),
        (r"(statut|status|etat)_(vente|commande|ligne)", 95),
        (r"(statut|status)", 70),
    ],
    "return_flag": [
        (r"^(retour|is_retour|est_retour|returned|is_return)$", 100),
        (r"(retour|return|remboursement|refund)", 80),
    ],
    "cancel_flag": [
        (r"^(annule|annulee|is_annule|cancelled|canceled|is_cancelled)$", 100),
        (r"(annul|cancel)", 80),
    ],
    "product_key": [
        (r"^(produit_id|id_produit|product_id|id_product|produit_key|product_key)$", 100),
        (r"^(sku|code_produit|product_code|reference_produit)$", 90),
        (r"(produit|product).*(id|key|sk|code)", 75),
        (r"(id|key).*(produit|product)", 75),
    ],
    "client_key": [
        (r"^(client_id|id_client|customer_id|id_customer|client_key)$", 100),
        (r"(client|customer).*(id|key|sk|code)", 75),
        (r"(id|key).*(client|customer)", 75),
    ],
    "promotion_key": [
        (r"^(promotion_id|id_promotion|promo_id|id_promo|promotion_key)$", 100),
        (r"(promotion|promo).*(id|key|sk|code)", 75),
        (r"(id|key).*(promotion|promo)", 75),
    ],
    "line_id": [
        (r"^(vente_id|id_vente|ligne_id|id_ligne|sale_id|transaction_id|line_id)$", 100),
        (r"^(event_id|id_event|evenement_id|id_evenement)$", 95),
        (r"^id$", 85),
        (r"(ligne|line|transaction|vente|event|evenement).*(id|key)", 60),
    ],
    "order_id": [
        (r"^(commande_id|id_commande|order_id|id_order|num_commande)$", 100),
        (r"(commande|order).*(id|num|key)", 70),
    ],
    "category": [
        (r"^(categorie|category|famille|rayon)$", 100),
        (r"(categorie|category|famille)(?!.*(sous|sub))", 80),
    ],
    "subcategory": [
        (r"^(sous_categorie|souscategorie|subcategory|sub_category|sous_famille)$", 100),
        (r"(sous.?categorie|sub.?categor|sous.?famille)", 90),
    ],
    "brand": [
        (r"^(marque|brand|fabricant|manufacturer)$", 100),
        (r"(marque|brand)", 75),
    ],
    "label": [
        (r"^(libelle|nom|name|designation|label|nom_produit|libelle_produit)$", 100),
        (r"(libelle|designation|nom_|name)", 70),
    ],
    "launch_date": [
        (r"(date).*(lancement|launch|creation|mise_en_vente|introduction)", 100),
        (r"(lancement|launch)", 80),
    ],
    "start_date": [
        (r"(date).*(debut|start|from)", 100),
        (r"^(debut|start_date|date_debut)$", 100),
    ],
    "end_date": [
        (r"(date).*(fin|end|to)", 100),
        (r"^(fin|end_date|date_fin)$", 100),
    ],
    "discount_rate": [
        (r"(taux|pct|pourcentage|rate).*(remise|reduction|discount)", 100),
        (r"(remise|reduction|discount).*(taux|pct|rate|pourcentage)", 100),
        (r"^(remise|discount|reduction)$", 80),
    ],
    "event_type": [
        (r"^(type_evenement|event_type|type_event|evenement|event|action|type)$", 100),
        (r"(type).*(evenement|event|action)", 90),
        (r"(evenement|event)", 60),
    ],
    "session_key": [
        (r"^(session_id|id_session|session_key|visit_id)$", 100),
        (r"session", 70),
    ],
    "stock_level": [
        (r"^(niveau_stock|stock_level|stock_niveau|quantite_stock)$", 100),
        (r"^stock$", 90),
        (r"stock", 60),
    ],
}

NUMERIC_ROLES = {"quantity", "amount", "unit_price", "discount", "discount_rate"}
DATE_ROLES = {"date", "launch_date", "start_date", "end_date"}


def normalize(name: str) -> str:
    """minuscules, sans accents, séparateurs unifiés en ``_``."""
    text = unicodedata.normalize("NFKD", str(name))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def _is_numeric_type(data_type: str) -> bool:
    dt = str(data_type).lower()
    return any(
        token in dt
        for token in ("int", "numeric", "decimal", "double", "real", "float", "money")
    )


def _is_date_type(data_type: str) -> bool:
    dt = str(data_type).lower()
    return any(token in dt for token in ("date", "time"))


@dataclass
class RoleCandidate:
    column: str
    score: int
    reason: str


@dataclass
class TableMapping:
    table: str
    roles: dict[str, str | None] = field(default_factory=dict)
    candidates: dict[str, list[RoleCandidate]] = field(default_factory=dict)

    def get(self, role: str) -> str | None:
        return self.roles.get(role)


def propose_table_mapping(
    table: TableSchema,
    roles: Iterable[str],
    type_hints: bool = True,
) -> TableMapping:
    """Classe les colonnes de la table pour chacun des rôles demandés."""
    mapping = TableMapping(table=table.name)
    columns = table.columns

    for role in roles:
        patterns = ROLE_PATTERNS.get(role, [])
        found: list[RoleCandidate] = []
        for _, row in columns.iterrows():
            col = str(row["column_name"])
            norm = normalize(col)
            data_type = str(row.get("data_type", ""))
            best_score = 0
            best_pattern = ""
            for pattern, score in patterns:
                if re.search(pattern, norm):
                    if score > best_score:
                        best_score, best_pattern = score, pattern
            if best_score == 0:
                continue
            reason = f"motif `{best_pattern}`"
            if type_hints:
                # Bonus/malus de cohérence de type
                if role in NUMERIC_ROLES:
                    if _is_numeric_type(data_type):
                        best_score += 10
                        reason += ", type numérique"
                    else:
                        best_score -= 40
                        reason += f", type NON numérique ({data_type})"
                if role in DATE_ROLES:
                    if _is_date_type(data_type):
                        best_score += 10
                        reason += ", type date"
                    elif _is_numeric_type(data_type) and "id" in norm:
                        reason += ", clé de dimension date (numérique)"
                    else:
                        best_score -= 20
                        reason += f", type inattendu ({data_type})"
            found.append(RoleCandidate(column=col, score=best_score, reason=reason))

        found.sort(key=lambda c: (-c.score, c.column))
        mapping.candidates[role] = found
        mapping.roles[role] = found[0].column if found and found[0].score > 0 else None

    return mapping


# Rôles recherchés par table logique.
TABLE_ROLES: dict[str, list[str]] = {
    "ventes": [
        "date",
        "product_key",
        "client_key",
        "promotion_key",
        "quantity",
        "amount",
        "unit_price",
        "discount",
        "status",
        "return_flag",
        "cancel_flag",
        "line_id",
        "order_id",
    ],
    "produit": [
        "product_key",
        "label",
        "category",
        "subcategory",
        "brand",
        "unit_price",
        "launch_date",
    ],
    "date": ["date", "line_id"],
    "promotion": [
        "promotion_key",
        "product_key",
        "start_date",
        "end_date",
        "discount_rate",
        "label",
    ],
    "web": [
        "date",
        "product_key",
        "client_key",
        "event_type",
        "session_key",
        "line_id",
    ],
    "client": ["client_key", "label"],
    "stock": ["product_key", "date", "stock_level"],
}


def propose_mapping(snapshot: SchemaSnapshot, table_aliases: dict[str, str]) -> dict[str, TableMapping]:
    """Propose un mapping pour chaque table logique présente.

    ``table_aliases`` associe le nom logique (``ventes``, ``produit``...) au nom
    réel découvert dans la base.
    """
    result: dict[str, TableMapping] = {}
    for logical, real in table_aliases.items():
        if real is None or real not in snapshot.tables:
            logger.warning("Table logique '%s' introuvable (%s)", logical, real)
            continue
        roles = TABLE_ROLES.get(logical, [])
        result[logical] = propose_table_mapping(snapshot.tables[real], roles)
    return result


def match_tables(snapshot: SchemaSnapshot, configured: dict[str, Any]) -> dict[str, str | None]:
    """Associe noms logiques -> noms réels de tables.

    On part des noms déclarés en configuration, puis on retombe sur une
    recherche par mot-clé dans les tables réellement présentes.
    """
    keywords = {
        "ventes": ["vente", "sale", "commande", "order", "transaction"],
        "produit": ["produit", "product", "article", "item"],
        "date": ["date", "calendrier", "calendar", "temps", "time"],
        "promotion": ["promotion", "promo"],
        "web": ["web", "event", "evenement", "clickstream", "digital"],
        "client": ["client", "customer"],
        "stock": ["stock", "inventaire", "inventory"],
    }
    available = list(snapshot.tables)
    resolved: dict[str, str | None] = {}
    for logical, words in keywords.items():
        declared = (configured.get(logical) or {}).get("table")
        if declared and declared in available:
            resolved[logical] = declared
            continue
        # priorité aux tables de faits pour 'ventes'/'web'/'stock', aux dim pour le reste
        prefix = "fact" if logical in {"ventes", "web", "stock"} else "dim"
        scored: list[tuple[int, str]] = []
        for name in available:
            norm = normalize(name)
            score = 0
            for word in words:
                if word in norm:
                    score += 50
            if score and norm.startswith(prefix):
                score += 20
            if logical == "web" and "vente" in norm:
                score -= 60
            if score:
                scored.append((score, name))
        scored.sort(key=lambda x: (-x[0], x[1]))
        resolved[logical] = scored[0][1] if scored else None
    return resolved


def merge_with_config(
    proposals: dict[str, TableMapping],
    configured: dict[str, Any],
    logical_to_role_key: dict[str, dict[str, str]] | None = None,
) -> dict[str, dict[str, str | None]]:
    """Fusionne l'heuristique et la configuration (la config gagne toujours)."""
    key_map = logical_to_role_key or CONFIG_KEY_BY_ROLE
    merged: dict[str, dict[str, str | None]] = {}
    for logical, mapping in proposals.items():
        cfg_table = configured.get(logical) or {}
        entry: dict[str, str | None] = {"table": mapping.table}
        for role, column in mapping.roles.items():
            cfg_key = key_map.get(logical, {}).get(role)
            override = cfg_table.get(cfg_key) if cfg_key else None
            entry[role] = override or column
            if override:
                logger.info(
                    "Mapping %s.%s forcé par configuration : %s", logical, role, override
                )
        merged[logical] = entry
    return merged


# Correspondance rôle -> clé du YAML, par table logique.
CONFIG_KEY_BY_ROLE: dict[str, dict[str, str]] = {
    "ventes": {
        "date": "date_column",
        "product_key": "product_key",
        "client_key": "client_key",
        "promotion_key": "promotion_key",
        "quantity": "quantity_column",
        "amount": "amount_column",
        "unit_price": "unit_price_column",
        "discount": "discount_column",
        "status": "status_column",
        "return_flag": "return_flag_column",
        "line_id": "line_id_column",
    },
    "produit": {
        "product_key": "key",
        "label": "label",
        "category": "category",
        "subcategory": "subcategory",
        "brand": "brand",
        "launch_date": "launch_date",
    },
    "date": {"product_key": "key", "date": "date_column"},
    "promotion": {
        "promotion_key": "key",
        "product_key": "product_key",
        "start_date": "start_date",
        "end_date": "end_date",
        "discount_rate": "discount_rate",
    },
    "web": {
        "date": "date_column",
        "product_key": "product_key",
        "event_type": "event_type_column",
        "session_key": "session_column",
    },
    "stock": {
        "product_key": "product_key",
        "date": "date_column",
        "stock_level": "level_column",
    },
}


def best_join_column(
    fact_values: pd.Series, dim: pd.DataFrame, min_overlap: float = 0.9
) -> tuple[str | None, float]:
    """Trouve la colonne de la dimension qui joint réellement avec la table de faits.

    Le nom ne suffit pas : un modèle en étoile porte souvent à la fois une clé
    de substitution (``produit_key``, celle qui joint) et une clé naturelle
    (``product_id``, qui ne joint pas). On choisit donc la colonne dont les
    **valeurs** recouvrent le mieux celles de la clé de faits, et on renvoie ce
    taux de recouvrement pour qu'il soit vérifiable.
    """
    values = set(fact_values.dropna().unique())
    if not values or dim.empty:
        return None, 0.0
    best_col, best_rate = None, 0.0
    for col in dim.columns:
        dim_values = set(dim[col].dropna().unique())
        if not dim_values:
            continue
        rate = len(values & dim_values) / len(values)
        if rate > best_rate:
            best_col, best_rate = col, rate
    if best_rate < min_overlap:
        return None, best_rate
    return best_col, best_rate


def mapping_report(proposals: dict[str, TableMapping]) -> pd.DataFrame:
    """Tableau lisible des rôles retenus et de leurs alternatives."""
    rows: list[dict[str, Any]] = []
    for logical, mapping in proposals.items():
        for role, column in mapping.roles.items():
            alternatives = [
                f"{c.column} ({c.score})" for c in mapping.candidates.get(role, [])[1:4]
            ]
            top = mapping.candidates.get(role, [])
            rows.append(
                {
                    "table_logique": logical,
                    "table_reelle": mapping.table,
                    "role": role,
                    "colonne_retenue": column,
                    "score": top[0].score if top else None,
                    "justification": top[0].reason if top else "aucun candidat",
                    "alternatives": ", ".join(alternatives) if alternatives else "",
                }
            )
    return pd.DataFrame(rows)
