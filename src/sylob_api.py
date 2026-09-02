"""
[ARCHITECTURE] Interfaçage ERP Sylob (fiche_de_controle)

Stratégie :
- Credentials depuis Azure Key Vault (DefaultAzureCredential), fallback .env
- health-check au démarrage pour le status board
- Retry automatique sur 401 (session expirée) avec re-fetch des credentials KV
"""

import os
import sys
import base64
import json
import logging
import requests
import urllib3
import xml.etree.ElementTree as ET
from typing import Optional

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logger = logging.getLogger(__name__)


def get_base_path() -> str:
    """Retourne le chemin d'exécution réel (script ou .exe PyInstaller)."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


class SylobAPI:
    """Client REST de l'ERP Sylob (endpoint RECEPTIONAPI, réponse XML)."""

    # Source de verite unique des credentials Sylob applicatifs : un secret
    # unique dans kv-dtpf-prod, partage avec MyReport et tout futur connecteur.
    # Un nom de secret Key Vault n accepte pas d underscore, d ou les tirets.
    _VAULT_URL = "https://kv-dtpf-prod.vault.azure.net/"
    _SECRET_CLIENT = "tb-sylob-client"
    # Repli sur l ancien emplacement, un secret par variable, le temps que tous
    # les postes soient passes sur le secret unique.
    _VAULT_URL_LEGACY = "https://kv-tb-ia-agents-secrets.vault.azure.net/"
    _SECRET_NAMES = ("SYLOB-USER", "SYLOB-PASS", "SYLOB-UNITE-PERS",
                     "SYLOB-SESSION-ID", "SYLOB-BASE-URL1")
    _CHAMPS = ("user", "password", "unite_pers", "session_id", "base_url1")

    def __init__(self) -> None:
        self.user: str = ""
        self.password: str = ""
        self.unite_pers: str = ""
        self.session_id: str = ""
        self.base_url1: str = ""
        self.headers: dict = {}
        self.source_credentials: str = ""
        self._load_credentials()

    # ------------------------------------------------------------------
    # Credentials
    # ------------------------------------------------------------------

    def _load_credentials(self) -> None:
        """
        Charge les credentials dans l ordre : secret unique Key Vault, ancien
        Key Vault par variable, puis .env local.

        Junior Tip : le .env etait copie en clair sur le partage reseau a chaque
        deploiement. Il ne reste ici qu en dernier recours, pour ne pas bloquer
        un poste dont l authentification Azure serait tombee.
        """
        if self._load_from_keyvault():
            self.source_credentials = "Key Vault (tb-sylob-client)"
        elif self._load_from_keyvault_legacy():
            self.source_credentials = "Key Vault (secrets unitaires)"
            logger.warning("[ATTENTION] Credentials lus dans l ancien Key Vault. "
                           "Migrer vers %s.", self._SECRET_CLIENT)
        else:
            self._load_from_env()
            self.source_credentials = ".env local"
            logger.warning("[ATTENTION] Credentials lus dans le .env local. "
                           "Ce fichier ne doit pas rester sur un partage reseau.")
        self.headers = self._build_headers()

    def _load_from_keyvault(self) -> bool:
        """
        Lit le secret unique tb-sylob-client (charge utile JSON) dans kv-dtpf-prod.

        Returns:
            True si les cinq champs attendus sont presents, False sinon.
        """
        try:
            from azure.identity import DefaultAzureCredential
            from azure.keyvault.secrets import SecretClient
            kv = SecretClient(vault_url=self._VAULT_URL,
                              credential=DefaultAzureCredential())
            charge = json.loads(kv.get_secret(self._SECRET_CLIENT).value)
        except ImportError as e:
            logger.error("[ECHEC] Packages Azure absents (%s). Installer "
                         "azure-identity et azure-keyvault-secrets.", e)
            return False
        except Exception as e:
            logger.warning("[ATTENTION] Secret %s illisible : %s",
                           self._SECRET_CLIENT, e)
            return False
        manquants = [c for c in self._CHAMPS if not charge.get(c)]
        if manquants:
            logger.error("[ECHEC] Secret %s incomplet, champs manquants : %s",
                         self._SECRET_CLIENT, ", ".join(manquants))
            return False
        for champ in self._CHAMPS:
            setattr(self, champ, charge[champ])
        logger.info("[SUCCES] Credentials Sylob charges depuis %s.",
                    self._SECRET_CLIENT)
        return True

    def _load_from_keyvault_legacy(self) -> bool:
        """Repli : ancien Key Vault, un secret par variable."""
        try:
            from azure.identity import DefaultAzureCredential
            from azure.keyvault.secrets import SecretClient
            kv = SecretClient(vault_url=self._VAULT_URL_LEGACY,
                              credential=DefaultAzureCredential())
            valeurs = [kv.get_secret(nom).value for nom in self._SECRET_NAMES]
        except Exception as e:
            logger.warning("[ATTENTION] Ancien Key Vault indisponible : %s", e)
            return False
        if not all(valeurs):
            return False
        for champ, valeur in zip(self._CHAMPS, valeurs):
            setattr(self, champ, valeur)
        return True

    def _load_from_env(self) -> None:
        """Charge les credentials depuis le fichier .env local."""
        try:
            from dotenv import load_dotenv
            load_dotenv(os.path.join(get_base_path(), '.env'))
        except Exception:
            pass
        self.user = os.getenv("SYLOB_USER", "")
        self.password = os.getenv("SYLOB_PASS", "")
        self.unite_pers = os.getenv("SYLOB_UNITE_PERS", "")
        self.session_id = os.getenv("SYLOB_SESSION_ID", "")
        self.base_url1 = os.getenv("SYLOB_BASE_URL1", "")

    def _build_headers(self) -> dict:
        """Construit le header Basic Auth Base64 requis par Sylob."""
        login = f"{self.user}@@{self.unite_pers}@@{self.session_id}"
        token = base64.b64encode(f"{login}:{self.password}".encode()).decode("ascii")
        return {"Authorization": f"Basic {token}"}

    def _refresh_credentials(self) -> None:
        """Re-fetch credentials depuis Key Vault et reconstruit les headers (retry 401)."""
        logger.warning("[ATTENTION] Session Sylob expiree (401), refresh...")
        if self._load_from_keyvault() or self._load_from_keyvault_legacy():
            self.headers = self._build_headers()
            logger.info("[Sylob] Credentials rafraîchis depuis Key Vault.")
        else:
            logger.error("[Sylob] Refresh impossible — Key Vault inaccessible.")

    # ------------------------------------------------------------------
    # Health-check
    # ------------------------------------------------------------------

    def is_healthy(self) -> bool:
        """
        Vérifie que l'API Sylob répond (requête test avec paramètres génériques).
        Utilisé au démarrage pour afficher le status board.

        Returns:
            True si Sylob répond avec un XML valide, False sinon.
        """
        if not self.base_url1:
            return False
        try:
            response = requests.get(
                self.base_url1,
                params={"limite": "1", "CMD": "%", "ART": "%", "LOT": "%", "EAN": "%"},
                headers=self.headers,
                verify=False,
                timeout=5,
            )
            if response.status_code == 401:
                self._refresh_credentials()
                response = requests.get(
                    self.base_url1,
                    params={"limite": "1", "CMD": "%", "ART": "%", "LOT": "%", "EAN": "%"},
                    headers=self.headers,
                    verify=False,
                    timeout=5,
                )
            ET.fromstring(response.text)
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Recherche lot/PO
    # ------------------------------------------------------------------

    def chercher_lot_par_po(
        self,
        po: str = "",
        art: str = "",
        lot: str = "",
        ean: str = "",
    ) -> Optional[dict]:
        """
        Interroge l'API Sylob pour valider un lot et une commande.
        Retry automatique sur 401 (session expirée).

        Args:
            po:  Numéro de Purchase Order.
            art: Référence interne article.
            lot: Numéro de Batch/Lot fournisseur.
            ean: Code EAN.

        Returns:
            Dict {"po": ..., "lot": ...} ou None si absence de résultat / erreur.
        """
        if not self.base_url1:
            logger.error("[Sylob] URL RECEPTIONAPI non configurée.")
            return None

        params = {
            "limite": "1",
            "CMD": po or "%",
            "ART": art or "%",
            "LOT": lot or "%",
            "EAN": ean or "%",
        }

        result = self._call_api(params)
        if result == "401":
            self._refresh_credentials()
            result = self._call_api(params)
            if result == "401":
                logger.error("[Sylob] 401 persistant après refresh — session inutilisable.")
                return None

        return result if isinstance(result, dict) else None

    def _call_api(self, params: dict) -> Optional[dict | str]:
        """
        Effectue l'appel HTTP vers Sylob et parse le XML.

        Returns:
            Dict {"po", "lot"}, None si pas de résultat, "401" sur session expirée.
        """
        try:
            logger.info(f"[API] Sylob → {params}")
            response = requests.get(
                self.base_url1,
                params=params,
                headers=self.headers,
                verify=False,
                timeout=5,
            )
            if response.status_code == 401:
                return "401"
            response.raise_for_status()

            root = ET.fromstring(response.text)
            ligne = root.find(".//ligneResultatWS")
            if ligne is None:
                logger.info("[Sylob] Aucune commande/lot ouvert trouvé.")
                return None

            valeurs = ligne.findall("valeur")
            result: dict = {}
            if valeurs:
                result['po'] = (valeurs[0].text or "").strip()
            if len(valeurs) > 5:
                result['lot'] = (valeurs[5].text or "").strip()

            return result if result else None

        except requests.exceptions.Timeout:
            logger.warning("[Sylob] Timeout — fallback données PDF/CSV.")
            return None
        except requests.exceptions.RequestException as e:
            logger.warning(f"[Sylob] Erreur réseau : {e}")
            return None
        except ET.ParseError as e:
            logger.warning(f"[Sylob] XML invalide : {e}")
            return None
