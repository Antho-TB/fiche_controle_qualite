"""
[STOCKAGE] Lecture des Packing Lists et depot des fiches de controle.

Strategie :
- Une interface, deux implementations : `DepotLocal` (poste, developpement,
  executable historique) et `DepotSMB` (Web App Azure, ecrit sur SRV-FILES-POM
  par le VPN sous le compte de service AD svc-fichectrl).
- Arborescence de la qualite, identique dans les deux cas :
    <racine>/<annee>/Contrôle TB/1_Packing_Lists_A_Traiter
    <racine>/<annee>/Contrôle TB/2_Fiches_Creees
  L'annee est CALCULEE : un chemin fige sur 2026 casserait le 1er janvier.
- Repli decide le 09/10/2026 si le SMB est refuse : un Drive partage Google,
  a brancher derriere cette meme interface.

Junior Tip : un nom de fichier venu du navigateur est une donnee hostile. Sans
nettoyage, "../../x.pdf" ecrirait hors du dossier prevu. `nom_sur()` ne garde
que le dernier segment et des caracteres sans risque.
"""

import logging
import os
import re
from datetime import date
from typing import Optional, Protocol

from src.config import Config

logger = logging.getLogger(__name__)

DOSSIER_PL = "1_Packing_Lists_A_Traiter"
DOSSIER_FICHES = "2_Fiches_Creees"
TAILLE_MAX_PL = 25 * 1024 * 1024  # une Packing List scannee depasse rarement 10 Mo

_CARACTERES_INTERDITS = re.compile(r"[^\w .()\-]", re.UNICODE)


def nom_sur(nom: str) -> str:
    """
    Rend un nom de fichier sans chemin ni caractere dangereux.

    Raises:
        ValueError: si le nom est vide une fois nettoye.
    """
    base = re.split(r"[\\/]", nom or "")[-1].strip()
    base = _CARACTERES_INTERDITS.sub("_", base).lstrip(".")
    if not base:
        raise ValueError("Nom de fichier vide ou invalide.")
    return base[:150]


class DepotFichiers(Protocol):
    """Contrat commun aux depots de fichiers."""

    description: str

    def verifier(self) -> tuple[bool, str]: ...

    def lister_packing_lists(self) -> list[str]: ...

    def lire_packing_list(self, nom: str) -> bytes: ...

    def deposer_packing_list(self, nom: str, contenu: bytes) -> str: ...

    def deposer_fiche(self, nom: str, contenu: bytes) -> str: ...


class DepotLocal:
    """Depot sur un dossier local ou un lecteur deja monte (poste Windows)."""

    def __init__(self, racine: Optional[str] = None) -> None:
        from src.excel_handler import get_base_path
        self.racine: str = racine or Config.DOSSIER_LOCAL or get_base_path()
        self.description = "dossier local %s" % self.racine

    def _dossier(self, sous_dossier: str) -> str:
        chemin = os.path.join(self.racine, sous_dossier)
        os.makedirs(chemin, exist_ok=True)
        return chemin

    def verifier(self) -> tuple[bool, str]:
        try:
            self._dossier(DOSSIER_FICHES)
            return True, self.description
        except OSError as e:
            return False, "%s inaccessible (%s)" % (self.racine, type(e).__name__)

    def lister_packing_lists(self) -> list[str]:
        dossier = self._dossier(DOSSIER_PL)
        return sorted(f for f in os.listdir(dossier) if f.lower().endswith(".pdf"))

    def lire_packing_list(self, nom: str) -> bytes:
        with open(os.path.join(self._dossier(DOSSIER_PL), nom_sur(nom)), "rb") as flux:
            return flux.read()

    def deposer_packing_list(self, nom: str, contenu: bytes) -> str:
        return self._ecrire(DOSSIER_PL, nom, contenu)

    def deposer_fiche(self, nom: str, contenu: bytes) -> str:
        return self._ecrire(DOSSIER_FICHES, nom, contenu)

    def _ecrire(self, sous_dossier: str, nom: str, contenu: bytes) -> str:
        chemin = os.path.join(self._dossier(sous_dossier), nom_sur(nom))
        with open(chemin, "wb") as flux:
            flux.write(contenu)
        logger.info("[SUCCES] Fichier depose : %s", chemin)
        return chemin


class DepotSMB:
    """
    Depot sur le partage qualite de SRV-FILES-POM, joint en SMB par le VPN.

    On vise le serveur reel (cible DFS de A:\\QUALITE) par son IP : le DNS
    interne n'est pas resolu depuis Azure, et un client SMB hors domaine suit
    mal les referrals DFS.
    """

    def __init__(self, identifiants: Optional[tuple[str, str]] = None,
                 annee: Optional[int] = None) -> None:
        self.serveur: str = Config.SMB_SERVEUR
        self.annee: int = annee or date.today().year
        self.base: str = "\\\\%s\\%s\\%s\\%d\\%s" % (
            self.serveur, Config.SMB_PARTAGE,
            Config.SMB_DOSSIER_RACINE.replace("/", "\\"), self.annee,
            Config.SMB_SOUS_DOSSIER)
        self.description = "partage SMB %s" % self.base
        self._identifiants = identifiants
        self._session_ouverte = False

    def _ouvrir_session(self) -> None:
        """Ouvre la session SMB au premier besoin, identifiants lus au Key Vault."""
        if self._session_ouverte:
            return
        import smbclient
        login, mot_de_passe = self._identifiants or _lire_identifiants_smb()
        smbclient.register_session(self.serveur, username=login,
                                   password=mot_de_passe, connection_timeout=10)
        self._session_ouverte = True

    def _dossier(self, sous_dossier: str) -> str:
        import smbclient
        self._ouvrir_session()
        chemin = "%s\\%s" % (self.base, sous_dossier)
        smbclient.makedirs(chemin, exist_ok=True)
        return chemin

    def verifier(self) -> tuple[bool, str]:
        try:
            self._dossier(DOSSIER_FICHES)
            return True, self.description
        except Exception as e:
            logger.error("[ECHEC] Partage qualite inaccessible : %s", e)
            return False, "%s inaccessible (%s)" % (self.base, type(e).__name__)

    def lister_packing_lists(self) -> list[str]:
        import smbclient
        dossier = self._dossier(DOSSIER_PL)
        return sorted(f for f in smbclient.listdir(dossier) if f.lower().endswith(".pdf"))

    def lire_packing_list(self, nom: str) -> bytes:
        import smbclient
        chemin = "%s\\%s" % (self._dossier(DOSSIER_PL), nom_sur(nom))
        with smbclient.open_file(chemin, mode="rb") as flux:
            return flux.read()

    def deposer_packing_list(self, nom: str, contenu: bytes) -> str:
        return self._ecrire(DOSSIER_PL, nom, contenu)

    def deposer_fiche(self, nom: str, contenu: bytes) -> str:
        return self._ecrire(DOSSIER_FICHES, nom, contenu)

    def _ecrire(self, sous_dossier: str, nom: str, contenu: bytes) -> str:
        import smbclient
        chemin = "%s\\%s" % (self._dossier(sous_dossier), nom_sur(nom))
        with smbclient.open_file(chemin, mode="wb") as flux:
            flux.write(contenu)
        logger.info("[SUCCES] Fichier depose : %s", chemin)
        return chemin


def _lire_identifiants_smb() -> tuple[str, str]:
    """
    Lit le compte de service AD au Key Vault.

    Raises:
        RuntimeError: si l'identite Azure ou les secrets manquent. Un depot sans
            identifiants doit echouer bruyamment, pas ecrire ailleurs.
    """
    from azure.keyvault.secrets import SecretClient
    from src.azure_auth import obtenir_credential
    credential = obtenir_credential(interactif=False)
    if credential is None:
        raise RuntimeError("Identite Azure indisponible pour lire le compte SMB.")
    kv = SecretClient(vault_url=Config.KEY_VAULT_URL, credential=credential)
    return (kv.get_secret(Config.SMB_SECRET_LOGIN).value,
            kv.get_secret(Config.SMB_SECRET_PASSWORD).value)


def creer_depot() -> DepotFichiers:
    """Instancie le depot designe par la configuration."""
    if Config.STOCKAGE == "smb":
        if not Config.SMB_SERVEUR:
            raise RuntimeError("STOCKAGE=smb mais SMB_SERVEUR est vide.")
        return DepotSMB()
    return DepotLocal()
