"""
[IA] Lecture des Packing Lists par Gemini, en dernier recours.

Strategie :
- Appele UNIQUEMENT quand le texte natif et l'OCR local n'ont produit aucun
  article. Mesure du 09/10/2026 sur les 5 Packing Lists scannees des archives :
  tesseract 0 sur 5, RapidOCR 1 sur 5. L'OCR lit bien du texte, ce sont les
  regex par format fournisseur qui ne reconnaissent pas ces mises en page.
  Gemini recoit le PDF lui-meme et rend des LIGNES structurees, ce qui
  contourne le probleme des formats plutot que d'empiler une regex de plus.
- Le modele n'a jamais le dernier mot (meme regle qu'Apave-Corim) : ce qu'il
  lit n'est qu'un indice. Le PO sert seulement a departager les commandes du
  DWH, le lot fournisseur est affiche a l'operateur, et l'article vient
  toujours du code scanne resolu dans le referentiel.
- Projet GCP dedie (Config.GEMINI_PROJET) : le cout se lit par projet. Chaque
  appel porte en plus le label app=fiche-controle.
- Resultat mis en cache par empreinte du PDF : la reindexation du dossier ne
  refacture pas une Packing List deja lue.

Junior Tip : temperature 0 et schema de reponse impose. Une lecture qui varie
d'un appel a l'autre produirait des indices non reproductibles, donc
impossibles a verifier en recette.
"""

import hashlib
import json
import logging
import os
from typing import Optional

from pydantic import BaseModel, Field

from src.config import Config

logger = logging.getLogger(__name__)

_TAILLE_MAX = 18 * 1024 * 1024  # envoi en ligne limite a ~20 Mo par Vertex AI

CONSIGNE = (
    "Tu lis une packing list fournisseur (souvent chinoise) envoyee a TB "
    "(Tarrerias-Bonjean). Releve chaque ligne d'article. Pour chaque ligne : "
    "code_article = le code article TB (6 a 8 chiffres, souvent colonne ITEM, "
    "ITEM NO, ART. ou REF), ean = code EAN13 ou EAN14 s'il est imprime, po = "
    "numero de commande TB (8 chiffres commencant souvent par 00) s'il est "
    "porte par la ligne, lot = numero de lot ou batch du fournisseur, quantite "
    "= quantite totale de pieces. En plus : fournisseur = nom de l'expediteur "
    "(jamais Tarrerias-Bonjean, qui est le destinataire), po_entete = numeros "
    "de commande TB lus dans l'en-tete. Ne devine rien : laisse vide ce qui "
    "n'est pas imprime. Recopie les chiffres exactement."
)


class LigneLue(BaseModel):
    code_article: str = Field(default="")
    ean: str = Field(default="")
    po: str = Field(default="")
    lot: str = Field(default="")
    quantite: Optional[float] = None


class LecturePackingList(BaseModel):
    fournisseur: str = Field(default="")
    po_entete: list[str] = Field(default_factory=list)
    lignes: list[LigneLue] = Field(default_factory=list)


class LecteurGemini:
    """Client Vertex AI Gemini, cree a la premiere lecture."""

    def __init__(self, dossier_cache: str) -> None:
        self.actif: bool = Config.GEMINI_ACTIF and bool(Config.GEMINI_PROJET)
        self.dossier_cache = dossier_cache
        self._client = None

    def _client_genai(self) -> object:
        if self._client is None:
            from google import genai
            from src.gcp_auth import PORTEE_CLOUD, credentials_google
            self._client = genai.Client(
                vertexai=True, project=Config.GEMINI_PROJET,
                location=Config.GEMINI_LOCATION,
                credentials=credentials_google([PORTEE_CLOUD]))
        return self._client

    def lire(self, chemin_pdf: str) -> Optional[LecturePackingList]:
        """
        Lit une Packing List. Rend None si Gemini est inactif ou echoue : un
        echec ici ne doit jamais bloquer le scan, la fiche se remplit alors
        depuis Sylob et le DWH seuls.
        """
        if not self.actif:
            return None
        with open(chemin_pdf, "rb") as flux:
            contenu = flux.read()
        if len(contenu) > _TAILLE_MAX:
            logger.warning("[ATTENTION] %s trop volumineux pour Gemini.", os.path.basename(chemin_pdf))
            return None
        cle = hashlib.sha1(contenu).hexdigest()
        en_cache = self._lire_cache(cle)
        if en_cache is not None:
            return en_cache
        try:
            lecture = self._appeler(contenu)
        except Exception as e:
            logger.error("[ECHEC] Gemini sur %s : %s", os.path.basename(chemin_pdf), e)
            return None
        self._ecrire_cache(cle, lecture)
        logger.info("[SUCCES] Gemini a lu %d ligne(s) dans %s.", len(lecture.lignes),
                    os.path.basename(chemin_pdf))
        return lecture

    def _appeler(self, contenu: bytes) -> LecturePackingList:
        from google.genai import types
        reponse = self._client_genai().models.generate_content(
            model=Config.GEMINI_MODELE,
            contents=[types.Part.from_bytes(data=contenu, mime_type="application/pdf"),
                      CONSIGNE],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=LecturePackingList,
                temperature=0.0,
                labels={"app": "fiche-controle"}))
        return LecturePackingList.model_validate_json(reponse.text)

    def _fichier_cache(self, cle: str) -> str:
        return os.path.join(self.dossier_cache, "gemini_%s.json" % cle)

    def _lire_cache(self, cle: str) -> Optional[LecturePackingList]:
        try:
            with open(self._fichier_cache(cle), encoding="utf-8") as flux:
                return LecturePackingList.model_validate(json.load(flux))
        except FileNotFoundError:
            return None
        except Exception as e:
            logger.warning("[ATTENTION] Cache Gemini illisible : %s", e)
            return None

    def _ecrire_cache(self, cle: str, lecture: LecturePackingList) -> None:
        try:
            os.makedirs(self.dossier_cache, exist_ok=True)
            with open(self._fichier_cache(cle), "w", encoding="utf-8") as flux:
                json.dump(lecture.model_dump(), flux)
        except OSError as e:
            logger.warning("[ATTENTION] Ecriture du cache Gemini impossible : %s", e)


def vers_resultats(lecture: LecturePackingList) -> dict[str, list[dict]]:
    """
    Convertit une lecture Gemini au format de PDFExtractor (code -> infos).

    Un PO d'en-tete n'est applique a une ligne que s'il est UNIQUE ; sinon la
    ligne est marquee ambigue, comme le fait le parsing regex.
    """
    resultats: dict[str, list[dict]] = {}
    entete = [p for p in lecture.po_entete if p]
    for ligne in lecture.lignes:
        code = "".join(c for c in ligne.code_article if c.isdigit()) or \
               "".join(c for c in ligne.ean if c.isdigit())
        if len(code) < 6:
            continue
        info = {"po": ligne.po, "lot": ligne.lot, "fournisseur": lecture.fournisseur,
                "source": "Gemini"}
        if not ligne.po and len(entete) == 1:
            info["po"] = entete[0]
        elif not ligne.po and len(entete) > 1:
            info.update({"po_ambigu": True, "po_candidats": entete})
        resultats.setdefault(code, [])
        if info not in resultats[code]:
            resultats[code].append(info)
    return resultats
