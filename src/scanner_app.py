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

                    # --- NOUVEAU: Extraction d'infos via PDF (Lot + PO) ---
                    infos_pdf = pdf_data.chercher_infos_pdf(
                        code_article=code_scanne,
                        ref_article=article.get('ref', '')
                    )
                    po = infos_pdf.get('po', '')
                    article['po'] = po
                    
                    # Récupérer le lot depuis Sylob si on a un PO
                    lot_sylob = None
                    if po and hasattr(loader, 'sylob') and loader.sylob:
                        try:
                            lot_sylob = loader.sylob.chercher_lot_par_po(po)
                        except Exception as e:
                            logging.error(f"Erreur lors de la récupération du lot Sylob: {e}")
                    
                    if lot_sylob:
                        article['lot'] = lot_sylob
                        print(f"     [Sylob] Lot récupéré : {lot_sylob}")
                    else:
                        article['lot'] = infos_pdf.get('lot', '')
                        if article['lot']:
                            print(f"     [PDF] Lot trouvé (fallback) : {article['lot']}")
                    # --------------------------------------------------------

                    print(f"[OK] Article identifié : {article['designation']}")
                    print(f"     Référence : {article['ref']}")
                    
                    if article['po']:
                        print(f"     [PDF] N° Commande : {article['po']} | Lot : {article['lot']}")

                    # 3. Génération de la fiche Excel
                    print("     Génération de la fiche Excel en cours...")
                    chemin_fiche = handler.generer_fiche(article)
                    
                    if chemin_fiche:
                        print(f"[SUCCÈS] Document créé : {chemin_fiche}")
                        # On log un événement pour chaque scan réussi
                        mlflow.log_metric("total_scans_success", nb_scans)
                    else:
                        print("[ERREUR] Impossible de sauvegarder le fichier Excel.")
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
