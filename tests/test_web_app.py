"""
Tests de l'application web : routes, identite Easy Auth, garde-fous de depot.

Le service metier est remplace par un double : on teste ici le contrat HTTP,
pas Sylob ni le DWH (couverts par la recette sur donnees reelles).
"""

from fastapi.testclient import TestClient

from src import web_app
from src.depot_fichiers import nom_sur
from src.reception_service import ArticleNonConfirme, Proposition


class _DepotFactice:
    description = "depot de test"

    def verifier(self) -> tuple[bool, str]:
        return True, self.description


class _ServiceFactice:
    def __init__(self) -> None:
        self.depot = _DepotFactice()
        self.loader = type("L", (), {"dwh": None, "sylob": type(
            "S", (), {"is_healthy": lambda self: True})()})()
        self.dernier_operateur = ""
        self.pl_recues: list[tuple[str, bytes]] = []

    def rapports_packing_lists(self) -> list[dict]:
        return []

    def analyser(self, code: str) -> Proposition:
        if code == "000":
            return Proposition(code=code, message="Code inconnu.")
        return Proposition(code=code, trouve=True, fiable=code != "999",
                           article={"ref": "10120214", "designation": "Couteau"},
                           po="00184449", lot_sylob="TGHU1534800")

    def generer(self, code: str, choix: dict, operateur: str) -> tuple[str, bytes, str]:
        if code == "000":
            raise LookupError("Code inconnu.")
        if code == "999" and not choix.get("confirme"):
            raise ArticleNonConfirme("correspondance approximative")
        self.dernier_operateur = operateur
        return "Fiche_10120214_TGHU1534800_x.xlsx", b"PK-xlsx", "\\\\srv\\partage\\Fiche.xlsx"

    def ajouter_packing_list(self, nom: str, contenu: bytes) -> str:
        self.pl_recues.append((nom, contenu))
        return "/pl/" + nom


def _client() -> tuple[TestClient, _ServiceFactice]:
    service = _ServiceFactice()
    web_app.app.state.service = service
    return TestClient(web_app.app), service


def test_page_servie() -> None:
    client, _ = _client()
    reponse = client.get("/")
    assert reponse.status_code == 200
    assert 'id="code"' in reponse.text


def test_scan_renvoie_la_proposition() -> None:
    client, _ = _client()
    corps = client.post("/api/scan", json={"code": " 3760000000001 "}).json()
    assert corps["trouve"] is True
    assert corps["code"] == "3760000000001"
    assert corps["po"] == "00184449"


def test_scan_vide_refuse() -> None:
    client, _ = _client()
    assert client.post("/api/scan", json={"code": ""}).status_code == 422


def test_fiche_porte_l_identite_easy_auth() -> None:
    client, service = _client()
    reponse = client.post("/api/fiches", json={"code": "123"},
                          headers={"X-MS-CLIENT-PRINCIPAL-NAME": "flo@tb-groupe.fr"})
    assert reponse.status_code == 200
    assert reponse.content == b"PK-xlsx"
    assert "attachment" in reponse.headers["content-disposition"]
    assert service.dernier_operateur == "flo@tb-groupe.fr"


def test_fiche_sans_easy_auth_prend_l_operateur_local() -> None:
    client, service = _client()
    client.post("/api/fiches", json={"code": "123"})
    assert service.dernier_operateur == web_app.Config.OPERATEUR_LOCAL


def test_article_non_fiable_exige_confirmation() -> None:
    client, _ = _client()
    assert client.post("/api/fiches", json={"code": "999"}).status_code == 409
    assert client.post("/api/fiches", json={"code": "999", "confirme": True}).status_code == 200


def test_code_inconnu_404() -> None:
    client, _ = _client()
    assert client.post("/api/fiches", json={"code": "000"}).status_code == 404


def test_depot_refuse_un_non_pdf() -> None:
    client, service = _client()
    reponse = client.post("/api/packing-lists",
                          files={"fichier": ("pl.pdf", b"MZ binaire", "application/pdf")})
    assert reponse.status_code == 415
    assert service.pl_recues == []


def test_depot_accepte_un_pdf() -> None:
    client, service = _client()
    reponse = client.post("/api/packing-lists",
                          files={"fichier": ("PL-SZSE1-TGHU1.pdf", b"%PDF-1.7 ...", "application/pdf")})
    assert reponse.status_code == 200
    assert service.pl_recues[0][0] == "PL-SZSE1-TGHU1.pdf"


def test_health_degrade_sans_dwh() -> None:
    client, _ = _client()
    assert client.get("/api/health").status_code == 503


def test_nom_sur_neutralise_les_chemins() -> None:
    assert nom_sur("../../etc/passwd") == "passwd"
    assert nom_sur("C:\\Windows\\x.pdf") == "x.pdf"
    assert nom_sur("PL-SZSE2601540-TLLU4162583.pdf") == "PL-SZSE2601540-TLLU4162583.pdf"
    assert nom_sur("..pdf") == "pdf"
