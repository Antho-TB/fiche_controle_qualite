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

class DataLoader:
    """
    Classe responsable du chargement et de la recherche des articles.
    On utilise ISO-8859-1 car les exports ERP/WMS sous Windows sont souvent dans ce format.
    """
    
    def __init__(self, csv_path="data/article.csv"):
        self.csv_path = csv_path
        self.df = None
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
        Recherche un article par son code EAN (douchette) ou sa Référence.
        Retourne un dictionnaire avec les infos ou None.
        """
        if self.df is None:
            return None

        # On cherche d'abord dans les EAN (priorité douchette)
        resultat = self.df[self.df['ean'] == code]
        
        # Si rien trouvé, on teste la référence
        if resultat.empty:
            resultat = self.df[self.df['ref'] == code]
            
        # NOUVEAU : Recherche encore plus souple (Fuzzy Matching Léger)
        # Certains lecteurs ajoutent un préfixe (ex: '3') ou modifient le dernier chiffre.
        if resultat.empty and len(code) >= 10:
            # On cherche si une partie significative du code scanné existe dans la base
            # On prend les chiffres du milieu qui sont les plus fiables
            coeur_du_code = code[1:11] 
            resultat = self.df[self.df['ean'].str.contains(coeur_du_code, na=False)]
            if not resultat.empty:
                logging.info(f"Article trouvé via recherche du coeur de code ({coeur_du_code})")

        if not resultat.empty:
            article = resultat.iloc[0].to_dict()
            logging.info(f"Article trouvé : {article['designation']}")
            return article
            
        logging.warning(f"Aucun article trouvé pour le code : {code}")
        return None

if __name__ == "__main__":
    # Petit test de fonctionnement local
    loader = DataLoader()
    test_code = "10120098" # Exemple de réf
    print(f"Test recherche {test_code} :", loader.chercher_article(test_code))
