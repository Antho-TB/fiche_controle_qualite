"""
[SECRETS] Migration des credentials Sylob du .env vers Azure Key Vault.

Strategie :
- Lit le .env local, construit une charge utile JSON, et ecrit UN SEUL secret
  `tb-sylob-client` dans kv-dtpf-prod, source de verite partagee avec MyReport
  et tout futur connecteur Sylob (socle data commun, section 4).
- Aucun secret n est affiche ni journalise : le script ne montre que les noms
  de champs. La valeur transite du .env vers Key Vault sans passer par la
  console ni par un fichier temporaire.
- Idempotent : relancer ne cree qu une nouvelle version du secret.

Usage :
    python scripts/migrer_secrets_sylob.py --verifier   # controle seul
    python scripts/migrer_secrets_sylob.py --appliquer  # ecrit dans Key Vault

Prerequis : az login effectue, droits set sur kv-dtpf-prod.
"""

import json
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
for _bruyant in ("azure", "azure.identity", "azure.core.pipeline.policies."
                 "http_logging_policy", "urllib3"):
    logging.getLogger(_bruyant).setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

VAULT_URL = "https://kv-dtpf-prod.vault.azure.net/"
ENTREE_KV = "tb-sylob-client"
CORRESPONDANCE: dict[str, str] = {
    "user": "SYLOB_USER",
    "password": "SYLOB_PASS",
    "unite_pers": "SYLOB_UNITE_PERS",
    "session_id": "SYLOB_SESSION_ID",
    "base_url1": "SYLOB_BASE_URL1",
    "base_url": "SYLOB_BASE_URL",
}


def _charger_env() -> dict[str, str]:
    """Construit la charge utile depuis le .env, sans jamais l afficher."""
    from dotenv import load_dotenv
    racine = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    load_dotenv(os.path.join(racine, ".env"))
    charge = {champ: os.getenv(variable, "")
              for champ, variable in CORRESPONDANCE.items()}
    manquants = [c for c, v in charge.items() if not v and c != "base_url"]
    if manquants:
        logger.error("[ECHEC] Champs absents du .env : %s", ", ".join(manquants))
        sys.exit(1)
    logger.info("[INFO] Champs prets : %s", ", ".join(sorted(charge)))
    return charge


def _client_kv() -> object:
    """Ouvre un client Key Vault avec l identite Azure courante."""
    from azure.identity import DefaultAzureCredential
    from azure.keyvault.secrets import SecretClient
    return SecretClient(vault_url=VAULT_URL, credential=DefaultAzureCredential())


def verifier() -> None:
    """Controle que le secret est lisible et complet, sans exposer sa valeur."""
    try:
        charge = json.loads(_client_kv().get_secret(ENTREE_KV).value)
    except Exception as e:
        logger.error("[ECHEC] Secret %s illisible : %s", ENTREE_KV, e)
        sys.exit(1)
    attendus = set(CORRESPONDANCE) - {"base_url"}
    manquants = sorted(attendus - {c for c, v in charge.items() if v})
    if manquants:
        logger.error("[ECHEC] Champs manquants dans le secret : %s",
                     ", ".join(manquants))
        sys.exit(1)
    logger.info("[SUCCES] Secret %s complet (%d champs).", ENTREE_KV, len(charge))


def appliquer() -> None:
    """Ecrit la charge utile dans Key Vault, puis verifie la relecture."""
    charge = _charger_env()
    _client_kv().set_secret(ENTREE_KV, json.dumps(charge, separators=(",", ":")))
    logger.info("[SUCCES] Secret %s ecrit dans kv-dtpf-prod.", ENTREE_KV)
    verifier()
    logger.info("[INFO] Etape suivante : supprimer le .env du partage reseau et "
                "retirer sa copie de Deploiement_Serveur.ps1.")


if __name__ == "__main__":
    if "--appliquer" in sys.argv:
        appliquer()
    elif "--verifier" in sys.argv:
        verifier()
    else:
        print(__doc__)
