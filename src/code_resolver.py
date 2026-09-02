"""
[RESOLVER] Resolution d un code scanne vers un article (fiche_de_controle)

Strategie :
- Un code scanne peut etre un EAN13 unite, un EAN14 carton (PCB), un EAN14
  sous-carton (SPCB) ou une reference interne TB. L implementation historique
  n interrogeait QUE les colonnes `ean` et `ref`, puis retombait sur un match
  flou de 10 caracteres. Consequence : les colis etiquetes en EAN14 par
  certains fournisseurs echouaient, ou remontaient un article voisin sans que
  personne le sache. C est la cause la plus probable du "ca ne marche plus
  selon le fournisseur" remonte par le service qualite.
- Ici la resolution est exhaustive, ordonnee et TRACEE : le type de code et la
  colonne de correspondance sont toujours connus, et le match approximatif
  devient un dernier recours explicitement signale, jamais un silence.

Junior Tip : un EAN14 n est pas un EAN13 avec un chiffre en plus. C est un
chiffre indicateur de conditionnement, suivi des 12 premiers chiffres de
l EAN13, suivi d une NOUVELLE cle de controle. On ne peut donc pas comparer
deux codes par sous-chaine : il faut reconstruire l EAN13 et recalculer sa cle.
"""

import logging
import re
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# Valeurs sentinelles d une cellule vide apres lecture pandas en dtype=str.
# 731 lignes du referentiel portent "nan" en ean_pcb : sans ce garde-fou, une
# valeur vide devient une cle de recherche et remonte un article au hasard.
_VIDES: frozenset[str] = frozenset({"", "nan", "none", "null", "na", "-"})

# Colonnes du referentiel article interrogees, dans l ordre de confiance.
_COLONNES_EXACTES: tuple[tuple[str, str], ...] = (
    ("ean", "EAN13"),
    ("ean_pcb", "EAN14_PCB"),
    ("ean_spcb", "EAN14_SPCB"),
    ("ref", "REF"),
)


@dataclass(frozen=True)
class ResolutionCode:
    """
    Resultat trace de la resolution d un code scanne.

    Attributes:
        trouve: True si un article a ete identifie.
        type_code: EAN13, EAN14_PCB, EAN14_SPCB, REF, EAN14_DERIVE, APPROXIMATIF
            ou INCONNU.
        colonne: colonne du referentiel qui a produit la correspondance.
        fiable: False quand la correspondance demande une confirmation humaine.
        article: dict article du referentiel, None si non trouve.
        message: explication destinee a l operateur (FR).
    """

    trouve: bool
    type_code: str
    colonne: str
    fiable: bool
    article: Optional[dict]
    message: str


def _cle_ean(base: str) -> str:
    """
    Calcule la cle de controle GS1 d un code sans sa cle (12 ou 13 chiffres).

    Args:
        base: Chiffres du code SANS la cle de controle finale.

    Returns:
        Le chiffre de cle de controle.

    Junior Tip : la ponderation GS1 part de la DROITE du code, en alternant
    3 puis 1. La cle est le complement a la dizaine superieure.
    """
    total = 0
    for position, caractere in enumerate(reversed(base)):
        poids = 3 if position % 2 == 0 else 1
        total += int(caractere) * poids
    return str((10 - total % 10) % 10)


def ean14_vers_ean13(code: str) -> Optional[str]:
    """
    Convertit un EAN14 (carton) en EAN13 (unite consommateur).

    Args:
        code: Code a 14 chiffres.

    Returns:
        L EAN13 correspondant, ou None si le code n est pas un EAN14 valide.
    """
    if not re.fullmatch(r"\d{14}", code or ""):
        return None
    if _cle_ean(code[:13]) != code[13]:
        logger.warning("[ATTENTION] Cle de controle EAN14 invalide : %s", code)
        return None
    base12 = code[1:13]
    return base12 + _cle_ean(base12)


def normaliser_code(code: str) -> str:
    """Retire espaces, tirets et caracteres parasites d une lecture douchette."""
    return re.sub(r"[^0-9A-Za-z]", "", (code or "").strip())


def resoudre(code_scanne: str, df: object) -> ResolutionCode:
    """
    Identifie l article correspondant a un code scanne, de facon tracee.

    Ordre de resolution :
      1. Correspondance exacte sur ean, ean_pcb, ean_spcb, ref (fiable).
      2. Si le code est un EAN14 valide absent des colonnes carton, on le
         convertit en EAN13 et on retente (fiable, GS1 deterministe).
      3. Correspondance approximative sur 10 chiffres (NON fiable, signalee).

    Args:
        code_scanne: Code brut sorti de la douchette.
        df: DataFrame du referentiel article (colonnes en minuscules).

    Returns:
        ResolutionCode, jamais None. `trouve=False` porte la raison.

    Junior Tip : on ne renvoie jamais un article sans dire COMMENT il a ete
    trouve. Un match approximatif accepte en silence est un faux positif qui
    finira sur une fiche de controle qualite.
    """
    code = normaliser_code(code_scanne)
    if code.lower() in _VIDES:
        return ResolutionCode(False, "INCONNU", "", False, None,
                              "Code scanne vide ou non exploitable.")
    if df is None:
        return ResolutionCode(False, "INCONNU", "", False, None,
                              "Referentiel article non charge.")

    for colonne, type_code in _COLONNES_EXACTES:
        if colonne not in df.columns:
            continue
        trouve = df[(df[colonne] == code)
                    & (~df[colonne].str.lower().isin(_VIDES))]
        if not trouve.empty:
            article = trouve.iloc[0].to_dict()
            article["source"] = "Referentiel (%s)" % colonne
            logger.info("[SUCCES] Article resolu par %s : %s",
                        colonne, article.get("designation", code))
            return ResolutionCode(True, type_code, colonne, True, article,
                                  "Article identifie par %s." % colonne)

    ean13 = ean14_vers_ean13(code)
    if ean13 and "ean" in df.columns:
        trouve = df[(df["ean"] == ean13)
                    & (~df["ean"].str.lower().isin(_VIDES))]
        if not trouve.empty:
            article = trouve.iloc[0].to_dict()
            article["source"] = "Referentiel (EAN14 converti)"
            logger.info("[SUCCES] EAN14 %s converti en EAN13 %s : %s",
                        code, ean13, article.get("designation", ean13))
            return ResolutionCode(
                True, "EAN14_DERIVE", "ean", True, article,
                "Code carton converti en EAN13 %s." % ean13)

    resolution = _resoudre_approximatif(code, df)
    if not resolution.trouve:
        logger.warning("[ECHEC] Code non resolu : %s", code)
    return resolution


def _resoudre_approximatif(code: str, df: object) -> ResolutionCode:
    """
    Dernier recours : correspondance sur 10 chiffres consecutifs.

    Conserve pour ne pas regresser sur les etiquettes hors norme, mais le
    resultat est marque NON fiable pour que l interface demande confirmation.
    """
    if len(code) < 11 or "ean" not in df.columns:
        return ResolutionCode(False, "INCONNU", "", False, None,
                              "Code inconnu du referentiel article.")
    coeur = code[1:11]
    trouve = df[df["ean"].str.contains(coeur, na=False, regex=False)]
    if trouve.empty:
        return ResolutionCode(False, "INCONNU", "", False, None,
                              "Code inconnu du referentiel article.")
    if len(trouve) > 1:
        logger.warning("[ATTENTION] %d articles correspondent au fragment %s",
                       len(trouve), coeur)
    article = trouve.iloc[0].to_dict()
    article["source"] = "Referentiel (approximatif)"
    logger.warning("[ATTENTION] Match approximatif sur %s (%d candidat(s))",
                   coeur, len(trouve))
    return ResolutionCode(
        False if len(trouve) > 1 else True, "APPROXIMATIF", "ean", False,
        article,
        "Correspondance approximative sur %s, %d candidat(s) : a confirmer."
        % (coeur, len(trouve)))
