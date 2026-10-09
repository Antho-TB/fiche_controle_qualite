"""
[AUTH] Identite Google de l'application (Drive partage et Vertex AI Gemini).

Strategie :
- Un seul compte de service Google, porte par le projet GCP dedie a la fiche
  de controle (tb-ai-fichectrl-prod) : son cout Gemini se lit a part, et il est
  membre du Drive partage du service qualite.
- Sa cle JSON est au Key Vault (Config.GCP_SECRET_SA), lue par l'identite
  managee de la Web App. En developpement, GOOGLE_APPLICATION_CREDENTIALS peut
  pointer un fichier local.
- Les identifiants sont memorises par portee : une lecture Key Vault par
  processus, pas une par appel Drive.

Junior Tip : la cible a terme est la federation d'identite (l'identite managee
Azure echangee contre un jeton Google, sans aucune cle). Elle demande un
fournisseur de jeton specifique a App Service ; la cle au coffre est le premier
pas, elle ne sort jamais du Key Vault ni de la memoire du processus.
"""

import json
import logging
import os
import threading
from typing import Optional

from src.config import Config

logger = logging.getLogger(__name__)

PORTEE_DRIVE = "https://www.googleapis.com/auth/drive"
PORTEE_CLOUD = "https://www.googleapis.com/auth/cloud-platform"

_verrou = threading.Lock()
_info_compte: Optional[dict] = None


def _lire_info_compte() -> dict:
    """
    Charge la cle du compte de service, Key Vault d'abord.

    Raises:
        RuntimeError: si aucune source n'est disponible. Une identite Google
            absente doit etre une erreur nommee, pas un depot silencieusement
            ignore.
    """
    global _info_compte
    with _verrou:
        if _info_compte is not None:
            return _info_compte
        chemin = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
        if chemin and os.path.exists(chemin):
            with open(chemin, encoding="utf-8") as flux:
                _info_compte = json.load(flux)
            logger.info("[INFO] Compte de service Google lu dans %s.", chemin)
            return _info_compte
        from azure.keyvault.secrets import SecretClient
        from src.azure_auth import obtenir_credential
        credential = obtenir_credential(interactif=False)
        if credential is None:
            raise RuntimeError("Identite Azure indisponible pour lire le compte Google.")
        kv = SecretClient(vault_url=Config.KEY_VAULT_URL, credential=credential)
        _info_compte = json.loads(kv.get_secret(Config.GCP_SECRET_SA).value)
        logger.info("[SUCCES] Compte de service Google %s charge depuis le Key Vault.",
                    _info_compte.get("client_email", "?"))
        return _info_compte


def credentials_google(portees: list[str]) -> object:
    """Rend des identifiants google-auth pour les portees demandees."""
    from google.oauth2 import service_account
    return service_account.Credentials.from_service_account_info(
        _lire_info_compte(), scopes=portees)


def oublier() -> None:
    """Efface la cle memorisee (tests, rotation de la cle)."""
    global _info_compte
    with _verrou:
        _info_compte = None
