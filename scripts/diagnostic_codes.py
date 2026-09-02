"""
[DIAG] Mesure du taux de resolution des codes du referentiel article.

But : verifier qu un code carton (EAN14 PCB ou SPCB) est desormais resolu de
facon fiable, et chiffrer ce que l ancienne implementation ratait.
Lecture seule, aucun effet de bord.
"""

import logging
import os
import random
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
logging.basicConfig(level=logging.ERROR)

import pandas as pd

from src.code_resolver import resoudre

ECHANTILLON = 300  # borne le cout : chaque test balaie 8874 lignes

CSV = os.path.join(os.path.dirname(__file__), "..",
                   "0_Modele_Et_Donnees", "article.csv")


def _ancienne_resolution(code: str, df: pd.DataFrame) -> bool:
    """Reproduit chercher_article() historique : ean, puis ref, puis flou."""
    if not df[df["ean"] == code].empty:
        return True
    if not df[df["ref"] == code].empty:
        return True
    if len(code) >= 10:
        return not df[df["ean"].str.contains(code[1:11], na=False,
                                            regex=False)].empty
    return False


def main() -> None:
    """Compare ancienne et nouvelle resolution sur les 3 types de code."""
    df = pd.read_csv(CSV, sep=";", encoding="ISO-8859-1", dtype=str, header=0)
    df.columns = [str(c).strip().lower() for c in df.columns]
    for col in df.columns:
        df[col] = df[col].astype(str).str.strip()

    for colonne, libelle in (("ean", "EAN13 unite"),
                             ("ean_pcb", "EAN14 carton PCB"),
                             ("ean_spcb", "EAN14 sous-carton SPCB"),
                             ("ref", "Reference interne")):
        codes = [c for c in df[colonne].tolist() if c and c != "nan"]
        if len(codes) > ECHANTILLON:
            codes = random.Random(42).sample(codes, ECHANTILLON)
        if not codes:
            print("%-26s aucune valeur" % libelle)
            continue
        avant = sum(1 for c in codes if _ancienne_resolution(c, df))
        apres = sum(1 for c in codes if resoudre(c, df).trouve)
        fiables = sum(1 for c in codes if resoudre(c, df).fiable)
        print("%-26s n=%-6d avant=%5.1f%%  apres=%5.1f%%  dont fiable=%5.1f%%"
              % (libelle, len(codes), 100 * avant / len(codes),
                 100 * apres / len(codes), 100 * fiables / len(codes)))


if __name__ == "__main__":
    main()
