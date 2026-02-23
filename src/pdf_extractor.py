import os
import re
import logging
from pypdf import PdfReader

class PDFExtractor:
    """
    Extrait les données (N° de Commande, N° de Lot) des fichiers PDF (Packing Lists).
    """
    
    def __init__(self, pdf_dir="data/packing_lists"):
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

            # 1. Extraction des PO et Lots de l'en-tête
            po_header_match = re.search(r"PO\s*#\s*:\s*([\d、]+)", text)
            lot_header_match = re.search(r"N[°º]\s*Lot\s*[：:]\s*([\d、]+)", text)
            
            if not po_header_match or not lot_header_match:
                logging.warning(f"En-tête PO/Lot introuvable dans {pdf_path}")
                return
                
            po_list = [po.strip() for po in po_header_match.group(1).split("、")]
            lot_list = [lot.strip() for lot in lot_header_match.group(1).split("、")]
            
            # Mapping positionnel PO -> Lot
            po_to_lot = dict(zip(po_list, lot_list))
            
            # 2. Recherche des articles dans les lignes
            # Format: PO:00162322821520000021970001
            # 00162322 = PO | 8215200000 = Code H.S | 21970001 = Code Article interne (ou partie)
            lines = text.split("\n")
            for line in lines:
                match = re.search(r"(?i)po:\s*(\d{8})(\d{10})?(\d+)?\s*(.*)", line)
                if match:
                    po = match.group(1)
                    art_code = match.group(3)
                    
                    if art_code:
                        lot = po_to_lot.get(po, "")
                        # On stocke l'information pour l'associer au scan plus tard
                        self.articles_pdf[art_code] = {
                            "po": po,
                            "lot": lot
                        }
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
               
        return {"po": "", "lot": ""}
