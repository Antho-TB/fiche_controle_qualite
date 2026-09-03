"""
[DIAG] Validation de la chaine complete de resolution, sans interaction.

Rejoue des scans reels et affiche ce que la fiche porterait : article, PO, lot
Sylob, lot fournisseur, fournisseur, et la source de chaque information.
Lecture seule cote DWH, aucune fiche generee.
"""

import logging
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
for _bruyant in ("azure", "azure.identity", "urllib3",
                 "azure.core.pipeline.policies.http_logging_policy"):
    logging.getLogger(_bruyant).setLevel(logging.ERROR)

from src.data_loader import DataLoader

CAS = [
    ("3118220016200", "EAN13 unite"),
    ("23118224448704", "EAN14 carton PCB"),
    ("32000006", "reference vue dans PL-SZSE2601807"),
    ("21870001", "reference vue dans PL-SZSE2601808"),
    ("999999999999", "code inconnu"),
]


def main() -> None:
    """Affiche la resolution complete pour chaque scan simule."""
    loader = DataLoader()
    print("DWH disponible : %s" % (loader.dwh.disponible if loader.dwh else False))
    print("Sylob disponible : %s" % loader.sylob.is_healthy())
    print("Referentiel CSV : %d articles\n" % loader.get_article_count())

    for code, libelle in CAS:
        resolution = loader.resoudre_code(code)
        print("=== %s (%s)" % (code, libelle))
        if not resolution.trouve:
            print("    non resolu : %s\n" % resolution.message)
            continue
        article = resolution.article
        print("    article  : %s | %s" % (article.get("ref"),
                                          str(article.get("designation"))[:45]))
        print("    source   : %s (type %s, fiable %s)"
              % (article.get("source"), resolution.type_code, resolution.fiable))
        enrichi = loader.enrichir_depuis_dwh(article)
        print("    PO       : %s%s"
              % (enrichi["po"] or "(vide)",
                 "  [%d candidat(s), arbitrage requis]" % len(enrichi["candidats_po"])
                 if enrichi["ambigu"] else ""))
        print("    lot Sylob: %s" % (enrichi["lot_sylob"] or "(vide)"))
        print("    frn      : %s\n" % (enrichi["fournisseur"] or "(vide)"))


if __name__ == "__main__":
    main()
