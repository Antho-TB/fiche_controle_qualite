"""
[WEB] Application web du controle reception (FastAPI + une page HTML).

Strategie :
- Remplace la boucle console de scanner_app pour la Web App Azure, avec le meme
  coeur metier (ServiceReception). L'executable reste utilisable tel quel.
- Une page unique (src/static/index.html) : un champ qui recoit la douchette,
  la proposition, les arbitrages, puis la fiche en telechargement. Le champ de
  scan reprend le focus apres chaque action : l'operateur enchaine les cartons
  sans toucher la souris (raison du choix HTML plutot que Streamlit).
- Identite : en-tete X-MS-CLIENT-PRINCIPAL-NAME pose par Easy Auth. Hors Azure
  (poste de developpement), Config.OPERATEUR_LOCAL.
- /api/health reste anonyme (exclu d'Easy Auth) et ne renvoie que des etats,
  aucune donnee metier.

Lancement local :
    python -m uvicorn src.web_app:app --port 8000
En Azure : gunicorn src.web_app:app --worker-class uvicorn.workers.UvicornWorker

Junior Tip : le service est cree au demarrage (lifespan), pas a l'import. Un
import qui ouvre une connexion PostgreSQL et lit Key Vault rend le module
intestable et fait echouer le demarrage pour une simple erreur de reseau.
"""

import logging
import os
from contextlib import asynccontextmanager
from typing import Optional
from urllib.parse import quote

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.config import Config
from src.depot_fichiers import TAILLE_MAX_PL

logger = logging.getLogger(__name__)

_DOSSIER_STATIQUE = os.path.join(os.path.dirname(__file__), "static")
# Tables lues par l'application : la sonde verifie que le role PostgreSQL y a
# toujours acces (un DROP/CREATE de MyReport fait disparaitre les GRANT).
TABLES_SONDEES: tuple[str, ...] = (
    "public.articles3", "public.commandes_detaillees", "public.fournisseurs2",
    "public.tracabilite", "achat.ot_transport", "achat.ot_transport_bl",
)


class ChoixFiche(BaseModel):
    """Valeurs arbitrees par l'operateur, renvoyees pour generer la fiche."""

    code: str = Field(min_length=1, max_length=64)
    po: str = Field(default="", max_length=32)
    lot_sylob: str = Field(default="", max_length=64)
    lot_fournisseur: str = Field(default="", max_length=64)
    fournisseur: str = Field(default="", max_length=120)
    confirme: bool = False


class Scan(BaseModel):
    code: str = Field(min_length=1, max_length=64)


def creer_service() -> object:
    """Assemble le service metier a partir de la configuration."""
    from src.data_loader import DataLoader
    from src.depot_fichiers import creer_depot
    from src.excel_handler import ExcelHandler
    from src.reception_service import ServiceReception
    return ServiceReception(DataLoader(), ExcelHandler(), creer_depot())


@asynccontextmanager
async def _cycle_de_vie(application: FastAPI):
    if getattr(application.state, "service", None) is None:
        application.state.service = creer_service()
    yield


app = FastAPI(title="Fiche de controle reception", lifespan=_cycle_de_vie,
              docs_url=None, redoc_url=None, openapi_url=None)
# Logo et favicon du design system TB (copies des assets officiels, jamais
# redessines ni recolores).
app.mount("/static", StaticFiles(directory=_DOSSIER_STATIQUE), name="static")


def _service(request: Request) -> object:
    service = getattr(request.app.state, "service", None)
    if service is None:
        raise HTTPException(503, "Service en cours de demarrage.")
    return service


def operateur(request: Request) -> str:
    """Identite de l'operateur : Easy Auth en Azure, valeur locale sinon."""
    return (request.headers.get("X-MS-CLIENT-PRINCIPAL-NAME", "").strip()
            or Config.OPERATEUR_LOCAL)


# ----------------------------------------------------------------------
# Page et etat
# ----------------------------------------------------------------------

@app.get("/", include_in_schema=False)
def page() -> FileResponse:
    return FileResponse(os.path.join(_DOSSIER_STATIQUE, "index.html"))


@app.get("/api/etat")
def etat(request: Request) -> dict:
    """Etat des sources, affiche en tete de page (ex status board console)."""
    service = _service(request)
    depot_ok, depot_detail = service.depot.verifier()
    dwh = service.loader.dwh
    return {
        "operateur": operateur(request),
        "sylob": Config.SYLOB_ACTIVE and service.loader.sylob.is_healthy(),
        "dwh": bool(dwh and dwh.disponible),
        "dwh_detail": "" if dwh and dwh.disponible else getattr(dwh, "motif_indisponible", ""),
        "depot": depot_ok,
        "depot_detail": depot_detail,
        "packing_lists": service.rapports_packing_lists(),
    }


@app.get("/api/health")
def sante(request: Request) -> JSONResponse:
    """Sonde App Service : 200 si la base et chaque table utile repondent."""
    service = getattr(request.app.state, "service", None)
    dwh = service.loader.dwh if service else None
    if dwh is None or not dwh.disponible:
        return JSONResponse({"statut": "degrade", "dwh": False}, status_code=503)
    tables = {table: _table_lisible(dwh, table) for table in TABLES_SONDEES}
    code = 200 if all(tables.values()) else 503
    return JSONResponse({"statut": "ok" if code == 200 else "degrade",
                         "dwh": True, "tables": tables}, status_code=code)


def _table_lisible(dwh: object, table: str) -> bool:
    try:
        from sqlalchemy import text
        with dwh._moteur.connect() as cnx:
            cnx.execute(text("select 1 from %s limit 1" % table))
        return True
    except Exception as e:
        logger.error("[ECHEC] Table %s illisible : %s", table, e)
        return False


# ----------------------------------------------------------------------
# Scan et fiche
# ----------------------------------------------------------------------

@app.post("/api/scan")
def scanner(scan: Scan, request: Request) -> dict:
    """Analyse un code scanne et renvoie la proposition, sans rien ecrire."""
    code = scan.code.strip()
    proposition = _service(request).analyser(code)
    logger.info("[INFO] Scan %s par %s : %s.", code, operateur(request),
                "trouve" if proposition.trouve else "inconnu")
    return proposition.en_dict()


@app.post("/api/fiches")
def generer_fiche(choix: ChoixFiche, request: Request) -> Response:
    """Genere la fiche, la depose sur le partage et la renvoie au navigateur."""
    from src.reception_service import ArticleNonConfirme
    try:
        nom, contenu, emplacement = _service(request).generer(
            choix.code.strip(), choix.model_dump(), operateur(request))
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ArticleNonConfirme as e:
        raise HTTPException(409, "Article a confirmer : %s" % e)
    except Exception as e:
        logger.error("[ECHEC] Generation ou depot de la fiche : %s", e, exc_info=True)
        raise HTTPException(500, "Fiche non deposee : %s" % type(e).__name__)
    return Response(
        content=contenu,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename*=UTF-8''%s" % quote(nom),
                 "X-Fiche-Nom": quote(nom),
                 "X-Fiche-Emplacement": quote(emplacement)})


@app.get("/api/lot")
def lot_du_po(code: str, po: str, request: Request) -> dict:
    """Lot Sylob temps reel d'un PO choisi par l'operateur parmi les candidats."""
    service = _service(request)
    article = service.loader.chercher_article(code.strip()) or {}
    return {"po": po, "lot": service.lot_temps_reel(po.strip(), article.get("ref", ""))}


# ----------------------------------------------------------------------
# Packing Lists
# ----------------------------------------------------------------------

@app.post("/api/packing-lists")
async def deposer_packing_list(request: Request,
                               fichier: UploadFile = File(...)) -> dict:
    """Depose une Packing List sur le partage et la reindexe."""
    contenu = await fichier.read(TAILLE_MAX_PL + 1)
    if len(contenu) > TAILLE_MAX_PL:
        raise HTTPException(413, "Fichier trop volumineux (25 Mo maximum).")
    if not contenu.startswith(b"%PDF"):
        raise HTTPException(415, "Le fichier n'est pas un PDF.")
    try:
        chemin = _service(request).ajouter_packing_list(fichier.filename or "", contenu)
    except ValueError as e:
        raise HTTPException(400, str(e))
    logger.info("[SUCCES] Packing List %s deposee par %s.", fichier.filename,
                operateur(request))
    return {"emplacement": chemin}


@app.post("/api/packing-lists/recharger")
def recharger_packing_lists(request: Request) -> dict:
    """Relit le dossier des Packing Lists (fichiers deposes hors application)."""
    service = _service(request)
    service.recharger_packing_lists()
    return {"packing_lists": service.rapports_packing_lists()}


def _configurer_journal(niveau: Optional[str] = None) -> None:
    logging.basicConfig(level=niveau or os.getenv("LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    for bruyant in ("azure", "urllib3", "smbprotocol", "spnego"):
        logging.getLogger(bruyant).setLevel(logging.WARNING)


_configurer_journal()
