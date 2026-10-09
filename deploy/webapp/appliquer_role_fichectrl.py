"""
[OPS] Role PostgreSQL de la Web App Fiche de controle, en LECTURE SEULE.

Cree ou met a jour le role `dtpf_fichectrl_app_prod` sur dtpf_sylob_prod et lui
donne SELECT sur les six tables dont la fiche a besoin, rien d'autre.

Pourquoi un script plutot que psql (meme choix que FUSEAU) : le mot de passe du
compte de service est lu au Key Vault et passe directement au serveur. Il ne
transite ni par un fichier SQL, ni par un argument de ligne de commande
(visible dans la liste des processus), ni par la console.

Execute par le compte admin PostgreSQL (seul porteur de CREATEROLE), lui-meme
lu dans kv-platform-vault-prod. A lancer sous le compte Azure qui peut lire ces
deux coffres (voir deployer_infra.ps1), APRES accord ecrit d'Antho.

Idempotent, non destructif : aucun DROP, aucun REVOKE, aucune donnee touchee.

Usage : python deploy/webapp/appliquer_role_fichectrl.py [--creer-secrets] [--dry-run]

`--creer-secrets` genere le mot de passe (secrets.token_urlsafe) et l'ecrit au
Key Vault avec le login, s'ils n'existent pas encore. Il exige le droit
d'ecrire des secrets dans kv-dtpf-prod. Un secret existant n'est jamais
ecrase : une rotation se fait explicitement, pas par effet de bord.
"""

import argparse
import logging
import sys
from dataclasses import dataclass

logger = logging.getLogger("appliquer_role_fichectrl")


@dataclass(frozen=True)
class Cible:
    """Cibles et noms de secrets (aucune valeur secrete ici)."""

    coffre_app: str = "kv-dtpf-prod"
    coffre_admin: str = "kv-platform-vault-prod"
    secret_mot_de_passe: str = "psql-prod-fichectrl-app-password"
    secret_admin_login: str = "dtpf-psql-admin-username-prod"
    secret_admin_mot_de_passe: str = "dtpf-psql-admin-password-prod"
    hote: str = "psql-dtpf-psql-prod.postgres.database.azure.com"
    base: str = "dtpf_sylob_prod"
    role: str = "dtpf_fichectrl_app_prod"
    # MyReport (public) et suivi de conteneur FUSEAU (achat). Si l'ETL MyReport
    # supprime et recree une table, le GRANT disparait : la sonde /api/health le
    # signale, et ce script se rejoue sans risque.
    tables: tuple[str, ...] = (
        "public.articles3", "public.commandes_detaillees", "public.fournisseurs2",
        "public.tracabilite", "achat.ot_transport", "achat.ot_transport_bl",
    )


def _secret(coffre: str, nom: str) -> str:
    from azure.identity import DefaultAzureCredential
    from azure.keyvault.secrets import SecretClient
    valeur = SecretClient("https://%s.vault.azure.net/" % coffre,
                          DefaultAzureCredential()).get_secret(nom).value
    if not valeur:
        raise RuntimeError("Secret vide : %s/%s" % (coffre, nom))
    return valeur


def creer_secrets(cible: Cible, dry_run: bool) -> None:
    """Cree login et mot de passe du role au Key Vault s'ils sont absents."""
    import secrets
    from azure.core.exceptions import ResourceNotFoundError
    from azure.identity import DefaultAzureCredential
    from azure.keyvault.secrets import SecretClient
    kv = SecretClient("https://%s.vault.azure.net/" % cible.coffre_app, DefaultAzureCredential())
    valeurs = {cible.secret_mot_de_passe.replace("-password", "-login"): cible.role,
               cible.secret_mot_de_passe: secrets.token_urlsafe(32)}
    for nom, valeur in valeurs.items():
        try:
            kv.get_secret(nom)
            logger.info("[INFO] Secret %s deja present, conserve.", nom)
        except ResourceNotFoundError:
            if dry_run:
                logger.info("[INFO] Simulation : le secret %s serait cree.", nom)
                continue
            kv.set_secret(nom, valeur, content_type="text/plain",
                          tags={"projet": "fiche-controle", "usage": "role PostgreSQL lecture seule"})
            logger.info("[SUCCES] Secret %s cree (valeur non affichee).", nom)


def _moteur(cible: Cible) -> object:
    from sqlalchemy import create_engine
    from sqlalchemy.engine import URL
    url = URL.create("postgresql+psycopg2",
                     username=_secret(cible.coffre_admin, cible.secret_admin_login),
                     password=_secret(cible.coffre_admin, cible.secret_admin_mot_de_passe),
                     host=cible.hote, port=5432, database=cible.base,
                     query={"sslmode": "require"})
    return create_engine(url)


def appliquer(cible: Cible, dry_run: bool) -> None:
    """Cree le role, verrouille la lecture seule et pose les six GRANT."""
    from sqlalchemy import text
    try:
        mot_de_passe = _secret(cible.coffre_app, cible.secret_mot_de_passe)
    except Exception:
        if not dry_run:
            raise
        mot_de_passe = "simulation"  # secret pas encore cree, rien ne sera applique
    with _moteur(cible).begin() as cnx:
        existe = cnx.execute(text("select 1 from pg_roles where rolname = :r"),
                             {"r": cible.role}).scalar() is not None
        verbe = "ALTER" if existe else "CREATE"
        # PASSWORD n'accepte pas de parametre bind : quote_literal cote serveur.
        litteral = cnx.execute(text("select quote_literal(:m)"), {"m": mot_de_passe}).scalar()
        ordres = [
            "%s ROLE %s LOGIN PASSWORD %s CONNECTION LIMIT 5" % (verbe, cible.role, litteral),
            "ALTER ROLE %s SET default_transaction_read_only = on" % cible.role,
            "ALTER ROLE %s SET statement_timeout = '30s'" % cible.role,
            'GRANT CONNECT ON DATABASE "%s" TO %s' % (cible.base, cible.role),
            "GRANT USAGE ON SCHEMA public TO %s" % cible.role,
            "GRANT USAGE ON SCHEMA achat TO %s" % cible.role,
        ] + ["GRANT SELECT ON TABLE %s TO %s" % (t, cible.role) for t in cible.tables]
        for ordre in ordres:
            logger.info("[INFO] %s", ordre.replace(litteral, "'***'"))
            if not dry_run:
                cnx.execute(text(ordre))
        if dry_run:
            cnx.rollback()
            logger.info("[INFO] Simulation : aucune modification appliquee.")
            return
        _controler(cnx, cible)


def _controler(cnx: object, cible: Cible) -> None:
    """Verifie que le role a exactement SELECT sur les six tables, rien de plus."""
    from sqlalchemy import text
    droits = cnx.execute(text(
        "select table_schema || '.' || table_name, string_agg(privilege_type, ',') "
        "from information_schema.role_table_grants where grantee = :r group by 1"),
        {"r": cible.role}).all()
    lus = {table: d for table, d in droits}
    attendu = set(cible.tables)
    if set(lus) != attendu or any(d != "SELECT" for d in lus.values()):
        raise RuntimeError("Droits inattendus pour %s : %s" % (cible.role, lus))
    logger.info("[SUCCES] %s : SELECT sur %d tables, aucun autre droit.", cible.role, len(lus))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--creer-secrets", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("azure").setLevel(logging.WARNING)
    try:
        if args.creer_secrets:
            creer_secrets(Cible(), args.dry_run)
        appliquer(Cible(), args.dry_run)
    except Exception as e:
        logger.error("[ECHEC] %s", e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
