import pandas as pd
import logging
import os

# Configuration du logging (Bonne pratique MLOps : tracer les actions)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/data_processing.log"),
        logging.StreamHandler()
    ]
)

from src.sylob_api import SylobAPI

class DataLoader:
    """
    Classe responsable du chargement et de la recherche des articles.
    Gère désormais une source hybride : API Sylob (temps réel) + CSV (secours).
    """
    
    def __init__(self, csv_path="data/article.csv"):
        self.csv_path = csv_path
        self.df = None
        self.sylob = SylobAPI() # Nouvelle source API
        self._load_data()

    def _load_data(self):
        """Charge le fichier CSV avec Pandas"""
        if not os.path.exists(self.csv_path):
            logging.error(f"Fichier introuvable : {self.csv_path}")
            return

        try:
            # Lecture du CSV : 
            # sep=';' car c'est le séparateur standard en France
            # encoding='ISO-8859-1' pour gérer les accents français
            # dtype=str pour éviter que les codes barres perdent leurs '0' au début
            self.df = pd.read_csv(
                self.csv_path, 
                sep=';', 
                encoding='ISO-8859-1', 
                dtype=str, 
                header=None
            )
            
            # Renommage des colonnes pour plus de clarté
            # On s'attend à : 0=Référence, 1=EAN, 2=Désignation
            self.df.columns = ['ref', 'ean', 'designation']
            
            # Nettoyage des espaces superflus (trim)
            for col in self.df.columns:
                self.df[col] = self.df[col].str.strip()
                
            logging.info(f"Base article chargée avec succès : {len(self.df)} articles.")
            
        except Exception as e:
            logging.error(f"Erreur lors de la lecture du CSV : {e}")

    def chercher_article(self, code):
        """
        Recherche un article. Ordre de priorité :
        1. API Sylob (Temps réel)
        2. EAN exact dans le CSV
        3. Référence exacte dans le CSV
        4. Recherche partielle dans le CSV (coeur de code)
        """
        # --- PRIORITÉ 1 : API SYLOB (si le code ressemble à un EAN) ---
        if code.isdigit() and len(code) >= 8:
            article_sylob = self.sylob.chercher_article(code)
            if article_sylob:
                logging.info(f"Article récupéré en direct de Sylob : {article_sylob['designation']}")
                return article_sylob

        # --- FALLBACK : RECHERCHE DANS LE CSV LOCAL ---
        if self.df is None:
            return None

        # Recherche par EAN exact
        resultat = self.df[self.df['ean'] == code]
        
        # Si rien trouvé, on teste la référence exacte
        if resultat.empty:
            resultat = self.df[self.df['ref'] == code]
            
        # Recherche souple (coeur de code) pour les variations de douchettes
        if resultat.empty and len(code) >= 10:
            coeur_du_code = code[1:11] 
            resultat = self.df[self.df['ean'].str.contains(coeur_du_code, na=False)]
            if not resultat.empty:
                logging.info(f"Article trouvé via recherche du coeur de code dans le CSV ({coeur_du_code})")

        if not resultat.empty:
            article = resultat.iloc[0].to_dict()
            article['source'] = 'CSV Local'
            logging.info(f"Article trouvé dans le CSV : {article['designation']}")
            return article
            
        logging.warning(f"Aucun article trouvé (Sylob ou CSV) pour le code : {code}")
        return None

if __name__ == "__main__":
    # Petit test de fonctionnement local
    loader = DataLoader()
    test_code = "10120098" # Exemple de réf
    print(f"Test recherche {test_code} :", loader.chercher_article(test_code))
