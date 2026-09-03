"""
[DIAG] Validation bout en bout de la resolution via le DWH.

Rejoue des cas reels tires des Packing Lists archivees et du referentiel :
scan unite, scan carton, remontee des commandes d achat, des lots, et du suivi
de conteneur deduit du nom de fichier. Lecture seule.

Usage : python scripts/diagnostic_dwh.py
"""

import logging
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
for _bruyant in ("azure", "azure.identity", "urllib3",
                 "azure.core.pipeline.policies.http_logging_policy"):
    logging.getLogger(_bruyant).setLevel(logging.WARNING)

from src.dwh_repository import DWHRepository, analyser_nom_packing_list

CAS_CODES = [
    ("3118220016200", "EAN13 unite, present aussi chez GDD"),
    ("23118224448704", "EAN14 carton PCB"),
    ("32000006", "reference interne"),
    ("21870001", "reference vue dans PL-SZSE2601808"),
]
CAS_PACKING_LISTS = [
    "PL-SZSE2602436-TLLU4162583.pdf",
    "PL-SZSE2601807-RESU2004119.pdf",
    "PL-SZSE2600297-YMMU1140160.pdf",
]


def main() -> None:
    """Affiche la resolution obtenue pour chaque cas."""
    depot = DWHRepository()
    if not depot.disponible:
        print("DWH indisponible : %s" % depot.motif_indisponible)
        return

    for code, libelle in CAS_CODES:
        print("\n=== %s (%s)" % (code, libelle))
        article = depot.chercher_article(code)
        if not article:
            print("    non resolu")
            continue
        print("    %s | %s | %s | type=%s"
              % (article.code_article, article.designation[:45],
                 article.societe, article.type_code))
        commandes = depot.commandes_pour_article(article.id_article, limite=3)
        for commande in commandes:
            print("    PO %s | frn %s | qte %s | reception %s | ouverte %s | ETD %s"
                  % (commande.numero, commande.fournisseur, commande.quantite,
                     commande.etat_reception, commande.ouverte,
                     commande.etd_confirme))
        if not commandes:
            print("    aucune commande d achat pour cet article")
        lots = depot.lots_pour_article(article.code_article, limite=4)
        print("    lots : %s" % (", ".join(lots) if lots else "aucun"))

    for nom in CAS_PACKING_LISTS:
        bl, conteneur = analyser_nom_packing_list(nom)
        print("\n=== %s -> BL %s / conteneur %s" % (nom, bl, conteneur))
        contexte = depot.contexte_conteneur(bl, conteneur)
        if not contexte:
            print("    inconnu du suivi transport")
            continue
        print("    frn %s | ETA %s | livraison %s | transitaire %s"
              % (contexte.fournisseur, contexte.eta, contexte.date_livraison,
                 contexte.transitaire))


if __name__ == "__main__":
    main()
