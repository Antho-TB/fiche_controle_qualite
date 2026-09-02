"""
[TEST] Non regression de la resolution des codes scannes.

Le bug corrige ici est le plus grave du projet : un code carton EAN14 etait
resolu par un match approximatif qui remontait un article VOISIN dans 91 pour
cent des cas, produisant une fiche de controle au nom du mauvais article.
"""

import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.code_resolver import ean14_vers_ean13, normaliser_code, resoudre

CSV = os.path.join(os.path.dirname(__file__), "..", "0_Modele_Et_Donnees",
                   "article.csv")


@pytest.fixture(scope="module")
def referentiel() -> pd.DataFrame:
    """Charge le referentiel article reel."""
    df = pd.read_csv(CSV, sep=";", encoding="ISO-8859-1", dtype=str, header=0)
    df.columns = [str(c).strip().lower() for c in df.columns]
    for col in df.columns:
        df[col] = df[col].astype(str).str.strip()
    return df


def test_ean14_vers_ean13_pcb_et_spcb() -> None:
    """Les deux conditionnements d un meme article donnent le meme EAN13."""
    assert ean14_vers_ean13("23118220016204") == "3118220016200"
    assert ean14_vers_ean13("13118220016207") == "3118220016200"


def test_ean14_cle_invalide_refusee() -> None:
    """Un EAN14 dont la cle de controle est fausse n est pas converti."""
    assert ean14_vers_ean13("23118220016200") is None
    assert ean14_vers_ean13("123") is None


def test_normalisation_douchette() -> None:
    """Espaces et tirets d une lecture douchette sont neutralises."""
    assert normaliser_code(" 3118220016200-\n") == "3118220016200"


@pytest.mark.parametrize("colonne", ["ean", "ean_pcb", "ean_spcb", "ref"])
def test_resolution_exacte_rend_le_bon_article(referentiel, colonne) -> None:
    """
    Pour chaque type de code, le code d une ligne doit resoudre CETTE ligne.

    C est l assertion qui echouait avant le correctif sur ean_pcb et ean_spcb.
    """
    valides = referentiel[colonne].str.match(r"^\w+$", na=False)
    non_vides = ~referentiel[colonne].str.lower().isin(
        {"", "nan", "none", "null", "na", "-"})
    echantillon = referentiel[valides & non_vides].head(150)
    for _, ligne in echantillon.iterrows():
        resolution = resoudre(ligne[colonne], referentiel)
        assert resolution.trouve, "%s non resolu (%s)" % (ligne[colonne], colonne)
        assert resolution.fiable, "%s resolu sans fiabilite" % ligne[colonne]
        assert resolution.article["ref"] == ligne["ref"], (
            "%s : attendu ref=%s, obtenu ref=%s"
            % (ligne[colonne], ligne["ref"], resolution.article["ref"]))


def test_valeur_sentinelle_refusee(referentiel) -> None:
    """La chaine "nan" laissee par pandas ne doit jamais resoudre un article."""
    for sentinelle in ("nan", "", "NULL", "-"):
        assert not resoudre(sentinelle, referentiel).trouve


def test_code_inconnu_ne_ment_pas(referentiel) -> None:
    """Un code absent du referentiel ne doit jamais rendre un article fiable."""
    resolution = resoudre("999999999999", referentiel)
    assert not resolution.trouve
    assert resolution.type_code == "INCONNU"
