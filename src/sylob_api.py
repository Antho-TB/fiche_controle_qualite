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

    _VAULT_URL = "https://kv-tb-ia-agents-secrets.vault.azure.net/"
    _SECRET_NAMES = ("SYLOB-USER", "SYLOB-PASS", "SYLOB-UNITE-PERS",
                     "SYLOB-SESSION-ID", "SYLOB-BASE-URL1")

    def __init__(self) -> None:
        self.user: str = ""
        self.password: str = ""
        self.unite_pers: str = ""
        self.session_id: str = ""
        self.base_url1: str = ""
        self.headers: dict = {}
        self._load_credentials()

    # ------------------------------------------------------------------
    # Credentials
    # ------------------------------------------------------------------

    def _load_credentials(self) -> None:
        """Charge les credentials depuis Key Vault puis fallback .env."""
        if not self._load_from_keyvault():
            self._load_from_env()
        self.headers = self._build_headers()

    def _load_from_keyvault(self) -> bool:
        """
        Tente de récupérer les secrets depuis Azure Key Vault.

        Returns:
            True si tous les secrets ont été chargés, False sinon.
        """
        try:
            from azure.identity import DefaultAzureCredential
            from azure.keyvault.secrets import SecretClient
            kv = SecretClient(vault_url=self._VAULT_URL, credential=DefaultAzureCredential())
            self.user = kv.get_secret("SYLOB-USER").value
            self.password = kv.get_secret("SYLOB-PASS").value
            self.unite_pers = kv.get_secret("SYLOB-UNITE-PERS").value
            self.session_id = kv.get_secret("SYLOB-SESSION-ID").value
            self.base_url1 = kv.get_secret("SYLOB-BASE-URL1").value
            return True
        except Exception as e:
            logger.warning(f"[Sylob] Key Vault indisponible, fallback .env : {e}")
            return False

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
        logger.warning("[Sylob] Session expirée (401) — refresh credentials...")
        if self._load_from_keyvault():
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
