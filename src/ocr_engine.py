"""
[OCR] Extraction de texte des Packing Lists, y compris les PDF scannes.

Strategie :
- Le texte natif du PDF est essaye en premier (pypdf), car il est instantane
  et exact quand il existe.
- Les fournisseurs qui envoient un scan produisent un PDF sans aucun texte
  (mesure sur les archives : 5 Packing Lists sur 19). Pour ceux-la, bascule sur
  un OCR local, avec le francais, l anglais ET le chinois simplifie, la plupart
  des fournisseurs etant chinois.
- Deux moteurs OCR, essayes dans cet ordre (schema valide le 09/10/2026) :
    1. RapidOCR (modeles PaddleOCR via onnxruntime, rendu des pages par
       pypdfium2) : installe par pip seul, sans binaire systeme, donc
       utilisable sur la Web App Azure ; meilleur que tesseract sur le chinois
       et les tableaux denses ;
    2. tesseract + pdf2image, livre dans tools/ avec l'executable du poste.
  Si aucun ne produit un texte exploitable, PDFExtractor passe la main a
  Gemini (src/lecteur_gemini.py), et chaque valeur lue reste confrontee a
  Sylob et au DWH avant d'atteindre la fiche.
  Azure Document Intelligence est abandonne : il exigeait un Key Vault, un
  reseau sortant et des packages Azure que l executable livre n embarquait pas,
  et il n a donc jamais tourne en production.
- Les binaires sont cherches d abord dans `tools/` a cote de l executable
  (livraison portable dans le zip), puis dans le PATH du poste.
- Resultat mis en cache par empreinte de fichier : un scan n est OCRise qu une
  fois, alors que l application reindexe le dossier a chaque demarrage.

Junior Tip : l OCR coute plusieurs secondes par page. Sans le cache, ouvrir
l application dix fois dans la journee relancait dix fois le meme calcul sur
les memes Packing Lists.
"""

import hashlib
import json
import logging
import os
import sys
from typing import Optional

logger = logging.getLogger(__name__)

LANGUES_DEFAUT = "eng+fra+chi_sim"
_SEUIL_TEXTE_UTILE = 30  # en dessous, le PDF est considere comme un scan
_DPI_OCR = 300


def get_base_path() -> str:
    """Retourne le chemin d execution reel (script Python ou .exe PyInstaller)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _dossier_outils() -> str:
    """Dossier des binaires portables livres avec l application."""
    return os.path.join(get_base_path(), "tools")


def _chemin_tesseract() -> Optional[str]:
    """Localise tesseract.exe : livraison portable, puis PATH du poste."""
    portable = os.path.join(_dossier_outils(), "tesseract", "tesseract.exe")
    if os.path.exists(portable):
        return portable
    import shutil
    return shutil.which("tesseract")


def _chemin_poppler() -> Optional[str]:
    """Localise le dossier bin de poppler, requis par pdf2image."""
    portable = os.path.join(_dossier_outils(), "poppler", "bin")
    if os.path.isdir(portable):
        return portable
    import shutil
    pdftoppm = shutil.which("pdftoppm")
    return os.path.dirname(pdftoppm) if pdftoppm else None


class OCREngine:
    """Extracteur de texte avec repli OCR local et cache par fichier."""

    def __init__(self, langues: str = LANGUES_DEFAUT) -> None:
        from src.config import Config
        self.langues: str = langues
        self.dossier_cache: str = os.path.join(get_base_path(), ".cache", "ocr")
        self.tesseract: Optional[str] = _chemin_tesseract()
        self.poppler: Optional[str] = _chemin_poppler()
        self.moteurs: list[str] = []
        if Config.OCR_ACTIVE and _rapidocr_installe():
            self.moteurs.append("RapidOCR")
        if Config.OCR_ACTIVE and self.tesseract and self.poppler:
            self.moteurs.append("Tesseract")
        self.disponible: bool = bool(self.moteurs)
        if self.disponible:
            logger.info("[SUCCES] OCR local disponible : %s.", ", ".join(self.moteurs))
        else:
            logger.warning("[ATTENTION] Aucun OCR local (OCR_ACTIVE=%s, RapidOCR=%s, "
                           "tesseract=%s, poppler=%s). Les Packing Lists scannees "
                           "dependront de Gemini.", Config.OCR_ACTIVE, _rapidocr_installe(),
                           bool(self.tesseract), bool(self.poppler))

    # ------------------------------------------------------------------
    # Interface publique
    # ------------------------------------------------------------------

    def extraire_texte(self, chemin_pdf: str) -> tuple[str, str]:
        """
        Extrait le texte d une Packing List.

        Args:
            chemin_pdf: Chemin du PDF a lire.

        Returns:
            Tuple (texte, moteur) ou moteur vaut PyPDF, RapidOCR, Tesseract,
            CACHE ou VIDE.
        """
        texte = self._texte_natif(chemin_pdf)
        if len(texte) >= _SEUIL_TEXTE_UTILE:
            return texte, "PyPDF"

        cache = self._lire_cache(chemin_pdf)
        if cache is not None:
            return cache, "CACHE"

        for moteur in self.moteurs:
            texte = self._rapidocr(chemin_pdf) if moteur == "RapidOCR" else self._ocr(chemin_pdf)
            if len(texte) >= _SEUIL_TEXTE_UTILE:
                self._ecrire_cache(chemin_pdf, texte)
                return texte, moteur
            logger.warning("[ATTENTION] %s : %s n'a rien produit d'exploitable.",
                           os.path.basename(chemin_pdf), moteur)
        if not self.moteurs:
            logger.error("[ECHEC] %s : PDF scanne et aucun OCR local.",
                         os.path.basename(chemin_pdf))
        return "", "VIDE"


    # ------------------------------------------------------------------
    # Moteurs
    # ------------------------------------------------------------------

    def _texte_natif(self, chemin_pdf: str) -> str:
        """Lit le texte embarque dans le PDF, sans OCR."""
        try:
            from pypdf import PdfReader
            reader = PdfReader(chemin_pdf)
            return "\n".join(p.extract_text() or "" for p in reader.pages).strip()
        except Exception as e:
            logger.warning("[ATTENTION] Lecture native impossible (%s) : %s",
                           os.path.basename(chemin_pdf), e)
            return ""

    def _rapidocr(self, chemin_pdf: str) -> str:
        """
        OCR par RapidOCR, page par page, en reconstituant les lignes.

        Junior Tip : RapidOCR rend des boites de texte, pas des lignes. Les
        regex fournisseur de PDFExtractor travaillent ligne par ligne : on
        regroupe donc les boites dont le centre vertical est proche, puis on les
        ordonne de gauche a droite.
        """
        try:
            import numpy
            import pypdfium2
            moteur = _moteur_rapidocr()
            document = pypdfium2.PdfDocument(chemin_pdf)
        except Exception as e:
            logger.error("[ECHEC] RapidOCR indisponible pour %s : %s",
                         os.path.basename(chemin_pdf), e)
            return ""
        pages: list[str] = []
        for numero in range(len(document)):
            try:
                image = document[numero].render(scale=_DPI_OCR / 72).to_pil().convert("RGB")
                boites, _ = moteur(numpy.array(image))
                pages.append(_lignes_depuis_boites(boites or []))
            except Exception as e:
                logger.error("[ECHEC] RapidOCR page %d de %s : %s", numero + 1,
                             os.path.basename(chemin_pdf), e)
        texte = "\n".join(pages).strip()
        logger.info("[SUCCES] RapidOCR de %s : %d page(s), %d caracteres.",
                    os.path.basename(chemin_pdf), len(document), len(texte))
        return texte

    def _ocr(self, chemin_pdf: str) -> str:
        """Convertit chaque page en image puis la soumet a tesseract."""
        try:
            import pytesseract
            from pdf2image import convert_from_path
        except ImportError as e:
            logger.error("[ECHEC] Packages OCR absents (%s). Installer "
                         "pytesseract et pdf2image.", e)
            return ""
        pytesseract.pytesseract.tesseract_cmd = self.tesseract
        try:
            images = convert_from_path(chemin_pdf, dpi=_DPI_OCR,
                                       poppler_path=self.poppler)
        except Exception as e:
            logger.error("[ECHEC] Conversion en images de %s : %s",
                         os.path.basename(chemin_pdf), e)
            return ""
        pages: list[str] = []
        for numero, image in enumerate(images, start=1):
            try:
                pages.append(pytesseract.image_to_string(image, lang=self.langues))
            except Exception as e:
                logger.error("[ECHEC] OCR page %d de %s : %s", numero,
                             os.path.basename(chemin_pdf), e)
        texte = "\n".join(pages).strip()
        logger.info("[SUCCES] OCR de %s : %d page(s), %d caracteres.",
                    os.path.basename(chemin_pdf), len(images), len(texte))
        return texte

    # ------------------------------------------------------------------
    # Cache
    # ------------------------------------------------------------------

    def _empreinte(self, chemin_pdf: str) -> str:
        """Empreinte du contenu du fichier, cle du cache."""
        digest = hashlib.sha1()
        with open(chemin_pdf, "rb") as flux:
            for bloc in iter(lambda: flux.read(1 << 16), b""):
                digest.update(bloc)
        return digest.hexdigest()

    def _fichier_cache(self, chemin_pdf: str) -> str:
        """Chemin du fichier de cache associe a un PDF."""
        return os.path.join(self.dossier_cache, "%s.json" % self._empreinte(chemin_pdf))

    def _lire_cache(self, chemin_pdf: str) -> Optional[str]:
        """Relit un texte deja OCRise, None si absent ou illisible."""
        try:
            chemin = self._fichier_cache(chemin_pdf)
            if not os.path.exists(chemin):
                return None
            with open(chemin, encoding="utf-8") as flux:
                return json.load(flux).get("texte")
        except Exception as e:
            logger.warning("[ATTENTION] Cache OCR illisible : %s", e)
            return None

    def _ecrire_cache(self, chemin_pdf: str, texte: str) -> None:
        """Enregistre un texte OCRise pour les demarrages suivants."""
        try:
            os.makedirs(self.dossier_cache, exist_ok=True)
            with open(self._fichier_cache(chemin_pdf), "w", encoding="utf-8") as flux:
                json.dump({"fichier": os.path.basename(chemin_pdf),
                           "langues": self.langues, "texte": texte}, flux)
        except Exception as e:
            logger.warning("[ATTENTION] Ecriture du cache OCR impossible : %s", e)


# ----------------------------------------------------------------------
# RapidOCR : moteur partage et reconstitution des lignes
# ----------------------------------------------------------------------

_moteur_partage = None


def _rapidocr_installe() -> bool:
    """Vrai si RapidOCR et le moteur de rendu PDF sont importables."""
    import importlib.util
    return all(importlib.util.find_spec(m) is not None
               for m in ("rapidocr_onnxruntime", "pypdfium2"))


def _moteur_rapidocr() -> object:
    """Charge les modeles une seule fois par processus (quelques secondes)."""
    global _moteur_partage
    if _moteur_partage is None:
        from rapidocr_onnxruntime import RapidOCR
        _moteur_partage = RapidOCR()
    return _moteur_partage


def _lignes_depuis_boites(boites: list) -> str:
    """
    Regroupe les boites RapidOCR [coins, texte, score] en lignes de texte.

    Deux boites sont sur la meme ligne si l'ecart de leur centre vertical est
    inferieur a la moitie de la hauteur de la ligne en cours.
    """
    elements = []
    for coins, texte, _score in boites:
        ys = [point[1] for point in coins]
        elements.append({"x": min(point[0] for point in coins),
                         "y": sum(ys) / len(ys), "h": max(ys) - min(ys), "t": texte})
    elements.sort(key=lambda e: e["y"])
    lignes: list[list[dict]] = []
    for element in elements:
        if lignes and abs(element["y"] - lignes[-1][0]["y"]) < max(lignes[-1][0]["h"], 1) / 2:
            lignes[-1].append(element)
        else:
            lignes.append([element])
    return "\n".join(" ".join(e["t"] for e in sorted(ligne, key=lambda e: e["x"]))
                     for ligne in lignes)
