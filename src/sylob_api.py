import os
import sys
import base64
import requests
import urllib3
import xml.etree.ElementTree as ET
import logging
from dotenv import load_dotenv

def get_base_path():
    """ Retourne le chemin d'exécution réel (script Python ou .exe compilé) """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

# Chargement explicite du .env situé à la racine de l'exécutable
env_path = os.path.join(get_base_path(), '.env')
if os.path.exists(env_path):
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv() # Fallback standard

# Désactivation des avertissements pour les certificats SSL auto-signés
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class SylobAPI:
    """
    Gestionnaire pour interroger l'API REST de l'ERP Sylob.
    Permet de récupérer les informations d'un article à partir de son EAN13.
    """
    
    def __init__(self):
        # Récupération des paramètres depuis le .env
        self.user = os.getenv("SYLOB_USER")
        self.password = os.getenv("SYLOB_PASS")
        self.unite_pers = os.getenv("SYLOB_UNITE_PERS")
        self.session_id = os.getenv("SYLOB_SESSION_ID")
        self.base_url1 = os.getenv("SYLOB_BASE_URL1", "") # Utilisation exclusive de RECEPTIONAPI
        
        # Préparation du header d'authentification Basic
        self.headers = self._build_headers()

    def _build_headers(self):
        """Construit le header d'autorisation Basic Base64"""
        login = f"{self.user}@@{self.unite_pers}@@{self.session_id}"
        userpass = f"{login}:{self.password}".encode("utf-8")
        token = base64.b64encode(userpass).decode("ascii")
        return {"Authorization": f"Basic {token}"}

    def chercher_lot_par_po(self, po: str, art: str = "", lot: str = "", ean: str = ""):
        """Interroge l'API Sylob pour trouver le lot correspondant à un numéro de commande (PO) et article"""
        url = self.base_url1
        if not url:
            logging.error("URL Sylob RECEPTIONAPI non configurée")
            return None
        
        # La nouvelle requête attend CMD, ART, LOT et EAN
        params = {"limite": "1", "CMD": po, "ART": art, "LOT": lot, "EAN": ean}
        
        try:
            logging.info(f"Interrogation API Sylob RECEPTIONAPI pour PO:{po}, ART:{art}, LOT:{lot}")
            response = requests.get(
                url,
                params=params,
                headers=self.headers,
                verify=False,
                timeout=5
            )
            response.raise_for_status()
            
            # Parser XML pour le Lot
            root = ET.fromstring(response.text)
            ligne = root.find(".//ligneResultatWS")
            
            if ligne is None:
                logging.info(f"Aucun lot trouvé dans Sylob pour le PO : {po}")
                return None
                
            valeurs = ligne.findall("valeur")
            
            # Le lot est supposé être retourné par la requête
            # Vu qu'on a sélectionné "Numéro de la commande" puis "Numéro de lot"
            if len(valeurs) >= 2:
                # Si la valeur 0 est le PO, la valeur 1 est le lot
                lot = (valeurs[1].text or "").strip()
                return lot
            elif len(valeurs) == 1:
                return (valeurs[0].text or "").strip()
            
            return None
            
        except requests.exceptions.RequestException as e:
            logging.warning(f"Avertissement lors de l'appel API Sylob (Lot PO), passage au PDF : {e}")
            return None
        except ET.ParseError as e:
            logging.warning(f"Avertissement de parsing XML Sylob (Lot), passage au PDF : {e}")
            return None

if __name__ == "__main__":
    # Test local
    logging.basicConfig(level=logging.INFO)
    api = SylobAPI()
    print("API Sylob initialisée.")
