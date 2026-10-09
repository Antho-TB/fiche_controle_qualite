"""
[ARCHITECTURE] I/O & Référentiel Article (fiche_de_controle)

Stratégie, par ordre de confiance décroissant :
1. DWH `dtpf_sylob_prod` (`public.articles3`) = référentiel article de
   référence. 39 580 articles, 3 sociétés, et il porte les EAN14 carton
   (`sup_ean14_pcb`, `sup_ean14_spcb`), donc il couvre le scan unité ET carton.
2. `article.csv` local = repli hors ligne, 8874 lignes maintenues à la main.
   Il reste indispensable au poste réception si le DWH est injoignable.
3. API Sylob = enrichissement PO/Lot temps réel (`enrichir_depuis_sylob`).

Les responsabilités restent séparées pour qu'une source indisponible n'en
bloque aucune autre : le scan doit continuer à produire une fiche même sans
réseau, quitte à laisser des cases vides plutôt que fausses.
"""

import os
import sys
import logging
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


def get_base_path() -> str:
    """Retourne le chemin d'exécution réel (script ou .exe PyInstaller)."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


def _setup_logging() -> None:
    """Configure le logging fichier + console."""
    try:
        log_dir = os.path.join(get_base_path(), "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "data_processing.log")
        with open(log_file, 'a', encoding='utf-8'):
            pass
    except (PermissionError, OSError):
        import tempfile
        log_dir = os.path.join(tempfile.gettempdir(), "Scanner_Qualite_Logs")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "data_processing.log")

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler(),
        ],
    )
    for noisy in ("azure", "azure.core.pipeline.policies.http_logging_policy", "azure.identity"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


_setup_logging()

from src.sylob_api import SylobAPI  # noqa: E402 (après setup logging)
from src.code_resolver import (ResolutionCode, normaliser_code,  # noqa: E402
                               resoudre)
from src.dwh_repository import DWHRepository  # noqa: E402


class DataLoader:
    """Référentiel maître des articles : lookup CSV + enrichissement Sylob."""

    def __init__(self, csv_path: Optional[str] = None,
                 avec_dwh: bool = True) -> None:
        if csv_path is None:
            csv_path = os.path.join(get_base_path(), "0_Modele_Et_Donnees", "article.csv")
        self.csv_path: str = csv_path
        self.df: Optional[pd.DataFrame] = None
        self.sylob: SylobAPI = SylobAPI()
        self.dwh: Optional[DWHRepository] = DWHRepository() if avec_dwh else None
        self._load_data()

    # ------------------------------------------------------------------
    # Chargement CSV
    # ------------------------------------------------------------------

    def _load_data(self) -> None:
        """Charge le CSV de référence article en mémoire."""
        if not os.path.exists(self.csv_path):
            logger.warning(f"[CSV] Fichier introuvable : {self.csv_path}. Sylob seul actif.")
            return
        try:
            self.df = pd.read_csv(
                self.csv_path,
                sep=';',
                encoding='ISO-8859-1',
                dtype=str,
                header=0,
            )
            self.df.columns = [str(c).strip().lower() for c in self.df.columns]
            for col in self.df.columns:
                self.df[col] = self.df[col].astype(str).str.strip()
            logger.info(f"[CSV] {len(self.df)} articles chargés.")
        except Exception as e:
            logger.error(f"[CSV] Erreur lecture : {e}")

    def get_article_count(self) -> int:
        """Retourne le nombre d'articles chargés (0 si CSV absent)."""
        return len(self.df) if self.df is not None else 0

    # ------------------------------------------------------------------
    # Lookup article
    # ------------------------------------------------------------------

    def resoudre_code(self, code: str) -> ResolutionCode:
        """
        Resout un code scanne en article, avec tracabilite du type de code.

        Interroge ean, ean_pcb, ean_spcb et ref, puis convertit un EAN14 en
        EAN13 si besoin. Le match approximatif historique reste disponible mais
        est marque non fiable : l interface doit demander confirmation.

        Args:
            code: Code brut sorti de la douchette.

        Returns:
            ResolutionCode portant l article, le type de code et la fiabilite.

        Junior Tip : avant ce correctif, un code carton EAN14 tombait dans le
        match approximatif et remontait un article VOISIN dans 91 pour cent des
        cas, sans aucune alerte. La fiche de controle portait alors le mauvais
        article.
        """
        if self.dwh is not None and self.dwh.disponible:
            article_dwh = self.dwh.chercher_article(normaliser_code(code))
            if article_dwh is not None:
                return ResolutionCode(
                    trouve=True, type_code=article_dwh.type_code,
                    colonne="DWH", fiable=True,
                    article={
                        "ref": article_dwh.code_article,
                        "designation": article_dwh.designation,
                        "ean": article_dwh.ean13,
                        "ean_pcb": article_dwh.ean14_pcb,
                        "ean_spcb": article_dwh.ean14_spcb,
                        "id_article": article_dwh.id_article,
                        "societe": article_dwh.societe,
                        "source": "DWH (articles3)",
                        "po": "", "lot": "", "fournisseur": "",
                    },
                    message="Article identifie dans le DWH par %s."
                            % article_dwh.type_code)
        return resoudre(code, self.df)

    def chercher_article(self, code: str) -> Optional[dict]:
        """
        Recherche un article dans le referentiel local.

        Returns:
            Dict article enrichi des cles _resolution et _fiable, ou None.
        """
        resolution = self.resoudre_code(code)
        if not resolution.article:
            return None
        article = dict(resolution.article)
        article["_resolution"] = resolution.type_code
        article["_fiable"] = resolution.fiable
        article["_message_resolution"] = resolution.message
        article["po"] = article.get("po", "") or ""
        article["lot"] = article.get("lot", "") or ""
        if article["po"] == "nan":
            article["po"] = ""
        if article["lot"] == "nan":
            article["lot"] = ""
        return article

    # ------------------------------------------------------------------
    # Enrichissement DWH : commande d achat et lot
    # ------------------------------------------------------------------

    def enrichir_depuis_dwh(self, article: dict,
                            po_indice: str = "") -> dict:
        """
        Complete PO, lot et fournisseur depuis le DWH, sans jamais deviner.

        Args:
            article: Article deja resolu, portant `id_article` et `ref`.
            po_indice: Numero de commande lu dans la Packing List, utilise
                UNIQUEMENT pour departager les candidats du DWH.

        Returns:
            Dict avec les cles po, lot_sylob, fournisseur, candidats_po,
            lots_connus et ambigu. `ambigu` a True signifie qu il faut
            demander a l operateur, jamais choisir a sa place.

        Junior Tip : quand plusieurs commandes portent le meme article, prendre
        la plus recente parait pratique mais produit une tracabilite qualite
        fausse une fois sur deux. On preleve l indice du PDF, et a defaut on
        rend la main a l operateur.
        """
        vide = {"po": "", "lot_sylob": "", "fournisseur": "",
                "candidats_po": [], "lots_connus": [], "ambigu": False}
        if self.dwh is None or not self.dwh.disponible:
            return vide
        id_article = article.get("id_article", "")
        if not id_article:
            return vide

        societe = article.get("societe", "")
        commandes = self.dwh.commandes_pour_article(id_article, societe=societe)
        lots = self.dwh.lots_pour_article(article.get("ref", ""), societe=societe)
        vide["lots_connus"] = lots
        vide["lot_sylob"] = lots[0] if lots else ""
        if not commandes:
            logger.info("[INFO] Aucune commande d achat au DWH pour %s.",
                        article.get("ref", ""))
            return vide

        vide["candidats_po"] = commandes
        vide["fournisseur"] = commandes[0].fournisseur

        if po_indice:
            correspondances = [c for c in commandes if c.numero == po_indice]
            if len(correspondances) == 1:
                vide["po"] = correspondances[0].numero
                vide["fournisseur"] = correspondances[0].fournisseur
                logger.info("[SUCCES] PO %s confirme par le DWH et la Packing "
                            "List.", vide["po"])
                return vide
            logger.warning("[ATTENTION] PO %s lu dans la Packing List absent "
                           "des commandes DWH de cet article.", po_indice)

        en_cours = [c for c in commandes
                    if c.etat_reception.lower().startswith(("non commenc",
                                                            "commenc"))]
        if len(en_cours) == 1:
            vide["po"] = en_cours[0].numero
            vide["fournisseur"] = en_cours[0].fournisseur
            logger.info("[SUCCES] PO %s deduit : seule commande en cours de "
                        "reception.", vide["po"])
            return vide

        vide["ambigu"] = True
        logger.warning("[ATTENTION] %d commande(s) candidate(s) pour %s, "
                       "arbitrage operateur requis.",
                       len(commandes), article.get("ref", ""))
        return vide

    # ------------------------------------------------------------------
    # Enrichissement Sylob
    # ------------------------------------------------------------------

    def enrichir_depuis_sylob(self, ean: str, ref: str = "") -> Optional[dict]:
        """
        Interroge Sylob pour obtenir PO/Lot à partir d'un EAN ou référence.
        Découplé du lookup article pour ne pas bloquer les nouveaux produits.

        Args:
            ean: Code EAN scanné.
            ref: Référence interne article (optionnel).

        Returns:
            Dict {"po": ..., "lot": ...} ou None si aucun résultat.
        """
        try:
            result = self.sylob.chercher_lot_par_po(po="", art=ref, lot="", ean=ean)
            if result:
                logger.info(f"[Sylob] PO={result.get('po')} LOT={result.get('lot')} (EAN={ean})")
            return result
        except Exception as e:
            logger.error(f"[Sylob] Erreur enrichissement : {e}")
            return None


if __name__ == "__main__":
    loader = DataLoader()
    print(loader.chercher_article("10120098"))
