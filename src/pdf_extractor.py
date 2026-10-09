"""
[ARCHITECTURE] I/O OCR & Text Parsing (fiche_de_controle)

Formats PDF fournisseurs identifies sur les archives :
  A - Template TB multicontainer (BILL TO, PO # : X, N deg Lot: X)
  B - PO#XXXXXXXX/MEN#XXXXX XXXXXXXX (Guangwei, JIT Global)
  C - PO NO.: / N deg. LOT: (Yangjiang Yinhong)
  D - Jieyang Wanxin : PO(8)+Lot(5)+Item(8) sans espaces, tableau chinois
  E - JAZZWAY : CUSTOMER P.O. NO. + code 8 chiffres
  F - PDFs scannes (images pures) -> OCR local obligatoire (src/ocr_engine.py)
- ocr_available (bool public) expose l etat du moteur pour le status board

Azure Document Intelligence a ete abandonne : il exigeait Key Vault, un reseau
sortant et des packages Azure que l executable livre n embarquait pas. Il n a
donc jamais tourne en production, et son absence etait avalee silencieusement.
Le moteur est desormais local (pytesseract, langues eng+fra+chi_sim).
"""

import os
import re
import sys
import logging
import shutil
import time
from typing import Optional

from src.ocr_engine import OCREngine

logger = logging.getLogger(__name__)


def get_base_path() -> str:
    """Retourne le chemin d execution reel (script Python ou .exe compile PyInstaller)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class PDFExtractor:
    """Moteur de parsing des Packing Lists (ADI primaire + fallback PyPDF)."""

    _PO_KEYS = frozenset({
        "po", "p.o.", "p.o", "purchase order", "order no", "order number",
        "cmd", "commande", "customer po", "customer p.o.", "no commande",
    })
    _LOT_KEYS = frozenset({
        "lot", "batch", "lot no", "batch no", "n° lot", "no lot",
        "lot number", "batch number", "n°lot",
    })
    # Separateur multi-valeurs dans les templates TB (ideogramme japonais virgule)
    _MULTI_SEP = re.compile(r"[、,]")

    def __init__(self, pdf_dir: Optional[str] = None) -> None:
        self.pdf_dir: str = pdf_dir or os.path.join(get_base_path(), "1_Packing_Lists_A_Traiter")
        self.articles_pdf: dict[str, list[dict]] = {}
        self.rapports: list[dict] = []
        self.ocr_available: bool = False
        self.adi_available: bool = False
        self._ocr: Optional[OCREngine] = None
        self._gemini = None
        self._init_ocr()
        self._load_all_pdfs()

    # ------------------------------------------------------------------
    # Initialisation ADI
    # ------------------------------------------------------------------

    def _init_ocr(self) -> None:
        """Initialise le moteur OCR local et positionne ocr_available."""
        self._ocr = OCREngine()
        self.ocr_available = self._ocr.disponible
        from src.lecteur_gemini import LecteurGemini
        self._gemini = LecteurGemini(self._ocr.dossier_cache)
        # Compatibilite ascendante : le status board historique lisait ce nom.
        self.adi_available = self.ocr_available

    # ------------------------------------------------------------------
    # Chargement dossier
    # ------------------------------------------------------------------

    def _load_all_pdfs(self) -> None:
        """Scan initial du hot folder et indexation en RAM."""
        if not os.path.exists(self.pdf_dir):
            os.makedirs(self.pdf_dir)
            logger.info("[INFO] Dossier cree : %s", self.pdf_dir)
            return
        pdf_files = [f for f in os.listdir(self.pdf_dir) if f.lower().endswith(".pdf")]
        if not pdf_files:
            logger.info("[INFO] Aucun PDF dans %s", self.pdf_dir)
            return
        logger.info("[INFO] Ingestion de %d Packing List(s)...", len(pdf_files))
        for file_name in pdf_files:
            self._extract_from_pdf(os.path.join(self.pdf_dir, file_name))

    # ------------------------------------------------------------------
    # Orchestration ADI -> PyPDF
    # ------------------------------------------------------------------

    def _extract_from_pdf(self, pdf_path: str) -> None:
        """
        Orchestre l extraction d une Packing List et RAPPORTE son resultat.

        Junior Tip : l implementation historique loguait "[SUCCES] Indexation
        terminee" meme quand zero article etait extrait. Une panne totale
        ressemblait donc a un succes dans les logs, et personne ne pouvait la
        voir avant que le service qualite se plaigne. Ici, zero article extrait
        est un ECHEC nomme, trace dans self.rapports et affichable a l ecran.
        """
        nom = os.path.basename(pdf_path)
        try:
            results, source = self._extract_from_text(pdf_path)
            if not results and self._gemini is not None and self._gemini.actif:
                results, source = self._repli_gemini(pdf_path, source)
            for art_code, infos in results.items():
                if art_code not in self.articles_pdf:
                    self.articles_pdf[art_code] = []
                for info in infos:
                    if info not in self.articles_pdf[art_code]:
                        self.articles_pdf[art_code].append(info)
            self._rapporter(nom, source, results)
        except Exception as e:
            logger.error("[ECHEC] Extraction PDF %s : %s", nom, e)
            self.rapports.append({"fichier": nom, "moteur": "-", "statut": "ERREUR",
                                  "n_articles": 0, "detail": str(e)})

    def _repli_gemini(self, pdf_path: str,
                      source: str) -> tuple[dict[str, list[dict]], str]:
        """Dernier recours quand ni le texte natif ni l'OCR n'ont donne d'article."""
        from src.lecteur_gemini import vers_resultats
        logger.info("[INFO] %s : aucun article via %s, lecture par Gemini.",
                    os.path.basename(pdf_path), source)
        lecture = self._gemini.lire(pdf_path)
        if lecture is None:
            return {}, source
        return vers_resultats(lecture), "%s+Gemini" % source

    def _rapporter(self, nom: str, source: str, results: dict) -> None:
        """Consigne le resultat d extraction d une Packing List."""
        n = len(results)
        ambigus = sum(1 for infos in results.values()
                      for i in infos if i.get("po_ambigu"))
        if n == 0:
            logger.error("[ECHEC] %s : aucun article extrait (moteur %s). "
                         "Packing List non exploitable.", nom, source)
            statut, detail = "ECHEC", "Aucun article extrait"
        elif ambigus:
            logger.warning("[ATTENTION] %s : %d article(s) extrait(s), PO "
                           "ambigu (plusieurs commandes dans l en-tete).", nom, n)
            statut, detail = "PARTIEL", "PO ambigu, a confirmer"
        else:
            logger.info("[SUCCES] %s : %d article(s) extrait(s) via %s.",
                        nom, n, source)
            statut, detail = "OK", ""
        self.rapports.append({"fichier": nom, "moteur": source, "statut": statut,
                              "n_articles": n, "detail": detail})

    def resume_ingestion(self) -> dict[str, int]:
        """Compte les Packing Lists par statut, pour le status board."""
        resume = {"OK": 0, "PARTIEL": 0, "ECHEC": 0, "ERREUR": 0}
        for r in self.rapports:
            resume[r["statut"]] = resume.get(r["statut"], 0) + 1
        return resume

    # ------------------------------------------------------------------
    # Extraction du texte puis parsing par format fournisseur
    # ------------------------------------------------------------------

    def _extract_from_text(self, pdf_path: str) -> tuple[dict[str, list[dict]], str]:
        """
        Extrait les articles d une Packing List, quelle que soit sa nature.

        Le texte vient du PDF lui meme quand il en contient, du cache OCR, ou
        d un OCR local pour les scans. Les regex par format fournisseur sont
        ensuite appliquees a l identique.

        Returns:
            Tuple (resultats par code article, nom du moteur utilise).
        """
        results: dict[str, list[dict]] = {}
        text, moteur = self._ocr.extraire_texte(pdf_path)
        if not text.strip():
            return results, moteur

        lines = [line.strip() for line in text.split("\n") if line.strip()]
        fournisseur = self._extract_fournisseur(lines)
        global_po = self._regex_global_po(text)
        global_lot = self._regex_global_lot(text)
        is_format_e = self._detect_format_e(text)

        po_list = self._split_multi_value(global_po, text, r"(?i)PO\s*#\s*:\s*([\d\s\u3001,]+)")
        lot_list = self._split_multi_value(global_lot, text, r"(?i)N\u00b0[\s.]*\s*Lot[\u003a\uff1a\s]\s*([\d\s\u3001,]+)")

        for line in lines:
            art_code, po, lot = self._parse_line_regex(line, global_po, global_lot, is_format_e)
            if not art_code:
                continue
            if len(po_list) > 1:
                # L en-tete porte plusieurs commandes et la ligne article ne dit
                # pas laquelle la concerne. L implementation historique faisait
                # un produit cartesien PO x Lot applique a TOUS les articles :
                # la fiche pouvait porter un PO faux sans que personne le voie.
                # On refuse de deviner et on remonte les candidats.
                info = {"po": "", "lot": "", "fournisseur": fournisseur,
                        "po_ambigu": True, "po_candidats": po_list,
                        "lot_candidats": lot_list}
                results.setdefault(art_code, [])
                if info not in results[art_code]:
                    results[art_code].append(info)
            else:
                info = {"po": po, "lot": lot, "fournisseur": fournisseur}
                results.setdefault(art_code, [])
                if info not in results[art_code]:
                    results[art_code].append(info)
        return results, moteur

    def _extract_fournisseur(self, lines: list[str]) -> str:
        """Extrait le nom du fournisseur depuis les premieres lignes."""
        skip = ("BILL TO", "PACKING LIST", "INVOICE", "TO:", "FROM:",
                "DELIVERY ADRESS", "DELIVERY ADDRESS", "TVA NUMBER", "EORI",
                "TARRERIAS", "TB-GROUPE", "INCOTERM", "HS CODE", "DATE",
                "PORT OF", "MONETARY", "CONSIGNEE", "SHIP VIA")
        for line in lines[:8]:
            majuscule = line.upper()
            if any(kw in majuscule for kw in skip):
                continue
            if len(line) > 3 and not re.match(r"^[\d\s.:/-]+$", line):
                return line[:120]
        logger.warning("[ATTENTION] Fournisseur non identifie dans l en-tete.")
        return ""

    def _split_multi_value(self, default: str, text: str, pattern: str) -> list[str]:
        """
        Extrait et decoupe les valeurs multiples (separateur ideogramme ou virgule).
        Retourne [default] si valeur unique ou pattern non trouve.
        """
        m = re.search(pattern, text)
        if not m:
            return [default] if default else []
        raw = m.group(1)
        parts = [p.strip() for p in self._MULTI_SEP.split(raw) if re.search(r"\d{6,}", p.strip())]
        return parts if len(parts) > 1 else [default] if default else []

    def _regex_global_po(self, text: str) -> str:
        """
        Extrait le premier PO depuis l en-tete.
        Formats : PO # :, PO NO.:, PO#/MEN#, CUSTOMER P.O. NO. (valeur sur ligne suivante).
        """
        patterns = [
            r"(?i)PO\s*#\s*:\s*([\d]+)",
            r"(?i)PO\s+NO\.\s*:\s*([\d]+)",
            r"(?i)CUSTOMER\s+P\.O\.\s+NO\.?\s+([\d]+)",
            r"(?i)PO#\s*([\d]+)/MEN#",
        ]
        for pat in patterns:
            m = re.search(pat, text)
            if m:
                return m.group(1).strip()
        # JAZZWAY : "CUSTOMER P.O. NO." est un header de colonne,
        # le numero PO apparait sur la ligne suivante (8 chiffres seuls)
        if re.search(r"(?i)CUSTOMER\s+P\.O\.\s+NO\.", text):
            lines = text.split("\n")
            for i, line in enumerate(lines):
                if re.search(r"(?i)CUSTOMER\s+P\.O\.\s+NO\.", line):
                    for j in range(i + 1, min(i + 5, len(lines))):
                        m = re.match(r"^(\d{8})\b", lines[j].strip())
                        if m:
                            return m.group(1)
        return ""

    def _regex_global_lot(self, text: str) -> str:
        """
        Extrait le premier Lot depuis l en-tete.
        Formats : N deg Lot:, N deg. LOT:, N deg LOT:, LOT:
        """
        patterns = [
            r"(?i)N\u00b0[\s.]*\s*Lot[\u003a\uff1a\s]\s*([\d]+)",
            r"(?i)LOT\s*:\s*([\d]+)",
        ]
        for pat in patterns:
            m = re.search(pat, text)
            if m:
                return m.group(1).strip()
        return ""

    def _detect_format_e(self, text: str) -> bool:
        """True si document Format E (JAZZWAY - CUSTOMER P.O. NO.)."""
        return bool(re.search(r"(?i)CUSTOMER\s+P\.O\.\s+NO\.", text))

    def _parse_line_regex(
        self, line: str, global_po: str, global_lot: str, is_format_e: bool = False
    ) -> tuple[str, str, str]:
        """
        Applique les formats regex sur une ligne de texte PDF.

        Formats:
          1 - PO:XXXXXXXXXXX (code embaque dans PO)
          B - PO# XXXXXXXX/MEN#XXXXX XXXXXXXX (Guangwei/JIT - article apres MEN#)
          3 - XXXXXXXX XXXXX XXXXXXXX (PO + Lot + Item avec espaces)
          D - PO(8)+Lot(4-6)+Item(7-8) sans espaces (Jieyang Wanxin)
          E - XXXXXXXX DESCRIPTION (JAZZWAY, seulement si is_format_e=True)

        Returns:
            Tuple (art_code, po, lot). art_code vide si aucun match.
        """
        # Format 1
        m = re.search(r"(?i)po:\s*(\d{8})(\d{10})?(\d{6,})", line)
        if m:
            return m.group(3), m.group(1), global_lot

        # Format B avec ITEM# explicite
        m = re.search(r"(?i)PO#\s*(\d+)/MEN#\d+\s+ITEM#\s*(\d{6,})", line)
        if m:
            return m.group(2), m.group(1), global_lot

        # Format B legacy (article directement apres MEN#XXXXX)
        m = re.search(r"(?i)PO#\s*(\d+)/MEN#\d+\s+(\d{6,})", line)
        if m:
            return m.group(2), m.group(1), global_lot

        # Format 3 (PO Lot Item avec espaces) - lot fixe 5 chiffres
        # \d{4,6} greedy causait sur-capture (6 chiffres) sur PDFs Jieyang Wanxin avec espaces PyPDF
        m = re.match(r"^(\d{8})\s+(\d{5})\s+(\d{6,})", line)
        if m:
            return m.group(3), m.group(1), m.group(2)

        # Format D (Jieyang Wanxin - sans espaces : PO8+Lot5+Item8+[qty digit(s)]+texte chinois)
        # Validation : du chinois doit apparaitre quelque part apres le match (pas forcément position 0)
        m = re.match(r"^(\d{8})(\d{5})(\d{7,8})", line)
        if m:
            rest = line[len(m.group(0)):]
            if rest and re.search(r"[一-鿿]", rest):
                return m.group(3), m.group(1), m.group(2)

        # Format E : 8 chiffres + espace + lettre (active si PO connu dans le doc)
        # Couvre : JAZZWAY, JIT Global (10610003 FUSIL...), etc.
        if global_po:
            m = re.match(r"^(\d{8})(?!\d)\s+[A-Za-z]", line)
            if m:
                return m.group(1), global_po, global_lot

        # Format H (JIT Global) : 8 chiffres + espace + 1-3 chiffres + lettre collees
        # Ex: "10320051 88SET OF 8 BLACK" - quantite collee a la description
        if global_po:
            m = re.match(r"^(\d{6,8})(?!\d)\s+\d{1,3}[A-Z]", line)
            if m:
                return m.group(1), global_po, global_lot

        # Format G : code article seul sur sa ligne (ex: "10590014")
        if global_po:
            m = re.match(r"^(\d{6,8})$", line)
            if m:
                return m.group(1), global_po, global_lot

        return "", global_po, global_lot

    # ------------------------------------------------------------------
    # Interface publique
    # ------------------------------------------------------------------

    def chercher_infos_pdf(self, code_article: str, ref_article: str = "") -> list[dict]:
        """
        Recherche en memoire les donnees extraites pour un article.
        Exact match sur code ou ref, puis fuzzy (sous-chaine >= 6 chars).
        """
        if code_article in self.articles_pdf:
            return self.articles_pdf[code_article]
        if ref_article and ref_article in self.articles_pdf:
            return self.articles_pdf[ref_article]
        for k, v in self.articles_pdf.items():
            if len(k) >= 6 and (k in code_article or k in ref_article):
                return v
        return []

    def archiver_pdfs(self) -> None:
        """Deplace les PDF consommes vers archives/ (log rotation)."""
        archive_dir = os.path.join(self.pdf_dir, "archives")
        os.makedirs(archive_dir, exist_ok=True)
        pdf_files = [f for f in os.listdir(self.pdf_dir) if f.lower().endswith(".pdf")]
        if not pdf_files:
            return
        logger.info("[INFO] Archivage de %d PDF...", len(pdf_files))
        for file_name in pdf_files:
            src = os.path.join(self.pdf_dir, file_name)
            dst = os.path.join(archive_dir, file_name)
            if os.path.exists(dst):
                base, ext = os.path.splitext(file_name)
                dst = os.path.join(archive_dir, "%s_%d%s" % (base, int(time.time()), ext))
            try:
                shutil.move(src, dst)
            except Exception as e:
                logger.error("[ERREUR] Archivage %s : %s", file_name, e)
