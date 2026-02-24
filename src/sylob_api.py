import os
import base64
import requests
import urllib3
import xml.etree.ElementTree as ET
import logging
from dotenv import load_dotenv

# Chargement des variables d'environnement depuis le fichier .env
load_dotenv()

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
        self.base_url = os.getenv("SYLOB_BASE_URL")
        
        # Préparation du header d'authentification Basic
        self.headers = self._build_headers()

    def _build_headers(self):
        """Construit le header d'autorisation Basic Base64"""
        login = f"{self.user}@@{self.unite_pers}@@{self.session_id}"
        userpass = f"{login}:{self.password}".encode("utf-8")
        token = base64.b64encode(userpass).decode("ascii")
        return {"Authorization": f"Basic {token}"}

    def chercher_article(self, ean13):
        """Interroge l'API Sylob pour un EAN13 donné"""
        if not self.base_url:
            logging.error("URL Sylob non configurée dans le .env")
            return None

        params = {"limite": "1", "EAN13": ean13}
        
        try:
            logging.info(f"Interrogation API Sylob pour EAN : {ean13}")
            response = requests.get(
                self.base_url,
                params=params,
                headers=self.headers,
                verify=False, # Pour le certificat interne srv-erp
                timeout=5      # On ne veut pas bloquer l'app trop longtemps
            )
            response.raise_for_status()
            
            return self._parser_xml(response.text)
            
        except requests.exceptions.RequestException as e:
            logging.error(f"Erreur lors de l'appel API Sylob : {e}")
            return None

    def _parser_xml(self, xml_text):
        """Extrait Code, Désignation et GTIN du XML de réponse"""
        try:
            root = ET.fromstring(xml_text)
            ligne = root.find(".//ligneResultatWS")
            
            if ligne is None:
                return None

            valeurs = ligne.findall("valeur")
            if len(valeurs) < 3:
                return None

            return {
                'ref': (valeurs[0].text or "").strip(),
                'designation': (valeurs[1].text or "").strip(),
                'ean': (valeurs[2].text or "").strip(),
                'source': 'Sylob API'
            }
        except ET.ParseError as e:
            logging.error(f"Erreur de parsing XML Sylob : {e}")
            return None

    def chercher_lot_par_po(self, po: str):
        """Interroge l'API Sylob pour trouver le lot correspondant à un numéro de commande (PO)"""
        if not self.base_url:
            return None
            
        # L'URL de base est configurée pour API_ART_EAN, on la remplace pour utiliser API_LOT_PO
        url = self.base_url.replace("API_ART_EAN", "API_LOT_PO")
        params = {"limite": "1", "PO": po}
        
        try:
            logging.info(f"Interrogation API Sylob LOT pour PO : {po}")
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
            logging.error(f"Erreur lors de l'appel API Sylob (Lot PO) : {e}")
            return None
        except ET.ParseError as e:
            logging.error(f"Erreur de parsing XML Sylob (Lot) : {e}")
            return None

if __name__ == "__main__":
    # Test local
    logging.basicConfig(level=logging.INFO)
    api = SylobAPI()
    print("Résultat test :", api.chercher_article("3118220054967"))
