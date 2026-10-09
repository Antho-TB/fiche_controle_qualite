"""
[ARCHITECTURE] Orchestrateur CLI (fiche_de_controle)

Stratégie :
- Status board au démarrage : état Sylob / ADI / CSV affiché avant la boucle scan
- Flow : CSV lookup → Sylob enrichissement → PDF fallback → CSV fallback
- Si article inconnu dans CSV et Sylob connecté : tentative Sylob par EAN (nouveaux produits)
- Feedback source sur chaque scan : [Sylob] / [ADI] / [PyPDF] / [CSV]
"""

import sys
import os
import logging
from typing import Optional

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.data_loader import DataLoader
from src.excel_handler import ExcelHandler
from src.pdf_extractor import PDFExtractor

logger = logging.getLogger(__name__)


def afficher_status_board(
    loader: DataLoader,
    pdf_data: PDFExtractor,
) -> None:
    """Affiche l'état des services au démarrage."""
    print("\n" + "=" * 52)
    print("      INTERFACE AUTOMATISÉE — SERVICE QUALITÉ")
    print("=" * 52)

    sylob_ok = loader.sylob.is_healthy()
    csv_count = loader.get_article_count()
    adi_ok = pdf_data.adi_available

    sylob_label = "CONNECTÉ ✓" if sylob_ok else "HORS LIGNE — mode dégradé"
    adi_label = "ACTIF ✓" if adi_ok else "INDISPONIBLE — fallback PyPDF"
    csv_label = f"CHARGÉ ✓ ({csv_count} articles)" if csv_count > 0 else "ABSENT"

    print(f"\n  [Sylob]   {sylob_label}")
    print(f"  [DocInt]  {adi_label}")
    print(f"  [CSV]     {csv_label}")

    resume = pdf_data.resume_ingestion()
    total = sum(resume.values())
    if total:
        print(f"  [PL]      {resume['OK']} exploitable(s) / {total} "
              f"— {resume['ECHEC'] + resume['ERREUR']} en echec")
        for rapport in pdf_data.rapports:
            if rapport["statut"] in ("ECHEC", "ERREUR"):
                print(f"            [!] {rapport['fichier']} : {rapport['detail']}")
    else:
        print("  [PL]      aucune Packing List dans la file d attente")
    print()
    print("=" * 52)


def _indice_pdf(pdf_data: PDFExtractor, code_scanne: str,
                ref: str) -> tuple[str, str, str]:
    """
    Extrait de la Packing List les indices utiles, sans leur faire confiance.

    Returns:
        Tuple (po_indice, lot_fournisseur, fournisseur_pdf). Chaines vides si
        la Packing List ne dit rien de fiable sur cet article.
    """
    infos = pdf_data.chercher_infos_pdf(code_article=code_scanne, ref_article=ref)
    if not infos:
        return "", "", ""
    premier = infos[0]
    if premier.get("po_ambigu"):
        candidats = premier.get("po_candidats", [])
        print("     [PL] Plusieurs commandes dans l en-tete : "
              + ", ".join(candidats))
        return "", "", premier.get("fournisseur", "")
    return (premier.get("po", ""), premier.get("lot", ""),
            premier.get("fournisseur", ""))


def _choisir_commande(candidats: list) -> Optional[object]:
    """
    Fait arbitrer par l operateur la commande d achat concernee.

    Les candidats viennent du DWH, donc chacun porte son fournisseur, sa
    quantite et son etat de reception : l operateur choisit sur des faits, pas
    sur un numero nu.
    """
    print("     [ATTENTION] Plusieurs commandes portent cet article :")
    for index, commande in enumerate(candidats, start=1):
        print("        %d. PO %s | %s | %.0f %s | reception %s"
              % (index, commande.numero, commande.fournisseur[:38],
                 commande.quantite, "pce", commande.etat_reception))
    saisie = input("     Numero de la ligne (Entree = laisser le PO vide) : ").strip()
    if not saisie.isdigit() or not 1 <= int(saisie) <= len(candidats):
        print("     [INFO] PO laisse vide, a completer manuellement.")
        return None
    return candidats[int(saisie) - 1]


def _enrichir_donnees(
    article: dict,
    loader: DataLoader,
    pdf_data: PDFExtractor,
    code_scanne: str,
) -> tuple[str, str, str, str]:
    """
    Construit PO, lot Sylob, lot fournisseur et fournisseur.

    Ordre : DWH (source de verite), Packing List (indice de desambiguisation),
    API Sylob puis CSV (repli hors ligne). Une case vide est preferee a une
    case fausse.

    Returns:
        Tuple (po, lot_sylob, lot_fournisseur, fournisseur).
    """
    ref = article.get("ref", "")
    po_indice, lot_fournisseur, fournisseur_pdf = _indice_pdf(
        pdf_data, code_scanne, ref)

    resultat = loader.enrichir_depuis_dwh(article, po_indice=po_indice)
    po = resultat["po"]
    lot_sylob = resultat["lot_sylob"]
    fournisseur = resultat["fournisseur"]

    if resultat["ambigu"]:
        choisie = _choisir_commande(resultat["candidats_po"])
        if choisie is not None:
            po, fournisseur = choisie.numero, choisie.fournisseur

    if po:
        print("     [DWH] PO=%s | %s" % (po, fournisseur[:40]))
    if lot_sylob:
        print("     [DWH] Lot Sylob=%s" % lot_sylob)

    po, lot_sylob = _completer_par_sylob(loader, code_scanne, ref, po, lot_sylob)
    return _completer_par_csv(article, po, lot_sylob, lot_fournisseur,
                              fournisseur or fournisseur_pdf)


def _completer_par_sylob(loader: DataLoader, code_scanne: str, ref: str,
                         po: str, lot: str) -> tuple[str, str]:
    """Comble les trous restants avec l API Sylob temps reel."""
    if po and lot:
        return po, lot
    resultat = loader.enrichir_depuis_sylob(ean=code_scanne, ref=ref)
    if not resultat:
        return po, lot
    ajouts = []
    if not po and resultat.get("po"):
        po = resultat["po"]
        ajouts.append("PO:%s" % po)
    if not lot and resultat.get("lot"):
        lot = resultat["lot"]
        ajouts.append("LOT:%s" % lot)
    if ajouts:
        print("     [Sylob] Complete : %s" % ", ".join(ajouts))
    return po, lot


def _completer_par_csv(article: dict, po: str, lot_sylob: str,
                       lot_fournisseur: str,
                       fournisseur: str) -> tuple[str, str, str, str]:
    """Dernier repli hors ligne : les colonnes du referentiel CSV."""
    def propre(cle: str) -> str:
        return str(article.get(cle, "")).replace("nan", "").strip()

    ajouts = []
    if not po and propre("po"):
        po = propre("po")
        ajouts.append("PO:%s" % po)
    if not lot_sylob and propre("lot"):
        lot_sylob = propre("lot")
        ajouts.append("LOT:%s" % lot_sylob)
    if not fournisseur and propre("fournisseur"):
        fournisseur = propre("fournisseur")
        ajouts.append("Fourn:%s" % fournisseur)
    if ajouts:
        print("     [CSV] Repli : %s" % ", ".join(ajouts))
    if not po and not lot_sylob:
        print("     [!] Aucun PO ni lot identifie. La fiche sortira avec ces "
              "cases vides, a completer a la main.")
    return po, lot_sylob, lot_fournisseur, fournisseur


def _traiter_article_inconnu(
    code_scanne: str,
    loader: DataLoader,
    handler: ExcelHandler,
    pdf_data: PDFExtractor,
) -> None:
    """
    Gère le cas où l'article est inconnu du CSV.
    Si Sylob est connecté, tente un appel EAN pour les nouveaux produits.
    """
    if not loader.sylob.is_healthy():
        print(f"[!] Code '{code_scanne}' inconnu du CSV. Sylob hors ligne — impossible de vérifier.")
        return

    result = loader.enrichir_depuis_sylob(ean=code_scanne)
    if result and (result.get('po') or result.get('lot')):
        print(f"     [Sylob] Nouveau produit détecté — CMD={result.get('po')} LOT={result.get('lot')}")
        article_minimal = {
            'ean': code_scanne, 'ref': code_scanne, 'designation': f'Article EAN {code_scanne}',
            'po': result.get('po', ''), 'lot': result.get('lot', ''), 'fournisseur': '',
        }
        chemin = handler.generer_fiche(article_minimal)
        if chemin:
            print(f"[SUCCÈS] Fiche créée (nouveau produit) : {chemin}")
        else:
            print("[ERREUR] Impossible de créer la fiche.")
    else:
        print(f"[!] Code '{code_scanne}' inconnu du CSV et absent de Sylob.")
        print("    Vérifiez qu'il s'agit bien d'une référence interne ou EAN valide.")


def _confirmer_resolution(article: dict, code_scanne: str) -> bool:
    """
    Fait valider par l operateur une correspondance article non fiable.

    Junior Tip : un code carton EAN14 tombait avant dans un match approximatif
    qui remontait un article VOISIN dans 91 pour cent des cas. La fiche de
    controle portait alors le mauvais article, en silence. Desormais toute
    correspondance non certaine passe par une confirmation humaine.
    """
    if article.get("_fiable", True):
        type_code = article.get("_resolution", "")
        if type_code in ("EAN14_PCB", "EAN14_SPCB", "EAN14_DERIVE"):
            print(f"     [Code] Carton reconnu ({type_code}) -> "
                  f"{article.get('designation', '')}")
        return True
    print(f"     [ATTENTION] {article.get('_message_resolution', '')}")
    print(f"     Article propose : {article.get('ref', '')} — "
          f"{article.get('designation', '')}")
    return input("     Confirmer cet article ? (O/N) : ").strip().upper() == "O"


def _choisir_po(candidats: list[str], lots: list[str]) -> Optional[tuple[str, str]]:
    """
    Demande a l operateur quelle commande concerne le colis scanne.

    Args:
        candidats: Numeros de commande lus dans l en-tete de la Packing List.
        lots: Numeros de lot lus dans le meme en-tete, dans le meme ordre.

    Returns:
        Tuple (po, lot) choisi, ou None si l operateur ne tranche pas.
    """
    if not candidats:
        return None
    for index, po in enumerate(candidats, start=1):
        lot = lots[index - 1] if index - 1 < len(lots) else ""
        print(f"        {index}. PO {po}" + (f"  (lot {lot})" if lot else ""))
    saisie = input("     Numero de la commande concernee (Entree = laisser "
                   "vide) : ").strip()
    if not saisie.isdigit() or not 1 <= int(saisie) <= len(candidats):
        print("     [INFO] PO laisse vide, a completer manuellement.")
        return None
    index = int(saisie) - 1
    return candidats[index], lots[index] if index < len(lots) else ""


def lancer_session_scan() -> None:
    """Lance la boucle interactive d'écoute de la douchette."""
    try:
        loader = DataLoader()
        handler = ExcelHandler()
        pdf_data = PDFExtractor()
    except Exception as e:
        print(f"[-] Erreur critique d'initialisation : {e}")
        return

    afficher_status_board(loader, pdf_data)

    print("\n[INFO] Astuce : utilisez votre douchette sur le code-barres de l'article.")
    print("[INFO] Tapez 'STOP' pour terminer la session.\n")

    while True:
        try:
            code_scanne = input(">>>> SCAN ARTICLES : ").strip()
            if not code_scanne:
                continue

            if code_scanne.upper() == 'STOP':
                print("\n[FIN] Session terminée.")
                choix = input("Archiver les Packing Lists actuelles ? (O/N) : ").strip().upper()
                if choix == 'O':
                    pdf_data.archiver_pdfs()
                    print("[INFO] PDF archivés.")
                break

            article = loader.chercher_article(code_scanne)

            if not article:
                _traiter_article_inconnu(code_scanne, loader, handler, pdf_data)
                print()
                continue

            if not _confirmer_resolution(article, code_scanne):
                print("     [ANNULE] Aucune fiche generee.\n")
                continue

            final_po, final_lot, lot_fournisseur, final_fournisseur = (
                _enrichir_donnees(article, loader, pdf_data, code_scanne))

            article_clone = {**article, 'po': final_po, 'lot': final_lot,
                             'lot_fournisseur': lot_fournisseur,
                             'fournisseur': final_fournisseur}

            print("     Génération de la fiche Excel...")
            chemin_fiche = handler.generer_fiche(article_clone)
            if chemin_fiche:
                print(f"[SUCCÈS] Fiche créée : {chemin_fiche}")
            else:
                print("[ERREUR] Impossible de sauvegarder — vérifiez que le fichier n'est pas ouvert.")

            print()
            choix_arch = input(
                "     → Entrée = PROCHAIN SCAN   |   'A' = ARCHIVER les PDF : "
            ).strip().upper()
            if choix_arch == 'A':
                pdf_data.archiver_pdfs()
                print("     [INFO] PDF archivés.")
            print()

        except KeyboardInterrupt:
            print("\nArrêt par l'opérateur.")
            break
        except Exception as e:
            logger.error(f"Exception inattendue dans la boucle principale : {e}", exc_info=True)
            print(f"\n[!] Erreur inattendue : {e}")


def main() -> int:
    """
    Point d entree. `--verifier-poste` lance le controle des prerequis.

    Junior Tip : l operateur du service qualite n a pas Python installe. Le
    controle des prerequis doit donc etre appelable depuis l executable lui
    meme, sinon personne ne le lancera jamais.
    """
    if "--verifier-poste" in sys.argv:
        from src.preflight import main as verifier
        return verifier()
    lancer_session_scan()
    return 0


if __name__ == "__main__":
    sys.exit(main())
