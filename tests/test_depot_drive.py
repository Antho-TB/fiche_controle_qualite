"""
Tests du depot Drive contre une fausse API Drive en memoire.

On verifie le contrat qui compte pour la qualite : arborescence annuelle
creee une seule fois, Packing List redeposee remplacee (pas dupliquee), fiche
retrouvable, et requetes toujours faites avec supportsAllDrives.
"""

import json
import re

import pytest

from src.depot_drive import DepotDrive


class _Reponse:
    def __init__(self, corps: object = None, contenu: bytes = b"") -> None:
        self._corps, self.content = corps or {}, contenu

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._corps


class _FauxDrive:
    """Simule les quelques routes Drive v3 utilisees par DepotDrive."""

    def __init__(self) -> None:
        self.fichiers: dict[str, dict] = {}
        self.appels_sans_all_drives = 0

    def _id(self) -> str:
        return "id%d" % (len(self.fichiers) + 1)

    def _verifier(self, params: dict) -> None:
        if params.get("supportsAllDrives") != "true":
            self.appels_sans_all_drives += 1

    def get(self, url: str, params: dict, timeout: int) -> _Reponse:
        self._verifier(params)
        if params.get("alt") == "media":
            return _Reponse(contenu=self.fichiers[url.rsplit("/", 1)[1]]["contenu"])
        q = params["q"]
        parent = re.search(r"'([^']+)' in parents", q).group(1)
        nom = re.search(r"name = '((?:[^'\\]|\\.)*)'", q)
        dossier = "mimeType = 'application/vnd.google-apps.folder'" in q
        pdf = "mimeType = 'application/pdf'" in q
        trouves = [dict(f, id=i) for i, f in self.fichiers.items()
                   if f["parent"] == parent and (not nom or f["name"] == nom.group(1))
                   and (not dossier or f["dossier"]) and (not pdf or f["name"].endswith(".pdf"))
                   and (dossier or not f["dossier"])]
        return _Reponse({"files": trouves})

    def post(self, url: str, params: dict, timeout: int, json: dict = None,
             data: bytes = None, headers: dict = None) -> _Reponse:
        self._verifier(params)
        identifiant = self._id()
        if json is not None:
            self.fichiers[identifiant] = {"name": json["name"], "parent": json["parents"][0],
                                          "dossier": True, "contenu": b""}
        else:
            meta, contenu = _decouper(data, headers)
            self.fichiers[identifiant] = {"name": meta["name"], "parent": meta["parents"][0],
                                          "dossier": False, "contenu": contenu}
        return _Reponse({"id": identifiant, "webViewLink": "https://drive/%s" % identifiant})

    def patch(self, url: str, params: dict, timeout: int, data: bytes,
              headers: dict) -> _Reponse:
        self._verifier(params)
        identifiant = url.rsplit("/", 1)[1]
        self.fichiers[identifiant]["contenu"] = _decouper(data, headers)[1]
        return _Reponse({"id": identifiant, "webViewLink": "https://drive/%s" % identifiant})


def _decouper(data: bytes, headers: dict) -> tuple[dict, bytes]:
    frontiere = headers["Content-Type"].split("boundary=")[1].encode()
    parties = data.split(b"--" + frontiere)
    meta = json.loads(parties[1].split(b"\r\n\r\n", 1)[1].rstrip(b"\r\n"))
    contenu = parties[2].split(b"\r\n\r\n", 1)[1][:-2]
    return meta, contenu


@pytest.fixture
def depot() -> tuple[DepotDrive, _FauxDrive]:
    faux = _FauxDrive()
    return DepotDrive(session=faux, racine="racine", annee=2026), faux


def test_fiche_deposee_dans_l_arborescence_annuelle(depot) -> None:
    drive, faux = depot
    lien = drive.deposer_fiche("Fiche_10120214_L1.xlsx", b"PKxlsx")
    noms = {f["name"] for f in faux.fichiers.values()}
    assert {"2026", "Contrôle TB", "2_Fiches_Creees", "Fiche_10120214_L1.xlsx"} <= noms
    assert lien.startswith("https://drive/")
    assert faux.appels_sans_all_drives == 0


def test_arborescence_creee_une_seule_fois(depot) -> None:
    drive, faux = depot
    drive.deposer_fiche("a.xlsx", b"1")
    drive.deposer_fiche("b.xlsx", b"2")
    assert sum(1 for f in faux.fichiers.values() if f["name"] == "2026") == 1


def test_packing_list_redeposee_remplace_sans_dupliquer(depot) -> None:
    drive, faux = depot
    drive.deposer_packing_list("PL-SZSE1-TGHU1.pdf", b"%PDF v1")
    drive.deposer_packing_list("PL-SZSE1-TGHU1.pdf", b"%PDF v2")
    assert drive.lister_packing_lists() == ["PL-SZSE1-TGHU1.pdf"]
    assert drive.lire_packing_list("PL-SZSE1-TGHU1.pdf") == b"%PDF v2"


def test_nom_hostile_neutralise(depot) -> None:
    drive, faux = depot
    drive.deposer_packing_list("../../x'y.pdf", b"%PDF")
    assert "x_y.pdf" in drive.lister_packing_lists()


def test_racine_obligatoire() -> None:
    with pytest.raises(RuntimeError):
        DepotDrive(session=object(), racine="")
