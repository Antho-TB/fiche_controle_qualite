"""
[DWH] Acces lecture seule au DWH Azure pour la fiche de controle.

Strategie :
- Le referentiel article, les commandes d achat, les lots et le suivi de
  conteneur existent deja dans `dtpf_sylob_prod`. Ils sont donc LUS, jamais
  re-saisis ni devines a partir d un PDF fournisseur (hierarchie de source de
  verite du socle data commun).
- Tables utilisees, toutes dans le schema `public`, sortie de l ETL MyReport :
    * `articles3` : referentiel article (39 580 lignes, 3 societes). Porte
      code_gtin_13, sup_ean14_pcb, sup_ean14_spcb et sup_ean14_palette, donc
      couvre le scan unite ET le scan carton.
    * `commandes_detaillees` (SANS suffixe) : lignes de commande d ACHAT
      (numero au format 00169477, etat de reception, ETD confirme). C est la
      seule version que MyReport alimente encore : `commandes_detaillees27`
      est figee depuis le 04/08/2026 (derniere commande au 30/06), alors que
      celle-ci porte 5 440 lignes creees depuis (mesure du 09/10/2026). Les
      suffixes numerotes sont des versions abandonnees de MyReport : verifier
      la fraicheur (pg_stat_user_tables) avant de changer de table.
    * `tracabilite` : numero de lot par article et par livraison.
    * `achat.ot_transport` / `ot_transport_bl` : suivi maritime FUSEAU,
      conteneur vers BL, ETA, transitaire.
- Gouvernance : ce module ne fait que des SELECT. Il ne doit JAMAIS ecrire, et
  ne doit pas devenir proprietaire d une table du schema `achat`, propriete du
  domaine FUSEAU. La lecture cross-schema reste limitee au suivi de conteneur.
- Connexion via `URL.create()` et secrets Key Vault, jamais de f-string ni de
  credential en dur. Timeout court : au poste reception, une base injoignable
  doit degrader l application en quelques secondes, pas la figer.

Junior Tip : la colonne `base_id_article` vaut "SE|<uuid>", "GDD|<uuid>" ou
"CIE|<uuid>". Sans filtre de societe, un meme EAN13 remonte deux articles (par
exemple Comp0165 chez SE et Comp0522 chez GDD) et la fiche peut porter la
mauvaise reference. La reception import se fait chez SE.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from src.config import Config

logger = logging.getLogger(__name__)

# Le controle reception import porte sur PLUSIEURS societes : les articles finis
# sont majoritairement chez SE, mais les kits et cales carton sont chez GDD (cas
# mesure sur PL-SZSE2601806, 6 articles introuvables tant que le filtre etait
# fige sur SE). L ordre ci-dessous n exclut rien, il sert seulement a departager
# un code present dans plusieurs societes.
SOCIETES_PREFEREES: tuple[str, ...] = ("SE", "GDD", "CIE")
_DELAI_CONNEXION = 8  # secondes, au dela le poste reception travaille sans DWH


@dataclass
class ArticleDWH:
    """Article du referentiel DWH, tel qu il alimente la fiche de controle."""

    id_article: str
    code_article: str
    designation: str
    ean13: str
    ean14_pcb: str
    ean14_spcb: str
    societe: str
    type_code: str  # colonne qui a produit la correspondance


@dataclass
class CommandeDWH:
    """Ligne de commande d achat candidate pour un article recu."""

    numero: str
    fournisseur: str
    designation_ligne: str
    quantite: float
    etat_reception: str
    ouverte: str
    etd_confirme: Optional[object]


@dataclass
class ContexteConteneur:
    """Suivi maritime d un conteneur, deduit du nom de la Packing List."""

    n_conteneur: str
    n_bl: str
    fournisseur: str = ""
    eta: Optional[object] = None
    date_livraison: Optional[object] = None
    transitaire: str = ""
    commandes: list[str] = field(default_factory=list)


class DWHRepository:
    """Depot lecture seule sur dtpf_sylob_prod, avec degradation explicite."""

    def __init__(self, societes: tuple[str, ...] = SOCIETES_PREFEREES) -> None:
        self.societes: tuple[str, ...] = societes
        self._moteur = None
        self.disponible: bool = False
        self.motif_indisponible: str = ""
        self._connecter()

    # ------------------------------------------------------------------
    # Connexion
    # ------------------------------------------------------------------

    def _connecter(self) -> None:
        """Ouvre le moteur SQLAlchemy et verifie la base par un SELECT 1."""
        try:
            from sqlalchemy import create_engine, text
            from sqlalchemy.engine import URL
        except ImportError as e:
            self.motif_indisponible = "packages SQLAlchemy absents (%s)" % e
            logger.error("[ECHEC] DWH inutilisable : %s", self.motif_indisponible)
            return

        identifiants = self._lire_identifiants()
        if not identifiants:
            self.motif_indisponible = "identifiants Key Vault illisibles"
            logger.warning("[ATTENTION] DWH indisponible : %s",
                           self.motif_indisponible)
            return

        login, mot_de_passe = identifiants
        url = URL.create(
            drivername="postgresql+psycopg2",
            username=login,
            password=mot_de_passe,
            host=Config.PG_HOTE,
            port=5432,
            database=Config.PG_BASE,
            query={"sslmode": "require",
                   "connect_timeout": str(_DELAI_CONNEXION)},
        )
        try:
            self._moteur = create_engine(url, pool_pre_ping=True)
            with self._moteur.connect() as cnx:
                cnx.execute(text("select 1"))
        except Exception as e:
            self.motif_indisponible = "connexion refusee (%s)" % type(e).__name__
            logger.warning("[ATTENTION] DWH injoignable, mode degrade : %s", e)
            self._moteur = None
            return
        self.disponible = True
        logger.info("[SUCCES] DWH %s joignable (societes %s).",
                    Config.PG_BASE, ", ".join(self.societes))

    def _lire_identifiants(self) -> Optional[tuple[str, str]]:
        """Lit login et mot de passe PostgreSQL dans Key Vault, sans les journaliser."""
        try:
            from azure.keyvault.secrets import SecretClient
            from src.azure_auth import obtenir_credential
            credential = obtenir_credential()
            if credential is None:
                return None
            kv = SecretClient(vault_url=Config.KEY_VAULT_URL, credential=credential)
            return (kv.get_secret(Config.PG_SECRET_LOGIN).value,
                    kv.get_secret(Config.PG_SECRET_PASSWORD).value)
        except Exception as e:
            logger.warning("[ATTENTION] Key Vault DWH illisible : %s", e)
            return None

    def _lire(self, requete: str, parametres: dict) -> list[dict]:
        """Execute un SELECT et rend des dictionnaires, [] si DWH indisponible."""
        if not self.disponible or self._moteur is None:
            return []
        from sqlalchemy import text
        try:
            with self._moteur.connect() as cnx:
                return [dict(l) for l in
                        cnx.execute(text(requete), parametres).mappings().all()]
        except Exception as e:
            logger.error("[ECHEC] Requete DWH : %s", e)
            return []

    # ------------------------------------------------------------------
    # Referentiel article
    # ------------------------------------------------------------------

    _COLONNES_CODE: tuple[tuple[str, str], ...] = (
        ("code_gtin_13", "EAN13"),
        ("sup_ean14_pcb", "EAN14_PCB"),
        ("sup_ean14_spcb", "EAN14_SPCB"),
        ("sup_ean14_palette", "EAN14_PALETTE"),
        ("code_article", "REF"),
    )

    def chercher_article(self, code: str) -> Optional[ArticleDWH]:
        """
        Resout un code scanne sur le referentiel DWH, societe par societe.

        Args:
            code: Code scanne, deja normalise (EAN13, EAN14 ou reference).

        Returns:
            ArticleDWH, ou None si aucun article ne correspond.
        """
        for colonne, type_code in self._COLONNES_CODE:
            lignes = self._lire(
                """
                select id_article, code_article, designation,
                       coalesce(code_gtin_13, '') as ean13,
                       coalesce(sup_ean14_pcb, '') as ean14_pcb,
                       coalesce(sup_ean14_spcb, '') as ean14_spcb,
                       split_part(base_id_article, '|', 1) as societe
                from public.articles3
                where %s = :code
                limit 5
                """ % colonne,
                {"code": code},
            )
            if not lignes:
                continue
            ligne = self._departager_societes(lignes, colonne, code)
            logger.info("[SUCCES] Article DWH %s (%s) resolu par %s.",
                        ligne["code_article"], ligne["societe"], colonne)
            return ArticleDWH(type_code=type_code, **ligne)
        return None

    def _departager_societes(self, lignes: list[dict], colonne: str,
                             code: str) -> dict:
        """
        Choisit une ligne quand un meme code existe dans plusieurs societes.

        L ordre de preference sert uniquement a trancher, il n exclut aucune
        societe : un code present seulement chez GDD est retenu tel quel. Toute
        ambiguite est journalisee, jamais masquee.
        """
        if len(lignes) == 1:
            return lignes[0]
        societes = sorted({l["societe"] for l in lignes})
        logger.warning("[ATTENTION] %s=%s existe chez %s. Preference appliquee : %s.",
                       colonne, code, ", ".join(societes),
                       ", ".join(self.societes))
        for societe in self.societes:
            for ligne in lignes:
                if ligne["societe"] == societe:
                    return ligne
        return lignes[0]

    # ------------------------------------------------------------------
    # Commandes d achat et lots
    # ------------------------------------------------------------------

    def commandes_pour_article(self, id_article: str, societe: str = "",
                               limite: int = 8) -> list[CommandeDWH]:
        """
        Rend les commandes d achat portant cet article, les plus recentes d abord.

        Les commandes sont filtrees sur la societe et triees par date de
        creation decroissante. L etat de reception permet a l interface de
        distinguer une commande deja soldee d une commande attendue.
        """
        lignes = self._lire(
            """
            select distinct
                   k.commande_numero_de_la_commande as numero,
                   coalesce(f.raison_sociale, f.code_fournisseur, '') as fournisseur,
                   coalesce(k.ligne_designation, '') as designation_ligne,
                   coalesce(k.ligne_quantite, 0) as quantite,
                   coalesce(k.commande_etat_de_reception, '') as etat_reception,
                   coalesce(k.commande_commande_ouverte, '') as ouverte,
                   k.commande_sup_etd_confirme as etd_confirme,
                   k.commande_creee_le
            from public.commandes_detaillees k
            left join public.fournisseurs2 f
                   on f.id_fournisseur = k.frn_id_fournisseur
            where k.article_id_article = :id_article
              and (:societe = '' or
                   split_part(k.base_n_commande_n_ligne, '|', 1) = :societe)
            order by k.commande_creee_le desc nulls last
            limit :limite
            """,
            {"id_article": id_article, "societe": societe, "limite": limite},
        )
        return [CommandeDWH(**{k: v for k, v in l.items()
                               if k != "commande_creee_le"}) for l in lignes]

    def lots_pour_article(self, code_article: str, societe: str = "",
                          limite: int = 8) -> list[str]:
        """Rend les numeros de lot connus pour cet article, les plus recents d abord."""
        lignes = self._lire(
            """
            select numero_lot, max(livraison) as derniere_livraison
            from public.tracabilite
            where article_code = :code_article
              and (:societe = '' or database_name = :societe)
              and numero_lot is not null and numero_lot <> ''
            group by numero_lot
            order by derniere_livraison desc nulls last
            limit :limite
            """,
            {"code_article": code_article, "societe": societe,
             "limite": limite},
        )
        return [l["numero_lot"] for l in lignes]

    # ------------------------------------------------------------------
    # Suivi de conteneur (schema achat, propriete FUSEAU, LECTURE seule)
    # ------------------------------------------------------------------

    def contexte_conteneur(self, n_bl: str,
                           n_conteneur: str) -> Optional[ContexteConteneur]:
        """
        Rend le suivi maritime d un conteneur en reception.

        Args:
            n_bl: Numero de connaissement, par exemple SZSE2602436.
            n_conteneur: Numero de conteneur, par exemple TLLU4162583.

        La colonne fournisseur de `ot_transport_bl` est renseignee de facon
        partielle : le nom du fournisseur doit venir de la commande d achat, pas
        du suivi transport.

        Returns:
            ContexteConteneur, ou None si le conteneur est inconnu du suivi.

        Junior Tip : ces deux numeros sont deja dans le NOM du fichier de la
        Packing List (PL-<BL>-<CONTENEUR>.pdf). Le perimetre de la reception se
        deduit donc sans ouvrir le PDF, ce qui fonctionne meme sur un scan.
        """
        # Le numero de conteneur est la cle discriminante. Un ciblage
        # "conteneur OU bl" avec un tri sur charge_le, identique pour toutes
        # les lignes issues de la reprise, rendait une ligne au hasard : deux
        # Packing Lists differentes ressortaient avec la meme ETA.
        requete = """
            select t.n_conteneur, t.n_bl, coalesce(b.fournisseur, '') as fournisseur,
                   t.eta, t.date_livraison, coalesce(t.transitaire, '') as transitaire
            from achat.ot_transport t
            left join achat.ot_transport_bl b
                   on b.n_conteneur = t.n_conteneur
            where t.%s = :valeur
            order by t.eta desc nulls last, t.charge_le desc nulls last
            limit 2
            """
        for colonne, valeur, libelle in (("n_conteneur", n_conteneur, "conteneur"),
                                         ("n_bl", n_bl, "BL")):
            if not valeur:
                continue
            lignes = self._lire(requete % colonne, {"valeur": valeur})
            if not lignes:
                continue
            if len(lignes) > 1:
                logger.warning("[ATTENTION] %d suivis pour le %s %s, le plus "
                               "recent est retenu.", len(lignes), libelle, valeur)
            if colonne == "n_bl":
                logger.warning("[ATTENTION] Conteneur %s absent du suivi, "
                               "rattachement par le BL %s seulement.",
                               n_conteneur, n_bl)
            return ContexteConteneur(**lignes[0])
        logger.info("[INFO] Conteneur %s et BL %s inconnus du suivi transport.",
                    n_conteneur, n_bl)
        return None


def analyser_nom_packing_list(nom_fichier: str) -> tuple[str, str]:
    """
    Extrait le numero de BL et le numero de conteneur du nom d une Packing List.

    Convention observee sur les archives : PL-<BL>-<CONTENEUR>.pdf, parfois avec
    deux conteneurs separes par un souligne, ou un suffixe entre parentheses.

    Args:
        nom_fichier: Nom du fichier, avec ou sans chemin.

    Returns:
        Tuple (n_bl, n_conteneur), chaines vides si le nom ne suit pas la
        convention.
    """
    import os
    import re

    base = os.path.splitext(os.path.basename(nom_fichier))[0]
    base = re.sub(r"\s*\(\d+\)$", "", base).strip()
    correspondance = re.match(r"(?i)^PL-([A-Z0-9]+)-([A-Z]{4}\d{7})", base)
    if not correspondance:
        return "", ""
    return correspondance.group(1).upper(), correspondance.group(2).upper()
