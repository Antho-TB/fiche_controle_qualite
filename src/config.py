"""
[CONFIG] Configuration centralisee de la fiche de controle.

Strategie :
- Une seule classe lit l'environnement. Les modules ne font plus d'os.getenv()
  disperses : la Web App Azure et l'executable du poste partagent le meme code,
  seules les variables changent (app settings d'un cote, valeurs par defaut de
  l'autre).
- Les valeurs par defaut reproduisent le comportement historique du poste
  (compte PostgreSQL nominatif, dossier local) : rien ne change pour
  l'executable tant qu'aucune variable n'est posee.
- Aucun secret ici : uniquement des NOMS de secrets Key Vault.

Junior Tip : une valeur lue a l'import est figee pour toute la vie du
processus. Les tests qui changent l'environnement doivent donc recharger la
classe via `Config.recharger()`, pas modifier os.environ apres coup.
"""

import os


def _bool(nom: str, defaut: bool) -> bool:
    """Lit un booleen d'environnement (1/0, true/false, oui/non)."""
    valeur = os.getenv(nom)
    if valeur is None or valeur.strip() == "":
        return defaut
    return valeur.strip().lower() in ("1", "true", "oui", "yes", "on")


class Config:
    """Parametres de l'application, lus une fois dans l'environnement."""

    KEY_VAULT_URL: str
    PG_HOTE: str
    PG_BASE: str
    PG_SECRET_LOGIN: str
    PG_SECRET_PASSWORD: str
    SYLOB_ACTIVE: bool
    SYLOB_HOTE: str
    SYLOB_SECRET: str
    STOCKAGE: str
    DOSSIER_LOCAL: str
    SMB_SERVEUR: str
    SMB_PARTAGE: str
    SMB_DOSSIER_RACINE: str
    SMB_SECRET_LOGIN: str
    SMB_SECRET_PASSWORD: str
    SOUS_DOSSIER: str
    DRIVE_DOSSIER_ID: str
    GCP_SECRET_SA: str
    OCR_ACTIVE: bool
    GEMINI_ACTIF: bool
    GEMINI_PROJET: str
    GEMINI_LOCATION: str
    GEMINI_MODELE: str
    OPERATEUR_LOCAL: str

    @classmethod
    def recharger(cls) -> None:
        """(Re)lit toutes les variables d'environnement."""
        nom_coffre = os.getenv("KEY_VAULT_NAME", "kv-dtpf-prod")
        cls.KEY_VAULT_URL = "https://%s.vault.azure.net/" % nom_coffre
        cls.PG_HOTE = os.getenv(
            "PG_HOST", "psql-dtpf-psql-prod.postgres.database.azure.com")
        cls.PG_BASE = os.getenv("PG_DB", "dtpf_sylob_prod")
        cls.PG_SECRET_LOGIN = os.getenv(
            "PG_SECRET_LOGIN", "psql-prod-sylob-anthony-bezille-login")
        cls.PG_SECRET_PASSWORD = os.getenv(
            "PG_SECRET_PASSWORD", "psql-prod-sylob-anthony-bezille-password")

        cls.SYLOB_ACTIVE = _bool("SYLOB_ACTIVE", True)
        # Vide : on garde l'hote de l'URL du secret (srv-erp, resolu sur le
        # reseau TB). En Azure, le DNS interne n'est pas resolu : on force l'IP.
        cls.SYLOB_HOTE = os.getenv("SYLOB_HOTE", "")
        cls.SYLOB_SECRET = os.getenv("SYLOB_SECRET", "tb-sylob-client")

        # "local" : dossier du poste ou de developpement. "smb" : SRV-FILES-POM.
        # "drive" : Drive partage Google, repli decide le 09/10/2026 tant que le
        # compte de service AD n'est pas cree.
        cls.STOCKAGE = os.getenv("STOCKAGE", "smb" if os.getenv("SMB_SERVEUR") else "local")
        # Sous-dossier annuel du service qualite : <racine>/<annee>/Contrôle TB.
        cls.SOUS_DOSSIER = os.getenv("SOUS_DOSSIER", os.getenv("SMB_SOUS_DOSSIER", "Contrôle TB"))
        cls.DRIVE_DOSSIER_ID = os.getenv("DRIVE_DOSSIER_ID", "")
        # Cle du compte de service Google (Drive et Vertex AI), JSON au Key Vault.
        cls.GCP_SECRET_SA = os.getenv("GCP_SECRET_SA", "gcp-fichectrl-sa-key")
        cls.DOSSIER_LOCAL = os.getenv("DOSSIER_LOCAL", "")
        cls.SMB_SERVEUR = os.getenv("SMB_SERVEUR", "")
        cls.SMB_PARTAGE = os.getenv("SMB_PARTAGE", "PARTAGE")
        cls.SMB_DOSSIER_RACINE = os.getenv(
            "SMB_DOSSIER_RACINE", "QUALITE/R4 ACHATS/Contrôle réception")
        cls.SMB_SECRET_LOGIN = os.getenv("SMB_SECRET_LOGIN", "svc-fichectrl-ad-login")
        cls.SMB_SECRET_PASSWORD = os.getenv(
            "SMB_SECRET_PASSWORD", "svc-fichectrl-ad-password")

        cls.OCR_ACTIVE = _bool("OCR_ACTIVE", True)
        # Gemini : repli de lecture des Packing Lists que l'OCR n'exploite pas.
        # Projet GCP dedie, pour lire son cout separement (decision du 09/10).
        cls.GEMINI_PROJET = os.getenv("GEMINI_PROJET", "")
        cls.GEMINI_ACTIF = _bool("GEMINI_ACTIF", bool(cls.GEMINI_PROJET))
        cls.GEMINI_LOCATION = os.getenv("GEMINI_LOCATION", "europe-west1")
        cls.GEMINI_MODELE = os.getenv("GEMINI_MODELE", "gemini-2.5-flash")
        # Identite affichee hors Easy Auth (poste de developpement).
        cls.OPERATEUR_LOCAL = os.getenv("OPERATEUR_LOCAL", "poste-local")


Config.recharger()
