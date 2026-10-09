"""
[AUTH] Identite Azure unique pour l application (fiche_de_controle).

Strategie :
- Le poste du service qualite n est PAS joint a Azure AD (dsregcmd :
  AzureAdJoined NO, WorkplaceJoined YES) et n a ni Azure CLI ni identite
  manageable. `DefaultAzureCredential` seul y echoue donc systematiquement,
  alors qu il fonctionne sur un poste de developpement ou `az login` a ete fait.
  C est la raison pour laquelle Key Vault n a jamais fonctionne en production.
- La chaine ci-dessous essaie d abord les identites non interactives (Managed
  Identity, Azure CLI, Visual Studio Code), puis retombe sur une connexion
  navigateur avec le compte TB de l operateur. Le jeton est mis en cache par
  Windows (DPAPI) : l operateur ne se connecte qu une fois, pas a chaque scan.
- Une seule instance est partagee par tous les modules : sans cela, chaque
  client Key Vault ouvrirait sa propre fenetre de connexion.

Prerequis cote Azure : le compte de l operateur doit avoir le droit `get` sur
les secrets `tb-sylob-client`, `psql-prod-sylob-anthony-bezille-login` et
`psql-prod-sylob-anthony-bezille-password` du coffre `kv-dtpf-prod`.

Junior Tip : ne jamais embarquer un secret de service principal dans un
executable pose sur un partage reseau. N importe qui pouvant lire le partage
lirait le secret. Une connexion nominative trace en plus QUI a accede a quoi.
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

TENANT_TB = "7c5e7e59-bf9f-42bf-87ae-f7b39ed22594"
_NOM_CACHE = "fiche_de_controle"

_credential = None
_echec_definitif = False


def obtenir_credential(interactif: bool = True) -> Optional[object]:
    """
    Rend l identite Azure de l application, en la creant au premier appel.

    Args:
        interactif: False pour interdire la connexion navigateur, par exemple
            dans un script planifie ou un diagnostic non surveille.

    Returns:
        Un credential azure-identity, ou None si aucune identite n est
        disponible. Le resultat est memorise, y compris l echec, pour ne pas
        rouvrir de fenetre de connexion a chaque tentative.
    """
    global _credential, _echec_definitif
    if _credential is not None:
        return _credential
    if _echec_definitif:
        return None

    try:
        from azure.identity import (ChainedTokenCredential,
                                    DefaultAzureCredential,
                                    InteractiveBrowserCredential,
                                    TokenCachePersistenceOptions)
    except ImportError as e:
        logger.error("[ECHEC] azure-identity absent (%s). Aucune lecture Key "
                     "Vault possible.", e)
        _echec_definitif = True
        return None

    silencieux = DefaultAzureCredential(
        exclude_interactive_browser_credential=True,
        exclude_shared_token_cache_credential=False,
    )
    if not interactif or os.getenv("FICHE_CONTROLE_SANS_INTERACTION"):
        _credential = silencieux
        logger.info("[INFO] Identite Azure non interactive uniquement.")
        return _credential

    try:
        cache = TokenCachePersistenceOptions(name=_NOM_CACHE)
        navigateur = InteractiveBrowserCredential(
            tenant_id=TENANT_TB,
            cache_persistence_options=cache,
        )
        _credential = ChainedTokenCredential(silencieux, navigateur)
        logger.info("[SUCCES] Identite Azure prete (connexion navigateur en "
                    "secours, jeton mis en cache).")
    except Exception as e:
        logger.warning("[ATTENTION] Cache de jeton indisponible (%s), "
                       "connexion non persistante.", e)
        _credential = ChainedTokenCredential(
            silencieux, InteractiveBrowserCredential(tenant_id=TENANT_TB))
    return _credential


def reinitialiser() -> None:
    """Oublie l identite memorisee. Utile en test, jamais en production."""
    global _credential, _echec_definitif
    _credential = None
    _echec_definitif = False