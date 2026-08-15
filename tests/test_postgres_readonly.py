"""Garanties de lecture seule et de non-divulgation de la connexion PostgreSQL.

Trois familles de tests, sans aucune connexion réseau :

* **statiques** : le code source de l'inspecteur ne contient aucune instruction
  d'écriture ;
* **mockés** : une fausse connexion enregistre les requêtes émises et vérifie
  qu'elles passent toutes le filtre lecture seule et qu'un ROLLBACK est émis ;
* **expurgation** : aucun identifiant ne peut fuiter dans un message ou un log.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.config.settings import PROJECT_ROOT, sanitize_database_url
from src.data.connection import ReadOnlyViolation, assert_read_only

SCRIPT = PROJECT_ROOT / "scripts" / "inspect_postgres_full.py"

# Valeurs FICTIVES : aucun identifiant réel n'apparaît dans les tests.
FAKE_URL = "postgresql://utilisateur:MotDePasseSecret@db.exemple.supabase.co:5432/postgres"
FAKE_URL_BRACKETS = "postgresql://utilisateur:[MotDePasseSecret]@db.exemple.supabase.co:5432/postgres"


# ---------------------------------------------------------------------------
# Tests statiques sur le source
# ---------------------------------------------------------------------------
def _sql_literals(source: str) -> list[str]:
    """Extrait les chaînes qui ressemblent à du SQL."""
    literals = re.findall(r'"""(.*?)"""', source, re.DOTALL)
    literals += re.findall(r"'''(.*?)'''", source, re.DOTALL)
    literals += re.findall(r'"([^"\n]{12,})"', source)
    literals += re.findall(r"'([^'\n]{12,})'", source)
    return [s for s in literals if re.search(r"\bSELECT\b", s, re.IGNORECASE)]


def test_le_script_existe():
    assert SCRIPT.exists()


def test_aucune_instruction_ecriture_dans_le_sql():
    source = SCRIPT.read_text(encoding="utf-8")
    for sql in _sql_literals(source):
        assert_read_only(sql)  # lève ReadOnlyViolation si écriture détectée


def test_le_script_ouvre_une_session_read_only():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "readonly=True" in source
    assert "statement_timeout" in source
    assert "lock_timeout" in source
    assert "idle_in_transaction_session_timeout" in source
    assert "rollback" in source.lower()


def test_le_script_ne_contient_aucun_identifiant_en_dur():
    source = SCRIPT.read_text(encoding="utf-8")
    assert not re.search(r"postgres(ql)?://[^<\s\"']*:[^<\s\"']+@", source), (
        "Une chaîne de connexion semble écrite en dur dans le script."
    )


# ---------------------------------------------------------------------------
# Tests mockés : rien ne sort du filtre lecture seule
# ---------------------------------------------------------------------------
class FakeCursor:
    def __init__(self, journal: list[str]) -> None:
        self._journal = journal
        self.description = [("n",)]

    def execute(self, sql, params=None):  # noqa: D102
        self._journal.append(str(sql))

    def fetchall(self):  # noqa: D102
        return [(1,)]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeConnection:
    """Connexion factice qui journalise tout et refuse le commit."""

    def __init__(self) -> None:
        self.journal: list[str] = []
        self.readonly = None
        self.rolled_back = False
        self.closed = False

    def set_session(self, readonly=None, autocommit=None):  # noqa: D102
        self.readonly = readonly

    def cursor(self):  # noqa: D102
        return FakeCursor(self.journal)

    def rollback(self):  # noqa: D102
        self.rolled_back = True

    def commit(self):  # noqa: D102
        raise AssertionError("Aucun commit ne doit être émis par l'inspection.")

    def close(self):  # noqa: D102
        self.closed = True


@pytest.fixture
def inspector(monkeypatch):
    import scripts.inspect_postgres_full as mod

    fake = FakeConnection()
    monkeypatch.setattr(mod, "psycopg2", type("m", (), {"connect": lambda *a, **k: fake}), raising=False)

    class Stub(mod.ReadOnlyInspector):
        def __init__(self):  # noqa: D107
            self._conn = fake
            self._settings_applied = []
            self._settings_refused = []

    return Stub(), fake


def test_la_session_est_ouverte_en_lecture_seule():
    import scripts.inspect_postgres_full as mod

    fake = FakeConnection()

    class FakePsycopg2:
        @staticmethod
        def connect(url, connect_timeout=None):
            return fake

    import sys

    saved = sys.modules.get("psycopg2")
    sys.modules["psycopg2"] = FakePsycopg2
    try:
        mod.ReadOnlyInspector(FAKE_URL)
    finally:
        if saved is not None:
            sys.modules["psycopg2"] = saved
        else:
            del sys.modules["psycopg2"]

    assert fake.readonly is True
    assert any("statement_timeout" in s for s in fake.journal)
    assert any("lock_timeout" in s for s in fake.journal)


def test_une_requete_ecriture_est_refusee(inspector):
    insp, fake = inspector
    with pytest.raises(ReadOnlyViolation):
        insp.query("DELETE FROM public.fact_ventes")
    assert not any("DELETE" in s.upper() for s in fake.journal)


def test_une_requete_lecture_est_journalisee(inspector):
    insp, fake = inspector
    insp.query("SELECT count(*) AS n FROM public.fact_ventes")
    assert len(fake.journal) == 1


def test_la_fermeture_emet_un_rollback(inspector):
    insp, fake = inspector
    insp.close()
    assert fake.rolled_back is True
    assert fake.closed is True


# ---------------------------------------------------------------------------
# Expurgation et nettoyage de la chaîne de connexion
# ---------------------------------------------------------------------------
def test_les_crochets_du_gabarit_sont_retires():
    assert sanitize_database_url(FAKE_URL_BRACKETS) == FAKE_URL


def test_les_caracteres_speciaux_sont_encodes():
    url = sanitize_database_url("postgresql://u:a@b#c@db.exemple.co:5432/postgres")
    assert "%40" in url and "%23" in url
    assert url.count("@") == 1


def test_url_sans_mot_de_passe_est_inchangee():
    url = "postgresql://utilisateur@db.exemple.co:5432/postgres"
    assert sanitize_database_url(url) == url


@pytest.mark.parametrize(
    "message",
    [
        f"could not connect using {FAKE_URL}",
        'FATAL: password authentication failed, password=MotDePasseSecret',
        "could not translate host name db.exemple.supabase.co to address",
    ],
)
def test_les_messages_derreur_sont_expurges(message):
    from scripts.inspect_postgres_full import redact

    nettoye = redact(message)
    assert "MotDePasseSecret" not in nettoye
    assert "db.exemple.supabase.co" not in nettoye


def test_le_resume_de_connexion_ne_contient_aucun_secret():
    from src.config.settings import DbCredentials

    creds = DbCredentials(database_url=FAKE_URL, database_url_source="DATABASE_URL")
    resume = str(creds.safe_summary())
    assert "MotDePasseSecret" not in resume
    assert "utilisateur" not in resume
    # Le nom de la variable est publiable, sa valeur non.
    assert "DATABASE_URL" in resume
