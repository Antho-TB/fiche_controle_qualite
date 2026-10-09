"""
[PREFLIGHT] Controle des prerequis du poste avant utilisation du Scanner Qualite.

A lancer sur le poste du service qualite, avant la premiere session de scan et
apres chaque redeploiement. Chaque ligne est un fait verifie, pas une supposition.
Aucune ecriture en base, aucune fiche generee.

Appele par `Scanner_Qualite.exe --verifier-poste` ou par
`python scripts/verifier_poste.py`.
"""

import logging
import os
import socket
import sys

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
for _bruyant in ("azure", "azure.identity", "urllib3",
                 "azure.core.pipeline.policies.http_logging_policy"):
    logging.getLogger(_bruyant).setLevel(logging.ERROR)

HOTE_DWH = "psql-dtpf-psql-prod.postgres.database.azure.com"
PORT_DWH = 5432
LARGEUR = 62


def _ligne(libelle: str, ok: bool, detail: str = "") -> bool:
    """Affiche une ligne de resultat et rend le booleen tel quel."""
    marque = "OK   " if ok else "ECHEC"
    print("  [%s] %-28s %s" % (marque, libelle, detail))
    return ok


def verifier_reseau_dwh() -> bool:
    """Resolution DNS puis ouverture TCP vers le DWH Azure."""
    try:
        adresse = socket.gethostbyname(HOTE_DWH)
    except OSError as e:
        return _ligne("DNS DWH", False, "%s" % e)
    _ligne("DNS DWH", True, adresse)
    try:
        with socket.create_connection((HOTE_DWH, PORT_DWH), timeout=8):
            return _ligne("TCP 5432 DWH", True, "joignable")
    except OSError as e:
        return _ligne("TCP 5432 DWH", False,
                      "%s (VPN site a site ou pare-feu)" % type(e).__name__)


def verifier_identite_azure() -> bool:
    """
    Verifie que l identite Azure permet de LIRE un secret, pas seulement
    d obtenir un jeton.

    Junior Tip : un jeton obtenu ne prouve rien. Le premier controle demandait
    un jeton brut et rendait ECHEC alors que la lecture de tb-sylob-client
    fonctionnait juste apres. Un prerequis se teste sur l operation reelle dont
    l application a besoin, sinon on diagnostique un faux probleme et on rate le
    vrai, qui etait ici une autorisation RBAC manquante sur un AUTRE secret.
    """
    from src.azure_auth import obtenir_credential
    credential = obtenir_credential()
    if credential is None:
        return _ligne("Identite Azure", False, "azure-identity absent")
    try:
        from azure.keyvault.secrets import SecretClient
        kv = SecretClient(vault_url="https://kv-dtpf-prod.vault.azure.net/",
                          credential=credential)
        kv.get_secret("tb-sylob-client")
        return _ligne("Identite Azure", True, "lecture Key Vault autorisee")
    except Exception as e:
        detail = "acces refuse (RBAC)" if "Forbidden" in str(e) else type(e).__name__
        return _ligne("Identite Azure", False, detail)


def verifier_sylob() -> bool:
    """Credentials Sylob et reponse de l API."""
    from src.sylob_api import SylobAPI
    api = SylobAPI()
    _ligne("Credentials Sylob", bool(api.user), api.source_credentials or "aucun")
    return _ligne("API Sylob", api.is_healthy(), "reponse XML valide")


def verifier_dwh() -> bool:
    """Lecture effective du referentiel article dans le DWH."""
    from src.dwh_repository import DWHRepository
    depot = DWHRepository()
    if not depot.disponible:
        return _ligne("Lecture DWH", False, depot.motif_indisponible)
    return _ligne("Lecture DWH", True, "articles3 interrogeable")


def verifier_ocr() -> bool:
    """Binaires OCR portables et langues installees."""
    from src.ocr_engine import OCREngine, _dossier_outils
    moteur = OCREngine()
    if not moteur.disponible:
        return _ligne("OCR local", False, "ni RapidOCR ni tesseract")
    if "RapidOCR" in moteur.moteurs:
        return _ligne("OCR local", True, ", ".join(moteur.moteurs))
    tessdata = os.path.join(_dossier_outils(), "tesseract", "tessdata")
    manquantes = [langue for langue in ("eng", "fra", "chi_sim")
                  if not os.path.exists(os.path.join(tessdata,
                                                     "%s.traineddata" % langue))]
    if manquantes:
        return _ligne("OCR local", False,
                      "langues manquantes : %s" % ", ".join(manquantes))
    return _ligne("OCR local", True, "eng, fra, chi_sim")


def verifier_fichiers() -> bool:
    """Modele Excel present et dossier de sortie accessible en ecriture."""
    from src.excel_handler import get_base_path
    racine = get_base_path()
    modele = os.path.join(racine, "0_Modele_Et_Donnees",
                          "FOR-ACH-30-2 Fiche d'inspection produit-Controle reception.xlsx")
    dossier_modele = os.path.join(racine, "0_Modele_Et_Donnees")
    trouve = os.path.isdir(dossier_modele) and any(
        f.lower().endswith(".xlsx") for f in os.listdir(dossier_modele))
    _ligne("Modele de fiche", trouve, dossier_modele if trouve else "introuvable")
    sortie = os.path.join(racine, "2_Fiches_Creees")
    try:
        os.makedirs(sortie, exist_ok=True)
        temoin = os.path.join(sortie, ".ecriture_test")
        with open(temoin, "w", encoding="utf-8") as flux:
            flux.write("test")
        os.remove(temoin)
        return _ligne("Ecriture des fiches", True, sortie)
    except Exception as e:
        return _ligne("Ecriture des fiches", False, "%s" % type(e).__name__)


def main() -> int:
    """Enchaine les controles et rend un code de sortie exploitable."""
    print("\n" + "=" * LARGEUR)
    print("   CONTROLE DES PREREQUIS -- SCANNER QUALITE")
    print("=" * LARGEUR + "\n")

    bloquants = [verifier_fichiers(), verifier_identite_azure(), verifier_sylob()]
    print()
    non_bloquants = [verifier_reseau_dwh(), verifier_dwh(), verifier_ocr()]

    print("\n" + "-" * LARGEUR)
    if all(bloquants) and all(non_bloquants):
        print("  Tout est en place. Le scan peut demarrer.")
        code = 0
    elif all(bloquants):
        print("  Mode degrade utilisable : le scan fonctionne, mais le PO, le")
        print("  lot ou les Packing Lists scannees seront incomplets.")
        code = 1
    else:
        print("  Prerequis bloquants manquants : corriger avant d utiliser")
        print("  l application au poste reception.")
        code = 2
    print("-" * LARGEUR + "\n")
    return code


if __name__ == "__main__":
    sys.exit(main())