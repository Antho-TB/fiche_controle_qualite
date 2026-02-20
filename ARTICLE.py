import base64
import requests
import urllib3
import xml.etree.ElementTree as ET

# Désactiver l'avertissement lié à verify=False (certificat interne)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# === PARAMÈTRES SYLOB À ADAPTER ===
UTILISATEUR = "ghouillon"                 # identifiant utilisateur
UNITE_PERS = "SE_TARRERIAS_BONJEAN"       # unité de persistance
SESSION_ID = "00001"                      # identifiant de session (arbitraire)
MOT_DE_PASSE = "65gMwdVE7"                # mot de passe de l'utilisateur

BASE_URL = "https://srv-erp:8443/rest/query/API_ART_EAN/resultat"

# Construction du login au format spécifié :
# {{utilisateur}}@@{{unite_persistance}}@@{{identifiant_session}}
LOGIN = f"{UTILISATEUR}@@{UNITE_PERS}@@{SESSION_ID}"

# Construction de la chaîne à encoder en base64 : login:motdepasse
userpass = f"{LOGIN}:{MOT_DE_PASSE}".encode("utf-8")
basic_token = base64.b64encode(userpass).decode("ascii")

HEADERS = {
    "Authorization": f"Basic {basic_token}"
}

# === FONCTIONS ===
def interroger_api(ean13: str) -> str:
    """
    GET https://srv-erp:8443/rest/query/API_ART_EAN/resultat?limite=1&EAN13=<ean13>
    avec header Authorization: Basic <token>
    """
    params = {
        "limite": "1",
        "EAN13": ean13
    }

    response = requests.get(
        BASE_URL,
        params=params,
        headers=HEADERS,
        verify=False  # cert self-signed
    )
    response.raise_for_status()
    return response.text


def parser_xml(xml_text: str):
    """
    Parse le XML et retourne (code, designation, gtin13) à partir de la
    première <ligneResultatWS>.
    """
    root = ET.fromstring(xml_text)

    ligne = root.find(".//ligneResultatWS")
    if ligne is None:
        return None

    valeurs = ligne.findall("valeur")
    if len(valeurs) < 3:
        return None

    code = (valeurs[0].text or "").strip()
    designation = (valeurs[1].text or "").strip()
    gtin13 = (valeurs[2].text or "").strip()

    return code, designation, gtin13


def main():
    print("=== Interrogation API Sylob par EAN13 ===\n")

    ean13 = input("Saisir l'EAN13 à interroger : ").strip()
    if not ean13:
        print("Aucun EAN13 saisi, arrêt.")
        input("\nAppuyez sur Entrée pour fermer la fenêtre...")
        return

    try:
        xml_text = interroger_api(ean13)
        result = parser_xml(xml_text)

        if not result:
            print("\nAucun résultat trouvé pour cet EAN13.")
        else:
            code, designation, gtin13 = result
            print("\n--- Résultat ---")
            print(f"Code       : {code}")
            print(f"Description: {designation}")
            print(f"GTIN-13    : {gtin13}")

    except requests.exceptions.HTTPError as e:
        print(f"\nErreur HTTP : {e}")
        print("Vérifie bien UTILISATEUR / UNITE_PERS / SESSION_ID / MOT_DE_PASSE.")
    except requests.exceptions.RequestException as e:
        print(f"\nErreur réseau : {e}")
    except ET.ParseError as e:
        print(f"\nErreur lors du parsing XML : {e}")

    input("\nAppuyez sur Entrée pour fermer la fenêtre...")


if __name__ == "__main__":
    main()
