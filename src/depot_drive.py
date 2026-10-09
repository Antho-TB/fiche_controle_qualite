"""
[STOCKAGE] Depot des fiches et des Packing Lists sur un Drive partage Google.

Strategie :
- Repli decide le 09/10/2026 en attendant le compte de service AD qui ouvrira
  le partage SRV-FILES-POM. Meme interface que DepotLocal et DepotSMB : le
  service metier ne sait pas ou les fichiers sont ranges.
- Meme arborescence que le partage qualite, sous le dossier Config.DRIVE_DOSSIER_ID :
    <annee>/Contrôle TB/1_Packing_Lists_A_Traiter
    <annee>/Contrôle TB/2_Fiches_Creees
  Les dossiers manquants sont crees, l'annee est calculee.
- API Drive v3 en REST via google-auth (AuthorizedSession) : pas de client
  Google complet a embarquer pour cinq appels.
- `supportsAllDrives` sur chaque appel : sans lui, l'API ne voit pas les
  fichiers d'un Drive partage et repond comme si le dossier etait vide.

Junior Tip : Drive accepte deux fichiers du meme nom dans un dossier. Une
Packing List redeposee remplace donc le contenu existant au lieu d'en creer
une seconde, sinon le parsing la lirait deux fois.
"""

import json
import logging
import uuid
from datetime import date
from typing import Optional

from src.config import Config
from src.depot_fichiers import DOSSIER_FICHES, DOSSIER_PL, nom_sur

logger = logging.getLogger(__name__)

_API = "https://www.googleapis.com/drive/v3/files"
_API_UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"
_TYPE_DOSSIER = "application/vnd.google-apps.folder"
_COMMUNS = {"supportsAllDrives": "true"}


def _echapper(nom: str) -> str:
    """Echappe un nom pour une requete de recherche Drive."""
    return nom.replace("\\", "\\\\").replace("'", "\\'")


def _multipart_related(metadonnees: dict, contenu: bytes,
                       type_mime: str) -> tuple[bytes, dict]:
    """
    Corps multipart/related exige par l'upload Drive (metadonnees puis contenu).

    Junior Tip : `requests(files=...)` produit du multipart/form-data, que
    l'API Drive ne garantit pas d'accepter pour un upload multipart.
    """
    frontiere = "fichectrl_%s" % uuid.uuid4().hex
    fin_ligne = chr(13) + chr(10)  # CRLF, impose par la RFC 2046
    entete_meta = "--%s%sContent-Type: application/json; charset=UTF-8%s%s" % (
        frontiere, fin_ligne, fin_ligne, fin_ligne)
    entete_fichier = "%s--%s%sContent-Type: %s%s%s" % (
        fin_ligne, frontiere, fin_ligne, type_mime, fin_ligne, fin_ligne)
    cloture = "%s--%s--%s" % (fin_ligne, frontiere, fin_ligne)
    corps = b"".join([entete_meta.encode(), json.dumps(metadonnees).encode("utf-8"),
                      entete_fichier.encode(), contenu, cloture.encode()])
    return corps, {"Content-Type": "multipart/related; boundary=%s" % frontiere}


class DepotDrive:
    """Depot sur un dossier d'un Drive partage, via un compte de service."""

    def __init__(self, session: Optional[object] = None,
                 racine: Optional[str] = None, annee: Optional[int] = None) -> None:
        self.racine: str = racine or Config.DRIVE_DOSSIER_ID
        if not self.racine:
            raise RuntimeError("STOCKAGE=drive mais DRIVE_DOSSIER_ID est vide.")
        self.annee: int = annee or date.today().year
        self.description = "Drive partage, %d/%s" % (self.annee, Config.SOUS_DOSSIER)
        self._session = session
        self._ids: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Acces bas niveau
    # ------------------------------------------------------------------

    def _http(self) -> object:
        if self._session is None:
            from google.auth.transport.requests import AuthorizedSession
            from src.gcp_auth import PORTEE_DRIVE, credentials_google
            self._session = AuthorizedSession(credentials_google([PORTEE_DRIVE]))
        return self._session

    def _chercher(self, nom: str, parent: str, dossier: bool) -> Optional[dict]:
        type_filtre = "=" if dossier else "!="
        requete = ("name = '%s' and '%s' in parents and trashed = false and "
                   "mimeType %s '%s'" % (_echapper(nom), parent, type_filtre, _TYPE_DOSSIER))
        reponse = self._http().get(_API, params={
            **_COMMUNS, "q": requete, "includeItemsFromAllDrives": "true",
            "corpora": "allDrives", "fields": "files(id,name,webViewLink)"}, timeout=30)
        reponse.raise_for_status()
        fichiers = reponse.json().get("files", [])
        return fichiers[0] if fichiers else None

    def _dossier(self, sous_dossier: str) -> str:
        """Identifiant du dossier <annee>/<Contrôle TB>/<sous_dossier>, cree au besoin."""
        if sous_dossier in self._ids:
            return self._ids[sous_dossier]
        parent = self.racine
        for nom in (str(self.annee), Config.SOUS_DOSSIER, sous_dossier):
            trouve = self._chercher(nom, parent, dossier=True)
            parent = trouve["id"] if trouve else self._creer_dossier(nom, parent)
        self._ids[sous_dossier] = parent
        return parent

    def _creer_dossier(self, nom: str, parent: str) -> str:
        reponse = self._http().post(_API, params=_COMMUNS, json={
            "name": nom, "mimeType": _TYPE_DOSSIER, "parents": [parent]}, timeout=30)
        reponse.raise_for_status()
        logger.info("[INFO] Dossier Drive cree : %s", nom)
        return reponse.json()["id"]

    # ------------------------------------------------------------------
    # Interface DepotFichiers
    # ------------------------------------------------------------------

    def verifier(self) -> tuple[bool, str]:
        try:
            self._dossier(DOSSIER_FICHES)
            return True, self.description
        except Exception as e:
            logger.error("[ECHEC] Drive partage inaccessible : %s", e)
            return False, "Drive partage inaccessible (%s)" % type(e).__name__

    def lister_packing_lists(self) -> list[str]:
        requete = ("'%s' in parents and trashed = false and mimeType = 'application/pdf'"
                   % self._dossier(DOSSIER_PL))
        reponse = self._http().get(_API, params={
            **_COMMUNS, "q": requete, "includeItemsFromAllDrives": "true",
            "corpora": "allDrives", "pageSize": "200", "fields": "files(name)"}, timeout=30)
        reponse.raise_for_status()
        return sorted(f["name"] for f in reponse.json().get("files", []))

    def lire_packing_list(self, nom: str) -> bytes:
        fichier = self._chercher(nom_sur(nom), self._dossier(DOSSIER_PL), dossier=False)
        if fichier is None:
            raise FileNotFoundError("Packing List absente du Drive : %s" % nom)
        reponse = self._http().get("%s/%s" % (_API, fichier["id"]),
                                   params={**_COMMUNS, "alt": "media"}, timeout=120)
        reponse.raise_for_status()
        return reponse.content

    def deposer_packing_list(self, nom: str, contenu: bytes) -> str:
        return self._televerser(DOSSIER_PL, nom, contenu, "application/pdf")

    def deposer_fiche(self, nom: str, contenu: bytes) -> str:
        return self._televerser(
            DOSSIER_FICHES, nom, contenu,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    def _televerser(self, sous_dossier: str, nom: str, contenu: bytes,
                    type_mime: str) -> str:
        """Cree le fichier, ou remplace son contenu s'il existe deja."""
        nom = nom_sur(nom)
        dossier = self._dossier(sous_dossier)
        existant = self._chercher(nom, dossier, dossier=False)
        metadonnees = {"name": nom} if existant else {"name": nom, "parents": [dossier]}
        corps, entete = _multipart_related(metadonnees, contenu, type_mime)
        params = {**_COMMUNS, "uploadType": "multipart", "fields": "id,webViewLink"}
        if existant:
            reponse = self._http().patch("%s/%s" % (_API_UPLOAD, existant["id"]), params=params,
                                         data=corps, headers=entete, timeout=120)
        else:
            reponse = self._http().post(_API_UPLOAD, params=params, data=corps,
                                        headers=entete, timeout=120)
        reponse.raise_for_status()
        lien = reponse.json().get("webViewLink", "")
        logger.info("[SUCCES] Fichier depose sur le Drive : %s/%s", sous_dossier, nom)
        return lien or "Drive : %d/%s/%s/%s" % (self.annee, Config.SOUS_DOSSIER, sous_dossier, nom)
