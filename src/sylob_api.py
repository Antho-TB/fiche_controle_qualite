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

if __name__ == "__main__":
    # Test local
    logging.basicConfig(level=logging.INFO)
    api = SylobAPI()
    print("Résultat test :", api.chercher_article("3118220054967"))
