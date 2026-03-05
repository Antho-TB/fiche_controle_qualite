import sys
import os

# Ajout du dossier racine au chemin de recherche pour pouvoir importer les modules de src/
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.data_loader import DataLoader
from src.excel_handler import ExcelHandler
from src.pdf_extractor import PDFExtractor
import logging
import mlflow

def lancer_session_scan():
    """
    Point d'entrée principal de l'application.
    Coordonne la lecture CSV, l'entrée douchette et la génération Excel.
    """
    print("\n" + "="*50)
    print("      INTERFACE AUTOMATISÉE - SERVICE QUALITÉ")
    print("="*50)
    
    # --- Configuration MLOps (MLflow) ---
    # On crée une expérience dédiée au suivi des sessions de scan
    mlflow.set_experiment("Controle_Qualite_Reception")
    
    # 1. Initialisation des composants
    try:
        loader = DataLoader() # Charge le CSV
        handler = ExcelHandler() # Prépare la gestion Excel
        pdf_data = PDFExtractor() # Extrait silencieusement les N° de Commande et Lots

    except Exception as e:
        print(f"[-] Erreur d'initialisation : {e}")
        return

    print("\n[INFO] Prêt pour le scan.")
    print("[INFO] Astuce : Utilisez votre douchette sur le code-barre de l'article.")
    print("[INFO] Tapez 'STOP' pour arrêter la session.\n")

    # On démarre un "run" MLflow pour cette session de travail
    with mlflow.start_run(run_name=f"Session_{datetime.now().strftime('%Y%m%d_%H%M')}"):
        # On log le fichier source utilisé
        mlflow.log_param("csv_source", loader.csv_path)
        nb_scans = 0

        while True:
            try:
                # On attend l'entrée de la douchette (qui simule une saisie clavier + Entrée)
                code_scanne = input(">>>> SCAN ARTICLES : ").strip()
                
                if code_scanne.upper() == 'STOP':
                    print("\n[FIN] Session terminée. Merci !")
                    
                    # Demander s'il faut nettoyer le dossier
                    choix = input("Voulez-vous archiver les Packing Lists actuelles pour ne pas les relire demain ? (O/N) : ").strip().upper()
                    if choix == 'O':
                        pdf_data.archiver_pdfs()
                        print("[INFO] Fichiers PDF archivés avec succès dans data/packing_lists/archives.")
                        
                    break
                    
                if not code_scanne:
                    continue

                # 2. Recherche de l'article
                article = loader.chercher_article(code_scanne)
                
                if article:
                    nb_scans += 1

                    # --- NOUVEAU: Mutiples Lots & Validation Sylob ---
                    infos_list = pdf_data.chercher_infos_pdf(
                        code_article=code_scanne,
                        ref_article=article.get('ref', '')
                    )
                    
                    if not infos_list:
                        # Fallback au CSV si le PDF ne renvoie rien
                        po_csv = article.get('po', '')
                        lot_csv = article.get('lot', '')
                        if po_csv or lot_csv:
                            infos_list = [{'po': po_csv, 'lot': lot_csv}]
                        else:
                            infos_list = [{'po': '', 'lot': ''}]
                            
                    print(f"[OK] Article identifié : {article['designation']}")
                    print(f"     Référence : {article['ref']}")

                    import time
                    for idx, infos in enumerate(infos_list):
                        po = infos.get('po', '')
                        lot = infos.get('lot', '')
                        
                        article_clone = article.copy()
                        article_clone['po'] = po
                        article_clone['lot'] = lot
                        
                        # Validation Sylob
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
                                logging.error(f"Erreur lors de la validation Sylob: {e}")
                        
                        suffix_num = f" (Lot {idx+1}/{len(infos_list)})" if len(infos_list) > 1 else ""
                        if validation_sylob:
                            print(f"     [Sylob] Validation OK : Commande {po} | Lot {lot}{suffix_num}")
                        else:
                            if po or lot:
                                print(f"     [PDF] Fallback utilisé : Commande {po} | Lot {lot} (Non validé Sylob){suffix_num}")
                            else:
                                print(f"     [!] Attention : Ni commande ni lot trouvés{suffix_num}.")

                        # 3. Génération de la fiche Excel
                        print(f"     Génération de la fiche Excel en cours...")
                        if idx > 0:
                            time.sleep(1) # Pour s'assurer de l'unicité du timestamp dans le nom de fichier
                            
                        chemin_fiche = handler.generer_fiche(article_clone)
                        
                        if chemin_fiche:
                            print(f"[SUCCÈS] Document créé : {chemin_fiche}")
                        else:
                            print("[ERREUR] Impossible de sauvegarder le fichier Excel.")
                            
                    # On log un événement pour le scan globalement réussi
                    mlflow.log_metric("total_scans_success", nb_scans)
                    
                    # --- Demander l'archivage après chaque génération ---
                    print()
                    choix_arch = input("     -> Appuyez sur Entrée pour CONTINUER, ou tapez 'A' pour ARCHIVER le(s) PDF actuel(s) : ").strip().upper()
                    if choix_arch == 'A':
                        pdf_data.archiver_pdfs()
                        print("     [INFO] Fichiers PDF archivés avec succès.")
                    print()
                else:
                    print(f"[!] Erreur : Le code '{code_scanne}' est inconnu.")
                    print("    Vérifiez qu'il s'agit bien d'une référence ou d'un GenCod valide.")

            except KeyboardInterrupt:
                print("\nArrêt forcé.")
                break
            except Exception as e:
                print(f"\n[!] Une erreur est survenue : {e}")
        
        # On log la métrique finale de la session
        mlflow.log_metric("total_session_scans", nb_scans)
        mlflow.set_tag("statut", "Complete")

if __name__ == "__main__":
    from datetime import datetime # Import nécessaire pour le nom du run
    lancer_session_scan()
