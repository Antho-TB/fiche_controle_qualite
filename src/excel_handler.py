import openpyxl
from datetime import datetime
import os
import logging

class ExcelHandler:
    """
    Classe pour manipuler le fichier Excel de contrôle réception.
    On utilise openpyxl pour préserver le formatage et les formules du template.
    """
    
    def __init__(self, template_path="data/FOR-ACH-30-2 Fiche d'inspection produit-Contrôle réception.xlsx"):
        self.template_path = template_path
        self.output_dir = "outputs"
        
        # S'assurer que le dossier de sortie existe
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

    def generer_fiche(self, article_info):
        """
        Remplit une nouvelle fiche basée sur le template avec les infos de l'article.
        """
        if not os.path.exists(self.template_path):
            logging.error(f"Template Excel introuvable : {self.template_path}")
            return None

        # On crée un nom de fichier unique pour cette inspection
        # Format : Fiche_[Ref]_[Date]_[Heure].xlsx
        now = datetime.now()
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        nom_sortie = f"Fiche_{article_info['ref']}_{timestamp}.xlsx"
        chemin_sortie = os.path.join(self.output_dir, nom_sortie)

        try:
            # Chargement du template
            wb = openpyxl.load_workbook(self.template_path)
            ws = wb.active # On travaille sur la feuille active

            # --- Saisie des données dans les cellules (Corrigé selon retour utilisateur) ---
            # NOTE : D'après la capture écran, l'en-tête se situe en haut.
            
            # 1. Date de réception (C4)
            ws['C4'] = now.strftime("%d/%m/%Y")
            
            # 2. Référence Article (B5)
            ws['B5'] = article_info['ref']
            
            # 3. Désignation Article (B6)
            ws['B6'] = article_info['designation']
            
            # Sauvegarde du nouveau fichier
            wb.save(chemin_sortie)
            logging.info(f"Fiche générée avec succès : {chemin_sortie}")
            return chemin_sortie

        except Exception as e:
            logging.error(f"Erreur lors de la manipulation Excel : {e}")
            return None

if __name__ == "__main__":
    # Test rapide
    h = ExcelHandler()
    dump_article = {'ref': 'TEST-123', 'designation': 'Article de Test', 'ean': '000000'}
    h.generer_fiche(dump_article)
