"""
[ARCHITECTURE] Génération Documentaire (fiche_de_controle)

Rôle global :
Ce module gère l'injection des données consolidées (issues de Sylob, du CSV et de l'extraction PDF)
directement dans un template Excel d'inspection qualité. C'est l'interface de sortie vers les équipes
opérationnelles (Qualité / Réception).

Stratégie métier (Template injection) :
Il est crucial d'utiliser la librairie `openpyxl` plutôt que `pandas` pour l'export. Pandas
écraserait les macros, la mise en forme (couleurs, polices, tailles de cellules) et les 
formules pré-existantes dans le fichier modèle (FOR-ACH-30-2). En utilisant openpyxl, on 
édite chirurgicalement des cellules spécifiques (ex: B4, G5) tout en conservant l'intégrité
du document qualité certifié.
"""

import io
import logging
import os
import sys
from datetime import datetime
from typing import Optional

import openpyxl

logger = logging.getLogger(__name__)

# Cellule du lot fournisseur. Elle sort du gabarit FOR-ACH-30-2 d origine :
# a ajuster avec le service qualite si la mise en page ne convient pas.
CELLULE_LOT_FOURNISSEUR = "H6"

def get_base_path() -> str:
    """
    Retourne le chemin d'exécution absolu.
    
    Stratégie :
    Prend en compte l'exécution depuis un exécutable compilé (PyInstaller)
    pour garantir que le dossier racine est toujours correctement résolu, 
    empêchant les erreurs "File Not Found" sur les postes des opérateurs.
    """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


class ExcelHandler:
    """
    Classe utilitaire gérant la manipulation du fichier Excel de contrôle réception.
    """
    
    def __init__(self, template_path: str = None):
        base_path = get_base_path()
        if template_path is None:
            self.template_path = os.path.join(base_path, "0_Modele_Et_Donnees", "FOR-ACH-30-2 Fiche d'inspection produit-Contrôle réception.xlsx")
        else:
            self.template_path = template_path
            
        self.output_dir = os.path.join(base_path, "2_Fiches_Creees")
        
        # S'assurer que le dossier de sortie existe
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

    def generer_fiche(self, article_info: dict, operateur: str = "") -> Optional[str]:
        """
        Genere la fiche et l'ecrit dans 2_Fiches_Creees (usage poste / executable).

        Returns:
            Chemin absolu de la fiche, ou None si l'ecriture echoue.
        """
        try:
            nom, contenu = self.construire_fiche(article_info, operateur)
        except Exception as e:
            logger.error("[ECHEC] Generation de la fiche : %s", e, exc_info=True)
            return None
        chemin_sortie = os.path.join(self.output_dir, nom)
        try:
            with open(chemin_sortie, "wb") as flux:
                flux.write(contenu)
        except OSError as e:
            # Cas typique : une fiche du meme nom ouverte dans Excel.
            logger.error("[ECHEC] Ecriture de %s : %s", chemin_sortie, e)
            return None
        logger.info("[SUCCES] Fiche generee : %s", chemin_sortie)
        return chemin_sortie

    def construire_fiche(self, article_info: dict,
                         operateur: str = "") -> tuple[str, bytes]:
        """
        Remplit le gabarit FOR-ACH-30-2 en memoire, sans rien ecrire sur disque.

        Strategie :
        - openpyxl edite des cellules precises et conserve la mise en forme du
          document qualite certifie (pandas l'ecraserait).
        - Nom horodate Fiche_<ref>_<lot>_<horodatage>.xlsx : jamais d'ecrasement.
        - L'operateur (identite Entra en Web App) est inscrit dans les
          proprietes du classeur : la tracabilite ne depend pas d'une cellule
          que le gabarit ne prevoit pas.

        Args:
            article_info: Donnees consolidees de l'article.
            operateur: Identite de la personne qui genere la fiche.

        Returns:
            Tuple (nom du fichier, contenu xlsx).

        Raises:
            FileNotFoundError: si le gabarit est absent.
        """
        if not os.path.exists(self.template_path):
            raise FileNotFoundError("Gabarit Excel introuvable : %s" % self.template_path)
        now = datetime.now()
        lot = str(article_info.get('lot', '')).replace("/", "-").replace("\\", "-")
        lot_suffix = f"_{lot}" if lot else ""
        ref = str(article_info['ref']).replace("/", "-").replace("\\", "-")
        nom = f"Fiche_{ref}{lot_suffix}_{now.strftime('%Y%m%d_%H%M%S')}.xlsx"

        wb = openpyxl.load_workbook(self.template_path)
        self._remplir(wb.active, article_info, lot, now)
        if operateur:
            wb.properties.creator = operateur
            wb.properties.lastModifiedBy = operateur
        tampon = io.BytesIO()
        wb.save(tampon)
        return nom, tampon.getvalue()

    def _remplir(self, ws: object, article_info: dict, lot: str,
                 now: datetime) -> None:
        """Injecte les donnees metier dans les cellules du gabarit, en rouge."""
        from openpyxl.styles import Font
        red_font = Font(color="FF0000")

        def set_red_value(cell_coord: str, value: object) -> None:
            ws[cell_coord] = value
            ws[cell_coord].font = red_font

        set_red_value('B4', now.strftime("%d/%m/%Y"))
        set_red_value('F4', now.strftime("%d/%m/%Y"))
        set_red_value('B5', article_info['ref'])
        set_red_value('B6', article_info['designation'])

        # Deux lots distincts et non interchangeables : le lot Sylob (reference
        # interne) et le lot imprime par le fournisseur. Les fondre dans une
        # meme case masquait les divergences, qui sont precisement ce qu'un
        # controle reception doit voir. CELLULE_LOT_FOURNISSEUR sort du gabarit
        # d'origine : validation visuelle du service qualite requise.
        set_red_value('G5', article_info.get('po', ''))
        set_red_value('G6', lot)
        lot_fournisseur = _propre(article_info.get('lot_fournisseur', ''))

        # Nettoyage preventif de la colonne H (commentaires du gabarit vierge),
        # AVANT d'y ecrire le lot fournisseur.
        for row in range(5, 51):
            ws[f'H{row}'] = None
        if lot_fournisseur and lot_fournisseur != lot:
            set_red_value(CELLULE_LOT_FOURNISSEUR, "Lot frn : %s" % lot_fournisseur)
            logger.warning("[ATTENTION] Lot fournisseur %s different du lot Sylob %s.",
                           lot_fournisseur, lot or "(vide)")
        elif lot_fournisseur:
            logger.info("[INFO] Lot fournisseur et lot Sylob concordent (%s).",
                        lot_fournisseur)

        fournisseur = article_info.get('fournisseur', '')
        if fournisseur:
            set_red_value('C9', fournisseur)
            ws.merge_cells('C9:G9')
        for cellule, cle in (('F12', 'ean_pcb'), ('F14', 'ean_spcb'), ('B35', 'ho')):
            valeur = _propre(article_info.get(cle, ''))
            if valeur:
                set_red_value(cellule, valeur)


def _propre(valeur: object) -> str:
    """Neutralise les 'nan' herites de pandas et les espaces."""
    return str(valeur or '').replace('nan', '').strip()


if __name__ == "__main__":
    # Test unitaire rapide
    h = ExcelHandler()
    dump_article = {'ref': 'TEST-123', 'designation': 'Article de Test', 'ean': '000000'}
    h.generer_fiche(dump_article)
