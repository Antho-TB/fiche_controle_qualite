"""
[OCR] Extraction de texte des Packing Lists, y compris les PDF scannes.

Strategie :
- Le texte natif du PDF est essaye en premier (pypdf), car il est instantane
  et exact quand il existe.
- Les fournisseurs qui envoient un scan produisent un PDF sans aucun texte
  (mesure sur les archives : 5 Packing Lists sur 19). Pour ceux-la, bascule sur
  un OCR local, avec le francais, l anglais ET le chinois simplifie, la plupart
  des fournisseurs etant chinois.
- Le moteur retenu est pytesseract + pdf2image, deja en production cote FUSEAU
  (`src/scripts/gmail/parse_bl.py`). On reutilise, on ne reconstruit pas.
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
        self.langues: str = langues
        self.dossier_cache: str = os.path.join(get_base_path(), ".cache", "ocr")
        self.tesseract: Optional[str] = _chemin_tesseract()
        self.poppler: Optional[str] = _chemin_poppler()
        self.disponible: bool = bool(self.tesseract and self.poppler)
        if self.disponible:
            logger.info("[SUCCES] OCR local disponible (%s).", self.langues)
        else:
            logger.warning("[ATTENTION] OCR indisponible : tesseract=%s poppler=%s. "
                           "Les Packing Lists scannees resteront inexploitables.",
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
            Tuple (texte, moteur) ou moteur vaut PyPDF, OCR, CACHE ou VIDE.
        """
        texte = self._texte_natif(chemin_pdf)
        if len(texte) >= _SEUIL_TEXTE_UTILE:
            return texte, "PyPDF"

        cache = self._lire_cache(chemin_pdf)
        if cache is not None:
            return cache, "CACHE"

        if not self.disponible:
            logger.error("[ECHEC] %s : PDF scanne et OCR indisponible.",
                         os.path.basename(chemin_pdf))
            return "", "VIDE"

        texte = self._ocr(chemin_pdf)
        if texte:
            self._ecrire_cache(chemin_pdf, texte)
            return texte, "OCR"
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
