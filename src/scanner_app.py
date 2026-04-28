"""
[ARCHITECTURE] Orchestrateur CLI (fiche_de_controle)

Rôle global :
Ce script est le point d'entrée principal (Main) de l'application Scanner de Qualité.
Il orchestre la boucle d'interaction avec l'opérateur (qui scanne avec sa douchette), 
coordonne la recherche dans le référentiel (`DataLoader`), extrait les informations
des "Packing Lists" (`PDFExtractor`), valide avec l'ERP (`SylobAPI`) et déclenche 
la création du document final (`ExcelHandler`).

Stratégie métier (UX Terminal & Boucle Infinie) :
L'application tourne sur le poste d'un opérateur en entrepôt. Elle doit être robuste,
ne jamais crasher sur une mauvaise frappe, et fournir un feedback visuel très clair
(Couleurs, balises [OK], [ERREUR]). La boucle `while True` permet d'enchaîner les 
scans à la vitesse de la douchette (qui simule un appui sur la touche "Entrée" après
chaque code-barres).
"""

import sys
import os
import logging
from datetime import datetime

# Ajout du dossier racine au chemin de recherche pour pouvoir importer les modules de src/
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.data_loader import DataLoader
from src.excel_handler import ExcelHandler
from src.pdf_extractor import PDFExtractor

def lancer_session_scan() -> None:
    """
    Lance la boucle interactive d'écoute de la douchette de scan.
    
    Stratégie :
    1. Initialise tous les composants en amont pour éviter les latences durant le scan.
    2. Reste en écoute (bloquant) sur `input()`.
    3. Traite la logique métier complète : CSV -> PDF -> Sylob -> Excel.
    4. Propose l'archivage en fin de session pour un roulement propre des données journalières.
    """
    print("\n" + "="*50)
    print("      INTERFACE AUTOMATISÉE - SERVICE QUALITÉ")
    print("="*50)
    
    # 1. Initialisation des composants (Fail-fast si fichiers manquants)
    try:
        loader = DataLoader()
        handler = ExcelHandler()
        pdf_data = PDFExtractor()

    except Exception as e:
        print(f"[-] Erreur critique d'initialisation : {e}")
        return

    print("\n[INFO] L'application est connectée et prête.")
    print("[INFO] Astuce : Utilisez votre douchette sur le code-barres de l'article.")
    print("[INFO] Tapez 'STOP' (ou scannez le code d'arrêt) pour terminer la session.\n")

    nb_scans = 0

    while True:
        try:
            # L'input bloque en attendant la douchette (ou une saisie clavier manuelle)
            code_scanne = input(">>>> SCAN ARTICLES : ").strip()
            
            if code_scanne.upper() == 'STOP':
                print("\n[FIN] Session terminée. Merci !")
                
                # Log rotation / Nettoyage métier
                choix = input("Voulez-vous archiver les Packing Lists actuelles pour ne pas les relire demain ? (O/N) : ").strip().upper()
                if choix == 'O':
                    pdf_data.archiver_pdfs()
                    print("[INFO] Fichiers PDF déplacés avec succès vers les archives.")
                    
                break
                
            if not code_scanne:
                continue

            # 2. Recherche de l'article (Data Layer)
            article = loader.chercher_article(code_scanne)
            
            if article:
                nb_scans += 1

                # Initialisation des variables avec priorité
                final_po = ""
                final_lot = ""
                final_fournisseur = ""
                
                # 3. Interroge API Sylob (Priorité 1)
                if hasattr(loader, 'sylob') and loader.sylob:
                    try:
                        result = loader.sylob.chercher_lot_par_po(
                            po="", art=article.get('ref', ''), lot="", ean=code_scanne
                        )
                        if result:
                            final_po = result.get('po', '')
                            final_lot = result.get('lot', '')
                            if final_po or final_lot:
                                print(f"     [Sylob] Données partielles/totales récupérées depuis l'ERP : Commande {final_po} | Lot {final_lot}")
                    except Exception as e:
                        logging.error(f"[ERREUR] Échec de l'interrogation Sylob: {e}")

                # 4. Fouille dans les PDF présents (Priorité 2 - Fallback des infos manquantes)
                pdf_infos_list = pdf_data.chercher_infos_pdf(code_article=code_scanne, ref_article=article.get('ref', ''))
                
                # Si le PDF a trouvé plusieurs occurrences, on prend la première pour combler les trous
                if pdf_infos_list:
                    pdf_po = pdf_infos_list[0].get('po', '')
                    pdf_lot = pdf_infos_list[0].get('lot', '')
                    pdf_fournisseur = pdf_infos_list[0].get('fournisseur', '')
                    
                    added_from_pdf = []
                    if not final_po and pdf_po: 
                        final_po = pdf_po
                        added_from_pdf.append(f"PO: {final_po}")
                    if not final_lot and pdf_lot:
                        final_lot = pdf_lot
                        added_from_pdf.append(f"Lot: {final_lot}")
                    if not final_fournisseur and pdf_fournisseur:
                        final_fournisseur = pdf_fournisseur
                        added_from_pdf.append(f"Fournisseur: {final_fournisseur}")
                        
                    if added_from_pdf:
                        print(f"     [PDF] Fallback utilisé pour compléter : {', '.join(added_from_pdf)}")

                # 5. Fallback sur article.csv (Priorité 3 - Fallback ultime)
                csv_po = str(article.get('po', '')).replace('nan', '').strip()
                csv_lot = str(article.get('lot', '')).replace('nan', '').strip()
                csv_fournisseur = str(article.get('fournisseur', '')).replace('nan', '').strip()
                
                added_from_csv = []
                if not final_po and csv_po:
                    final_po = csv_po
                    added_from_csv.append(f"PO: {final_po}")
                if not final_lot and csv_lot:
                    final_lot = csv_lot
                    added_from_csv.append(f"Lot: {final_lot}")
                if not final_fournisseur and csv_fournisseur:
                    final_fournisseur = csv_fournisseur
                    added_from_csv.append(f"Fournisseur: {final_fournisseur}")
                    
                if added_from_csv:
                    print(f"     [CSV] Fallback ultime utilisé depuis la base locale pour : {', '.join(added_from_csv)}")
                    
                if not final_po and not final_lot:
                    print(f"     [!] Attention : Ni commande ni lot identifiés après tous les fallbacks.")

                # Consolidation
                infos_list = [{'po': final_po, 'lot': final_lot, 'fournisseur': final_fournisseur}]

                import time
                for idx, infos in enumerate(infos_list):
                    po = infos.get('po', '')
                    lot = infos.get('lot', '')
                    fournisseur = infos.get('fournisseur', '')
                    
                    article_clone = article.copy()
                    article_clone['po'] = po
                    article_clone['lot'] = lot
                    article_clone['fournisseur'] = fournisseur

                    # 5. Export des données (Excel Layer)
                    print(f"     Génération de la fiche Excel en cours...")
                    if idx > 0:
                        # Assurer l'unicité du nommage de fichier basé sur le timestamp
                        time.sleep(1) 
                        
                    chemin_fiche = handler.generer_fiche(article_clone)
                    
                    if chemin_fiche:
                        print(f"[SUCCÈS] Fiche d'inspection créée avec succès : {chemin_fiche}")
                    else:
                        print("[ERREUR] Impossible de sauvegarder le fichier Excel, vérifiez qu'il n'est pas déjà ouvert.")
                        

                # Feedback UX pour ralentir la cadence et valider visuellement
                print()
                choix_arch = input("     -> Appuyez sur Entrée pour le PROCHAIN SCAN, ou tapez 'A' pour ARCHIVER le(s) PDF : ").strip().upper()
                if choix_arch == 'A':
                    pdf_data.archiver_pdfs()
                    print("     [INFO] Fichiers PDF isolés avec succès.")
                print()
            else:
                print(f"[!] Erreur : Le code '{code_scanne}' n'est rattaché à aucun article connu.")
                print("    Vérifiez qu'il s'agit bien d'une référence interne ou d'un EAN valide.")

        except KeyboardInterrupt:
            # Sortie élégante si l'utilisateur fait CTRL+C
            print("\nArrêt forcé par l'opérateur.")
            break
        except Exception as e:
            # Ne jamais crasher dans la boucle principale
            print(f"\n[!] Une exception inattendue est survenue : {e}")


if __name__ == "__main__":
    lancer_session_scan()
