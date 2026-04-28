"""
[ARCHITECTURE] I/O & Référentiel Article (fiche_de_controle)

Rôle global :
Ce module agit comme le référentiel maître des données articles au sein de l'application.
Il gère l'alimentation hybride des données de contrôle (soit via un dump CSV de secours, 
soit via l'API Sylob). C'est la brique d'accès aux données (Data Layer).

Stratégie métier (Résilience & Fallback) :
La logique est construite sur une architecture résiliente : on charge un fichier CSV
local en mémoire au démarrage. Si l'ERP Sylob est indisponible (latence réseau, VPN coupé),
l'application peut continuer à flasher des codes-barres sans interruption de la chaîne
logistique. De plus, il intègre une recherche "fuzzy" (coeur du code EAN) pour 
pallier les limitations physiques de certaines douchettes (qui tronquent les préfixes/suffixes).
"""

import pandas as pd
import logging
import os
import sys

def get_base_path() -> str:
    """
    Retourne le chemin d'exécution réel (script Python ou .exe compilé).
    
    Stratégie :
    L'application pouvant être packagée via PyInstaller pour les postes opérateurs,
    `__file__` ne pointera plus vers le bon dossier de ressources. `sys.frozen` 
    permet d'ancrer le script au bon endroit dans tous les scénarios.
    """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


# --- Configuration du logging (Bonne pratique MLOps : tracer les actions) ---
try:
    log_dir = os.path.join(get_base_path(), "logs")
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    log_file_path = os.path.join(log_dir, "data_processing.log")
    
    # Test d'écriture pour s'assurer des droits (environnement Windows restreint)
    with open(log_file_path, 'a', encoding='utf-8') as f:
        pass
        
except (PermissionError, OSError):
    import tempfile
    log_dir = os.path.join(tempfile.gettempdir(), "Scanner_Qualite_Logs")
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    log_file_path = os.path.join(log_dir, "data_processing.log")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file_path, encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# Silence verbose Azure SDK loggers
logging.getLogger("azure").setLevel(logging.WARNING)
logging.getLogger("azure.core.pipeline.policies.http_logging_policy").setLevel(logging.WARNING)
logging.getLogger("azure.identity").setLevel(logging.WARNING)

from src.sylob_api import SylobAPI

class DataLoader:
    """
    Classe responsable du chargement en RAM et de la recherche croisée des articles.
    """
    
    def __init__(self, csv_path: str = None):
        if csv_path is None:
            csv_path = os.path.join(get_base_path(), "0_Modele_Et_Donnees", "article.csv")
        self.csv_path = csv_path
        self.df = None
        self.sylob = SylobAPI() # Nouvelle source API
        self._load_data()

    def _load_data(self) -> None:
        """
        Charge le fichier CSV de référence avec Pandas.
        
        Stratégie :
        - sep=';' : standard d'export Excel FR.
        - encoding='ISO-8859-1' : pour gérer l'historique de l'ERP et les accents.
        - dtype=str : OBLIGATOIRE. Les codes-barres (EAN) commençant par 0 seraient tronqués
          par Pandas si traités en tant qu'entiers.
        """
        if not os.path.exists(self.csv_path):
            logging.warning(f"[INFO] Fichier CSV de fallback introuvable : {self.csv_path}. Utilisation exclusive de l'API Sylob.")
            return

        try:
            self.df = pd.read_csv(
                self.csv_path, 
                sep=';', 
                encoding='ISO-8859-1', 
                dtype=str, 
                header=0 # Use first row as column names
            )
            
            # Make sure columns are lowercase
            self.df.columns = [str(c).strip().lower() for c in self.df.columns]
            
            # Nettoyage des espaces superflus (trim) souvent générés par les exports ERP
            for col in self.df.columns:
                self.df[col] = self.df[col].astype(str).str.strip()
                
            logging.info(f"[SUCCÈS] Base article chargée en mémoire ({len(self.df)} articles).")
            
        except Exception as e:
            logging.error(f"[ERREUR] Échec de la lecture du CSV de secours : {e}")

    def chercher_article(self, code: str) -> dict:
        """
        Recherche un article dans la base de données locale (CSV).
        
        Stratégie :
        La recherche locale s'effectue en cascade :
        1. Correspondance exacte sur l'EAN (Code-barres)
        2. Correspondance exacte sur la Référence interne
        3. Recherche "fuzzy" : extraction du coeur du code EAN (caractères centraux)
           pour rattraper les lectures incomplètes du scanner.
           
        Args:
            code (str): Le code flashé par l'opérateur.
            
        Returns:
            dict: Les métadonnées de l'article, ou None si introuvable.
        """
        if self.df is None:
            return None

        # 1. Recherche par EAN exact
        resultat = self.df[self.df['ean'] == code]
        
        # 2. Si rien trouvé, on teste la référence exacte
        if resultat.empty:
            resultat = self.df[self.df['ref'] == code]
            
        # 3. Recherche souple (coeur de code) pour les variations matérielles (douchettes)
        if resultat.empty and len(code) >= 10:
            coeur_du_code = code[1:11] 
            resultat = self.df[self.df['ean'].str.contains(coeur_du_code, na=False)]
            if not resultat.empty:
                logging.info(f"[INFO] Article trouvé via recherche du coeur de code ({coeur_du_code})")

        if not resultat.empty:
            article = resultat.iloc[0].to_dict()
            article['source'] = 'CSV Local'
            # Sanity check : forcer une string vide au lieu de valeurs NaN
            article['po'] = article.get('po', '') if pd.notna(article.get('po')) else ''
            article['lot'] = article.get('lot', '') if pd.notna(article.get('lot')) else ''
            
            logging.info(f"[SUCCÈS] Article validé : {article['designation']}")
            return article
            
        logging.warning(f"[ERREUR] Aucun article trouvé pour le code : {code}")
        return None

if __name__ == "__main__":
    loader = DataLoader()
    test_code = "10120098"
    print(f"Test recherche {test_code} :", loader.chercher_article(test_code))
