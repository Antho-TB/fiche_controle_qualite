"""
[ARCHITECTURE] Interfaçage ERP (fiche_de_controle)

Rôle global :
Ce module gère les communications réseau avec l'ERP Sylob (via son API REST/XML).
Il permet d'interroger la base centrale de l'entreprise pour valider les numéros de Commande (PO)
et de Lots détectés par l'extracteur PDF.

Stratégie métier (Zero Trust & Secret Management) :
Pour respecter la doctrine Nubo, aucun secret (user, mot de passe, session) n'est stocké en dur.
Ils sont récupérés à la volée depuis Azure Key Vault via une Managed Identity ou l'Azure CLI de 
l'utilisateur. Le certificat SSL interne de Sylob étant potentiellement auto-signé, nous désactivons 
(temporairement) l'avertissement de sécurité SSL localement, tout en conservant une authentification
robuste via Basic Auth en Base64.
"""

import os
import sys
import base64
import requests
import urllib3
import xml.etree.ElementTree as ET
import logging
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

# Désactivation des avertissements pour les certificats SSL auto-signés
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class SylobAPI:
    """
    Client de l'API REST de l'ERP Sylob (Endpoint RECEPTIONAPI).
    """
    
    def __init__(self):
        # --- Standard NUBO : Authentification Azure Key Vault ---
        vault_url = "https://kv-tb-ia-agents-secrets.vault.azure.net/"
        try:
            credential = DefaultAzureCredential()
            client = SecretClient(vault_url=vault_url, credential=credential)
            self.user = client.get_secret("SYLOB-USER").value
            self.password = client.get_secret("SYLOB-PASS").value
            self.unite_pers = client.get_secret("SYLOB-UNITE-PERS").value
            self.session_id = client.get_secret("SYLOB-SESSION-ID").value
            self.base_url1 = client.get_secret("SYLOB-BASE-URL1").value
        except Exception as e:
            logging.error(f"[NUBO SEC] Erreur de récupération des secrets Sylob depuis AKV : {e}")
            self.user = ""
            self.password = ""
            self.unite_pers = ""
            self.session_id = ""
            self.base_url1 = ""
        
        self.headers = self._build_headers()

    def _build_headers(self) -> dict:
        """
        Construit le header d'autorisation Basic Base64 exigé par Sylob.
        """
        login = f"{self.user}@@{self.unite_pers}@@{self.session_id}"
        userpass = f"{login}:{self.password}".encode("utf-8")
        token = base64.b64encode(userpass).decode("ascii")
        return {"Authorization": f"Basic {token}"}

    def chercher_lot_par_po(self, po: str, art: str = "", lot: str = "", ean: str = "") -> str:
        """
        Interroge l'API Sylob pour valider l'existence d'un lot et d'une commande.
        
        Stratégie :
        L'API retourne un XML (et non du JSON). On utilise ElementTree pour extraire
        précisément le noeud <ligneResultatWS> et valider que l'ERP a bien connaissance
        de cette livraison imminente. En cas de timeout (latence Sylob), on déclenche un 
        fallback propre sans faire exploser l'application métier.
        
        Args:
            po (str): Numéro de Purchase Order.
            art (str): Référence interne.
            lot (str): Numéro de Batch/Lot fournisseur.
            ean (str): Code barres EAN.
            
        Returns:
            str: Le lot validé par l'ERP, ou None si échec.
        """
        url = self.base_url1
        if not url:
            logging.error("[ERREUR] URL Sylob RECEPTIONAPI non configurée.")
            return None
        
        params = {"limite": "1", "CMD": po, "ART": art, "LOT": lot, "EAN": ean}
        
        try:
            logging.info(f"[API] Interrogation Sylob (PO:{po}, ART:{art}, LOT:{lot})")
            response = requests.get(
                url,
                params=params,
                headers=self.headers,
                verify=False, # Certificat auto-signé interne
                timeout=5 # Fail-fast pour ne pas bloquer l'opérateur en entrepôt
            )
            response.raise_for_status()
            
            root = ET.fromstring(response.text)
            ligne = root.find(".//ligneResultatWS")
            
            if ligne is None:
                logging.info(f"[INFO] Aucun lot trouvé dans Sylob pour le PO : {po}")
                return None
                
            valeurs = ligne.findall("valeur")
            
            if len(valeurs) >= 2:
                # La requête retourne généralement le PO puis le Lot.
                return (valeurs[1].text or "").strip()
            elif len(valeurs) == 1:
                return (valeurs[0].text or "").strip()
            
            return None
            
        except requests.exceptions.RequestException as e:
            logging.warning(f"[ALERTE] Timeout ou erreur réseau Sylob, fallback sur les données PDF : {e}")
            return None
        except ET.ParseError as e:
            logging.warning(f"[ALERTE] Le format XML de retour Sylob est invalide, fallback PDF : {e}")
            return None
