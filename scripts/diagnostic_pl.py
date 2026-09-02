"""
[DIAG] Taux d exploitation des Packing Lists, fournisseur par fournisseur.

But : disposer d une mesure AVANT / APRES a chaque evolution du parsing. Sans
ce harnais, corriger un fournisseur cassait silencieusement un autre, ce qui
est exactement l historique de ce module.

Usage :
    python scripts/diagnostic_pl.py [dossier_pdf]

Lecture seule : aucun PDF n est deplace, aucune fiche n est generee.
"""

import glob
import json
import logging
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
logging.basicConfig(level=logging.ERROR, format="%(levelname)s %(message)s")

from src.pdf_extractor import PDFExtractor

DOSSIER_DEFAUT = os.path.join(os.path.dirname(__file__), "..",
                              "1_Packing_Lists_A_Traiter", "archives")


def analyser(dossier: str) -> list[dict]:
    """
    Analyse chaque PDF du dossier sans effet de bord.

    Args:
        dossier: Dossier contenant les Packing Lists a mesurer.

    Returns:
        Liste de rapports par fichier.
    """
    extracteur = PDFExtractor.__new__(PDFExtractor)
    extracteur.pdf_dir = dossier
    extracteur.articles_pdf = {}
    extracteur.rapports = []
    extracteur.ocr_available = False
    extracteur.adi_available = False
    extracteur._ocr = None
    extracteur._init_ocr()
    for chemin in sorted(glob.glob(os.path.join(dossier, "*.pdf"))):
        extracteur._extract_from_pdf(chemin)
    return extracteur.rapports


def main() -> None:
    """Affiche le tableau de mesure et un resume chiffre."""
    dossier = sys.argv[1] if len(sys.argv) > 1 else DOSSIER_DEFAUT
    rapports = analyser(dossier)
    if not rapports:
        print("Aucune Packing List dans %s" % dossier)
        return
    print("%-46s %-8s %-4s %s" % ("FICHIER", "STATUT", "N", "DETAIL"))
    for rapport in rapports:
        print("%-46s %-8s %-4d %s" % (rapport["fichier"][:45], rapport["statut"],
                                      rapport["n_articles"], rapport["detail"]))
    total = len(rapports)
    ok = sum(1 for r in rapports if r["statut"] == "OK")
    print("\nTOTAL %d Packing List(s) | exploitables %d (%.0f%%) | en echec %d"
          % (total, ok, 100 * ok / total, total - ok))
    print(json.dumps({r["fichier"]: r["statut"] for r in rapports},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
