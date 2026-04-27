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

                # 3. Récupération des données fournisseur (PDF Extraction Layer)
                infos_list = pdf_data.chercher_infos_pdf(
                    code_article=code_scanne,
                    ref_article=article.get('ref', '')
                )
                
                if not infos_list:
                    # Stratégie de Fallback : On prend les données statiques du CSV
                    po_csv = article.get('po', '')
                    lot_csv = article.get('lot', '')
                    if po_csv or lot_csv:
                        infos_list = [{'po': po_csv, 'lot': lot_csv}]
                    else:
                        infos_list = [{'po': '', 'lot': ''}]
                        
                print(f"[OK] Article identifié : {article['designation']}")
                print(f"     Référence interne : {article['ref']}")
                
                ean_spcb = article.get('ean_spcb', '')
                ean_pcb = article.get('ean_pcb', '')
                ho = article.get('ho', '')
                if ean_spcb or ean_pcb or ho:
                    print(f"     [Infos Complémentaires] ", end="")
                    if ean_spcb: print(f"EAN SPCB: {ean_spcb} | ", end="")
                    if ean_pcb: print(f"EAN PCB: {ean_pcb} | ", end="")
                    if ho: print(f"HO (Carrefour): {ho}", end="")
                    print()

                import time
                for idx, infos in enumerate(infos_list):
                    po = infos.get('po', '')
                    lot = infos.get('lot', '')
                    fournisseur = infos.get('fournisseur', '')
                    
                    article_clone = article.copy()
                    article_clone['po'] = po
                    article_clone['lot'] = lot
                    article_clone['fournisseur'] = fournisseur
                    
                    # 4. Validation avec le "Ground Truth" (ERP Layer)
                    validation_sylob = False
                    if po and hasattr(loader, 'sylob') and loader.sylob:
                        try:
                            result = loader.sylob.chercher_lot_par_po(
                                po=po, 
                                art=article.get('ref', ''), 
                                lot=lot,
                                ean=code_scanne
                            )
                            if result is not None:
                                validation_sylob = True
                        except Exception as e:
                            logging.error(f"[ERREUR] Échec de la validation Sylob: {e}")
                    
                    suffix_num = f" (Lot {idx+1}/{len(infos_list)})" if len(infos_list) > 1 else ""
                    if validation_sylob:
                        print(f"     [Sylob] Validation confirmée par l'ERP : Commande {po} | Lot {lot}{suffix_num}")
                    else:
                        if po or lot:
                            print(f"     [PDF] Fallback utilisé : Commande {po} | Lot {lot} (Lot non validé par Sylob){suffix_num}")
                        else:
                            print(f"     [!] Attention : Ni commande ni lot identifiés{suffix_num}.")

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
