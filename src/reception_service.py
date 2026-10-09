"""
[METIER] Service de reception : du code scanne a la fiche de controle.

Strategie :
- Reprend la logique de la boucle CLI (scanner_app) sans aucun input() : le
  service PROPOSE, l'operateur TRANCHE dans l'interface web, puis le service
  GENERE. Rien n'est devine : une case vide vaut mieux qu'une case fausse.
- Ordre des sources (revu le 09/10/2026 apres essai sur donnees reelles) :
    1. Packing List : simple indice (PO, lot fournisseur), jamais une verite ;
    2. DWH : commandes candidates et fournisseur. Une commande existe des
       semaines avant sa reception, le decalage J-1 ne la concerne pas ;
    3. API Sylob : LOT du PO retenu, en temps reel (la reception du jour y
       est deja, pas encore au DWH) ;
    4. referentiel CSV : dernier repli hors ligne.
- La generation re-resout l'article a partir du code : le navigateur ne peut
  pas imposer un article different de celui que le code designe.

Junior Tip : interroger RECEPTIONAPI par le seul EAN avec `limite=1` rend UNE
reception quelconque de l'article. Mesure du 09/10 sur l'article 10120214 :
PO 00147459, reception ancienne et soldee, alors que la commande en cours est
00184449. Sylob est donc interroge par PO (CMD + ART), une fois le PO connu, et
jamais pour choisir le PO a la place du DWH.
"""

import logging
import os
import shutil
import tempfile
import threading
from dataclasses import asdict, dataclass, field
from typing import Optional

from src.data_loader import DataLoader
from src.depot_fichiers import DepotFichiers, nom_sur
from src.excel_handler import ExcelHandler

logger = logging.getLogger(__name__)


@dataclass
class Proposition:
    """Ce que le service propose pour un code scanne, avant arbitrage."""

    code: str
    trouve: bool = False
    article: dict = field(default_factory=dict)
    resolution: str = ""
    fiable: bool = True
    message: str = ""
    po: str = ""
    lot_sylob: str = ""
    lot_fournisseur: str = ""
    fournisseur: str = ""
    po_ambigu: bool = False
    candidats_po: list[dict] = field(default_factory=list)
    lots_connus: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    alertes: list[str] = field(default_factory=list)

    def en_dict(self) -> dict:
        return asdict(self)


class ArticleNonConfirme(Exception):
    """Correspondance article non fiable que l'operateur n'a pas validee."""


class ServiceReception:
    """Orchestration lecture des sources, proposition et generation de fiche."""

    def __init__(self, loader: DataLoader, handler: ExcelHandler,
                 depot: DepotFichiers) -> None:
        self.loader = loader
        self.handler = handler
        self.depot = depot
        self._verrou = threading.Lock()
        self._pdf = None
        self._cache_pl: Optional[str] = None
        self.recharger_packing_lists()

    # ------------------------------------------------------------------
    # Packing Lists
    # ------------------------------------------------------------------

    def recharger_packing_lists(self) -> None:
        """
        Recopie les Packing Lists du depot dans un cache local et les indexe.

        PDFExtractor lit un dossier : on lui donne une copie locale plutot que
        de le faire lire en SMB fichier par fichier, ce qui garde le parsing
        identique entre le poste et la Web App.
        """
        from src.pdf_extractor import PDFExtractor
        with self._verrou:
            cache = tempfile.mkdtemp(prefix="fichectrl_pl_")
            try:
                for nom in self.depot.lister_packing_lists():
                    with open(os.path.join(cache, nom_sur(nom)), "wb") as flux:
                        flux.write(self.depot.lire_packing_list(nom))
            except Exception as e:
                logger.error("[ECHEC] Lecture des Packing Lists sur %s : %s",
                             self.depot.description, e)
            ancien, self._cache_pl = self._cache_pl, cache
            self._pdf = PDFExtractor(pdf_dir=cache)
        if ancien:
            shutil.rmtree(ancien, ignore_errors=True)

    def ajouter_packing_list(self, nom: str, contenu: bytes) -> str:
        """Depose une Packing List envoyee depuis le navigateur puis reindexe."""
        if not nom.lower().endswith(".pdf"):
            raise ValueError("Seuls les fichiers PDF sont acceptes.")
        chemin = self.depot.deposer_packing_list(nom, contenu)
        self.recharger_packing_lists()
        return chemin

    def rapports_packing_lists(self) -> list[dict]:
        return list(self._pdf.rapports) if self._pdf else []

    # ------------------------------------------------------------------
    # Proposition
    # ------------------------------------------------------------------

    def analyser(self, code: str) -> Proposition:
        """Resout le code et propose PO, lots et fournisseur, sans trancher."""
        prop = Proposition(code=code)
        article = self.loader.chercher_article(code)
        if not article:
            return self._article_inconnu(prop)
        prop.trouve = True
        prop.article = _article_public(article)
        prop.resolution = article.get("_resolution", "")
        prop.fiable = bool(article.get("_fiable", True))
        prop.message = article.get("_message_resolution", "")
        self._indice_packing_list(prop, article)
        self._completer_par_dwh(prop, article)
        self._completer_par_sylob(prop, article)
        self._completer_par_csv(prop, article)
        if not prop.po and not prop.lot_sylob and not prop.po_ambigu:
            prop.alertes.append("Aucun PO ni lot identifie : cases a completer a la main.")
        return prop

    def _article_inconnu(self, prop: Proposition) -> Proposition:
        """Code absent du referentiel : derniere chance par l'API Sylob."""
        resultat = self.loader.enrichir_depuis_sylob(ean=prop.code)
        if resultat and (resultat.get("po") or resultat.get("lot")):
            prop.trouve = True
            prop.fiable = False
            prop.message = ("Article absent du referentiel, connu de Sylob par "
                            "son EAN (nouveau produit). A confirmer.")
            prop.article = {"ref": prop.code, "designation": "Article EAN %s" % prop.code,
                            "ean": prop.code, "source": "Sylob (EAN)"}
            prop.po, prop.lot_sylob = resultat.get("po", ""), resultat.get("lot", "")
            prop.sources.append("Sylob : PO %s, lot %s" % (prop.po or "-", prop.lot_sylob or "-"))
            return prop
        prop.message = "Code inconnu du referentiel et de Sylob."
        return prop

    def _indice_packing_list(self, prop: Proposition, article: dict) -> None:
        if self._pdf is None:
            return
        infos = self._pdf.chercher_infos_pdf(code_article=prop.code,
                                             ref_article=article.get("ref", ""))
        if not infos:
            return
        premier = infos[0]
        prop.lot_fournisseur = premier.get("lot", "")
        prop.fournisseur = premier.get("fournisseur", "")
        if premier.get("po_ambigu"):
            prop.alertes.append("Packing List multi-commandes : "
                                + ", ".join(premier.get("po_candidats", [])))
        elif premier.get("po"):
            prop.sources.append("Packing List : PO %s (indice)" % premier["po"])
            article["_po_indice"] = premier["po"]

    def _completer_par_dwh(self, prop: Proposition, article: dict) -> None:
        resultat = self.loader.enrichir_depuis_dwh(
            article, po_indice=article.get("_po_indice", ""))
        candidats = resultat["candidats_po"]
        prop.candidats_po = [{"numero": c.numero, "fournisseur": c.fournisseur,
                              "quantite": c.quantite, "etat_reception": c.etat_reception}
                             for c in candidats]
        prop.lots_connus = resultat["lots_connus"]
        if resultat["po"]:
            prop.po = resultat["po"]
            prop.fournisseur = resultat["fournisseur"] or prop.fournisseur
            prop.sources.append("DWH : PO %s" % prop.po)
        elif resultat["ambigu"]:
            prop.po_ambigu = True
        if resultat["lot_sylob"]:
            prop.lot_sylob = resultat["lot_sylob"]
            prop.sources.append("DWH : lot %s (dernier connu, J-1)" % prop.lot_sylob)

    def _completer_par_sylob(self, prop: Proposition, article: dict) -> None:
        """
        Lot temps reel du PO retenu. Sans aucun candidat au DWH, dernier recours
        par EAN, signale comme a verifier.
        """
        if prop.po:
            lot = self.lot_temps_reel(prop.po, article.get("ref", ""))
            if lot:
                prop.lot_sylob = lot
                prop.sources.append("Sylob (temps reel) : lot %s pour le PO %s"
                                    % (lot, prop.po))
            return
        if prop.po_ambigu or prop.candidats_po:
            return
        resultat = self.loader.enrichir_depuis_sylob(ean=prop.code, ref=article.get("ref", ""))
        if resultat and resultat.get("po"):
            prop.po = resultat["po"]
            prop.lot_sylob = resultat.get("lot", "") or prop.lot_sylob
            prop.sources.append("Sylob par EAN : PO %s, lot %s"
                                % (prop.po, prop.lot_sylob or "-"))
            prop.alertes.append("PO %s trouve par Sylob mais inconnu du DWH : "
                                "reception possiblement ancienne, a verifier." % prop.po)

    def lot_temps_reel(self, po: str, ref: str) -> str:
        """Lot Sylob de la reception d'un PO precis, chaine vide si inconnu."""
        from src.config import Config
        if not (Config.SYLOB_ACTIVE and po):
            return ""
        resultat = self.loader.sylob.chercher_lot_par_po(po=po, art=ref)
        return (resultat or {}).get("lot", "")

    def _completer_par_csv(self, prop: Proposition, article: dict) -> None:
        for attribut, cle in (("po", "po"), ("lot_sylob", "lot"),
                              ("fournisseur", "fournisseur")):
            valeur = str(article.get(cle, "")).replace("nan", "").strip()
            if valeur and not getattr(prop, attribut):
                setattr(prop, attribut, valeur)
                prop.sources.append("Referentiel CSV : %s %s" % (cle, valeur))

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    def generer(self, code: str, choix: dict, operateur: str) -> tuple[str, bytes, str]:
        """
        Genere la fiche avec les valeurs arbitrees par l'operateur et la depose.

        Args:
            code: Code scanne, re-resolu ici.
            choix: po, lot_sylob, lot_fournisseur, fournisseur, confirme.
            operateur: Identite Entra (ou locale) de l'operateur.

        Returns:
            Tuple (nom du fichier, contenu xlsx, emplacement de depot).

        Raises:
            LookupError: code inconnu.
            ArticleNonConfirme: correspondance non fiable non confirmee.
        """
        prop = self.analyser(code)
        if not prop.trouve:
            raise LookupError(prop.message or "Code inconnu.")
        if not prop.fiable and not choix.get("confirme"):
            raise ArticleNonConfirme(prop.message)
        info = {**prop.article,
                "po": _texte(choix.get("po")), "lot": _texte(choix.get("lot_sylob")),
                "lot_fournisseur": _texte(choix.get("lot_fournisseur")),
                "fournisseur": _texte(choix.get("fournisseur"))}
        nom, contenu = self.handler.construire_fiche(info, operateur=operateur)
        emplacement = self.depot.deposer_fiche(nom, contenu)
        logger.info("[SUCCES] Fiche %s generee par %s (article %s, PO %s, lot %s).",
                    nom, operateur, info.get("ref"), info["po"] or "-", info["lot"] or "-")
        return nom, contenu, emplacement


def _article_public(article: dict) -> dict:
    """Ne garde que les champs utiles a la fiche, sans les cles techniques."""
    cles = ("ref", "designation", "ean", "ean_pcb", "ean_spcb", "ho",
            "id_article", "societe", "source")
    return {c: _texte(article.get(c)) for c in cles if _texte(article.get(c))}


def _texte(valeur: object) -> str:
    texte = str(valeur or "").strip()
    return "" if texte.lower() == "nan" else texte
