import os
import re
import sys
import logging
from pypdf import PdfReader

def get_base_path():
    """ Retourne le chemin d'exécution réel (script Python ou .exe compilé) """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


class PDFExtractor:
    """
    Extrait les données (N° de Commande, N° de Lot) des fichiers PDF (Packing Lists).
    """
    
    def __init__(self, pdf_dir=None):
        if pdf_dir is None:
            self.pdf_dir = os.path.join(get_base_path(), "1_Packing_Lists_A_Traiter")
        else:
            self.pdf_dir = pdf_dir
        self.articles_pdf = {} # Dictionnaire avec la référence article (ou coeur) comme clé
        self._load_all_pdfs()

    def _load_all_pdfs(self):
        """Scanne le dossier et extrait les données de tous les PDF présents."""
        if not os.path.exists(self.pdf_dir):
            os.makedirs(self.pdf_dir)
            logging.info(f"Dossier créé : {self.pdf_dir}")
            return

        pdf_files = [f for f in os.listdir(self.pdf_dir) if f.lower().endswith('.pdf')]
        
        if not pdf_files:
            logging.info(f"Aucun PDF trouvé dans {self.pdf_dir}")
            return
            
        logging.info(f"Lecture automatique de {len(pdf_files)} fichier(s) PDF...")
        
        for file_name in pdf_files:
            pdf_path = os.path.join(self.pdf_dir, file_name)
            self._extract_from_pdf(pdf_path)

    def _extract_from_pdf(self, pdf_path):
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
            
            po_header_match = re.search(r"(?i)PO\s*#\s*[:：]\s*([\d、]+)", text)
            if po_header_match:
                global_po = po_header_match.group(1).split("、")[0]
            elif re.search(r"(?i)CUSTOMER\s*P\.?O\.?\s*NO\.?\s*([\d]+)", text):
                global_po = re.search(r"(?i)CUSTOMER\s*P\.?O\.?\s*NO\.?\s*([\d]+)", text).group(1)

            lot_header_match = re.search(r"(?i)N[°º]\s*Lot\s*[:：]\s*([\d、]+)", text)
            if lot_header_match:
                global_lot = lot_header_match.group(1).split("、")[0]

            # Parse line by line to find item specific PO/Lot
            for line in lines:
                po, lot, art_code = global_po, global_lot, ""
                
                # Format 1: PO:00169477821520000032000006
                m1 = re.search(r"(?i)po:\s*(\d{8})(\d{10})?(\d{6,})", line)
                if m1:
                    po = m1.group(1)
                    art_code = m1.group(3)
                
                # Format 2: PO# 00017062/MEN#25102 10020313
                m2 = re.search(r"(?i)PO#\s*(\d+)/MEN#(\d+)\s+(\d{6,})", line)
                if m2:
                    po = m2.group(1)
                    lot = m2.group(2)
                    art_code = m2.group(3)
                    
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
                        
            logging.info(f"Extraction PDF terminée pour {os.path.basename(pdf_path)}")
            
        except Exception as e:
            logging.error(f"Erreur lors de la lecture du PDF {pdf_path}: {e}")

    def chercher_infos_pdf(self, code_article, ref_article=""):
        """
        Cherche si on a des infos de Commande et de Lot pour un article donné.
        Essaie avec le code scanné complet ou partiel, ou la Référence.
        """
        # On essaie de trouver le code exact
        if code_article in self.articles_pdf:
            return self.articles_pdf[code_article]
            
        if ref_article and ref_article in self.articles_pdf:
            return self.articles_pdf[ref_article]
            
        # Stratégie fuzzy : chercher si une partie longue du code est dans le PDF
        for k, v in self.articles_pdf.items():
            if len(k) >= 6 and (k in code_article or k in ref_article):
               return v
               
        return []

    def archiver_pdfs(self):
        """
        Déplace les PDF traités vers un dossier 'archives' 
        pour ne pas polluer les sessions de contrôle futures.
        """
        import time
        import shutil
        
        archive_dir = os.path.join(self.pdf_dir, "archives")
        if not os.path.exists(archive_dir):
            os.makedirs(archive_dir)
            
        pdf_files = [f for f in os.listdir(self.pdf_dir) if f.lower().endswith('.pdf')]
        if not pdf_files:
            return
            
        logging.info(f"Archivage de {len(pdf_files)} PDF(s)...")
        for file_name in pdf_files:
            src = os.path.join(self.pdf_dir, file_name)
            dst = os.path.join(archive_dir, file_name)
            try:
                # Si un fichier du même nom existe déjà dans l'archive, on ajoute un timestamp
                if os.path.exists(dst):
                    base, ext = os.path.splitext(file_name)
                    dst = os.path.join(archive_dir, f"{base}_{int(time.time())}{ext}")
                shutil.move(src, dst)
            except Exception as e:
                logging.error(f"Impossible d'archiver {file_name}: {e}")

