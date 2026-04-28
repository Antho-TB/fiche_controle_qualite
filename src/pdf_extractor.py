"""
[ARCHITECTURE] I/O OCR & Text Parsing (fiche_de_controle)

Rôle global :
Ce module scanne de manière autonome les dossiers contenant des "Packing Lists" (Bons de livraison
fournisseurs en PDF), en extrait le texte via PyPDF, et détecte les numéros de Commande (PO) 
et de Lot (Batch) par le biais d'expressions régulières (Regex).

Stratégie métier (Fuzzy Regex Matching) :
Les fournisseurs mondiaux (Asiatiques, Européens) ont des formats de Packing Lists extrêmement hétérogènes.
Une approche stricte échouerait dans 80% des cas. La stratégie ici est d'utiliser une série de
patterns (formats 1 à 4) pour ratisser large. On croise ensuite ces résultats avec l'API Sylob 
en aval. Ce module sert donc d'extracteur "Best-Effort" pour pré-remplir l'interface opérateur.
"""

import os
import re
import sys
import logging
from pypdf import PdfReader

def get_base_path() -> str:
    """
    Retourne le chemin d'exécution réel (script Python ou .exe compilé).
    Crucial pour s'assurer que l'application trouve toujours ses dossiers cibles
    même déployée via PyInstaller sur les Windows des entrepôts.
    """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


class PDFExtractor:
    """
    Moteur de parsing des Packing Lists au format PDF.
    """
    
    def __init__(self, pdf_dir: str = None):
        if pdf_dir is None:
            self.pdf_dir = os.path.join(get_base_path(), "1_Packing_Lists_A_Traiter")
        else:
            self.pdf_dir = pdf_dir
        self.articles_pdf = {} 
        self._load_all_pdfs()

    def _load_all_pdfs(self) -> None:
        """
        Scan initial du dossier de dépôt.
        
        Stratégie :
        Au lancement de l'application, l'extracteur pré-digère tous les PDF présents 
        dans le "hot folder" et indexe les PO/Lots en RAM. Cela permet de répondre
        instantanément (0 latence) quand l'opérateur scanne un code-barres.
        """
        if not os.path.exists(self.pdf_dir):
            os.makedirs(self.pdf_dir)
            logging.info(f"[INFO] Dossier de dépôt PDF créé : {self.pdf_dir}")
            return

        pdf_files = [f for f in os.listdir(self.pdf_dir) if f.lower().endswith('.pdf')]
        
        if not pdf_files:
            logging.info(f"[INFO] Aucun PDF trouvé dans la file d'attente ({self.pdf_dir})")
            return
            
        logging.info(f"[INFO] Ingestion automatique de {len(pdf_files)} Packing List(s)...")
        
        for file_name in pdf_files:
            pdf_path = os.path.join(self.pdf_dir, file_name)
            self._extract_from_pdf(pdf_path)

    def _extract_from_pdf(self, pdf_path: str) -> None:
        """
        Analyse itérative d'un fichier PDF avec expressions régulières (Regex).
        """
        try:
            reader = PdfReader(pdf_path)
            text = ""
            for page in reader.pages:
                text += page.extract_text() + "\n"

            lines = [l.strip() for l in text.split("\n") if l.strip()]
            fournisseur = ""
            if lines and "BILL TO" not in lines[0].upper() and "PACKING LIST" not in lines[0].upper():
                fournisseur = lines[0].strip()

            # Global PO and Lot (if present in header)
            global_po = ""
            global_lot = ""
            
            # Pattern : PO # : 123456
            po_header_match = re.search(r"(?i)PO\s*#\s*[:]\s*([\d]+)", text)
            if po_header_match:
                global_po = po_header_match.group(1)
            elif re.search(r"(?i)CUSTOMER\s*P\.?O\.?\s*NO\.?\s*([\d]+)", text):
                global_po = re.search(r"(?i)CUSTOMER\s*P\.?O\.?\s*NO\.?\s*([\d]+)", text).group(1)

            # Pattern : N° Lot : 123456
            lot_header_match = re.search(r"(?i)N[o°]\s*Lot\s*[:]\s*([\d]+)", text)
            if lot_header_match:
                global_lot = lot_header_match.group(1)

            # Ligne par ligne pour associer chaque article à son PO/Lot
            for line in lines:
                po, lot, art_code = global_po, global_lot, ""
                
                # Format 1: PO:00169477821520000032000006
                m1 = re.search(r"(?i)po:\s*(\d{8})(\d{10})?(\d{6,})", line)
                if m1:
                    po = m1.group(1)
                    art_code = m1.group(3)
                
                # Format 2: PO# 00017062/MEN#25102 10020313
                m2 = re.search(r"(?i)PO#\s*(\d+)/MEN#(\d+)\s+(\d+)", line)
                if m2:
                    po = m2.group(1)
                    art_code = m2.group(2) # MEN# is the article reference!
                    lot = m2.group(3) # The number after is the lot or supplier code
                    
                # Format 3: 00161343 25053 21870001 (PO Lot Item)
                m3 = re.search(r"^(\d{8})\s+(\d{4,6})\s+(\d{6,})", line)
                if m3:
                    po = m3.group(1)
                    lot = m3.group(2)
                    art_code = m3.group(3)
                    
                # Format 4: 40110011 MANDOLINE SLICER... where 40110011 is item code
                m4 = re.search(r"^(\d{6,})\s+[A-Za-z]+", line)
                if m4 and not art_code:
                    art_code = m4.group(1)

                if art_code:
                    if art_code not in self.articles_pdf:
                        self.articles_pdf[art_code] = []
                    info = {"po": po, "lot": lot, "fournisseur": fournisseur}
                    if info not in self.articles_pdf[art_code]:
                        self.articles_pdf[art_code].append(info)
                        
            logging.info(f"[SUCCÈS] Indexation PDF terminée pour {os.path.basename(pdf_path)}")
            
        except Exception as e:
            logging.error(f"[ERREUR] Échec de l'OCR/Parsing du PDF {pdf_path}: {e}")

    def chercher_infos_pdf(self, code_article: str, ref_article: str = "") -> list:
        """
        Recherche en mémoire les données extraites liées à un article spécifique.
        
        Stratégie :
        Identique à la stratégie DataLoader : exact match, puis fuzzy match.
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
        """
        Politique de rétention (Log rotation).
        Déplace les PDF consommés vers les archives pour éviter de polluer 
        la prochaine itération et provoquer des faux positifs (mauvais PO lié à la session de la veille).
        """
        import time
        import shutil
        
        archive_dir = os.path.join(self.pdf_dir, "archives")
        if not os.path.exists(archive_dir):
            os.makedirs(archive_dir)
            
        pdf_files = [f for f in os.listdir(self.pdf_dir) if f.lower().endswith('.pdf')]
        if not pdf_files:
            return
            
        logging.info(f"[INFO] Déplacement de {len(pdf_files)} PDF vers les archives...")
        for file_name in pdf_files:
            src = os.path.join(self.pdf_dir, file_name)
            dst = os.path.join(archive_dir, file_name)
            try:
                # Anti-collision
                if os.path.exists(dst):
                    base, ext = os.path.splitext(file_name)
                    dst = os.path.join(archive_dir, f"{base}_{int(time.time())}{ext}")
                shutil.move(src, dst)
            except Exception as e:
                logging.error(f"[ERREUR] Impossible d'archiver {file_name}: {e}")
