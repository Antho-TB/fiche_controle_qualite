# fiche_de_controle : contexte Claude

## Rôle
Qualité / réception : génération des fiches de contrôle réception (gabarit FOR-ACH-30-2) à partir
d'un code scanné à la douchette. Utilisé par Flo (service qualité).

## Statut (09/10/2026)
- **En production** : `Scanner_Qualite.exe` du 28/04 sur `A:\QUALITE\R4 ACHATS\Contrôle réception\2026\Contrôle TB`.
- **En cours** : bascule vers une **Web App Azure** (`app-shsv-fichectrl-prod`, plan FUSEAU). Le code et la CI sont
  livrés, l'infra reste à appliquer par Antho.
- **Reprendre par** `docs/20261009_Point_de_reprise.md` (actions dans l'ordre, pièges).
- Décisions : `claude/.ai_memory/decisions_log/20261009_fiche_controle_webapp_azure.md` (Web App) et
  `20260902_fiche_controle_fiabilisation.md` (codes carton, DWH).

## Stack
Python 3.11 · FastAPI et une page HTML (design system TB) · API Sylob · DWH `dtpf_sylob_prod` · RapidOCR puis
Gemini (Vertex AI) · openpyxl · Terraform (Azure App Service) · GitHub Actions (OIDC). L'exe PyInstaller reste
buildable (`build_exe.bat`).

## Structure
```
src/      # flat
├── web_app.py           # FastAPI : /, /api/scan, /api/fiches, /api/lot, /api/packing-lists, /api/health
├── static/              # index.html (design system TB), logo et favicon officiels
├── reception_service.py # Coeur métier sans input() : proposer, arbitrer, générer
├── config.py            # Config centralisée (variables d'environnement)
├── depot_fichiers.py    # Dépôt local | SMB (SRV-FILES-POM) ; depot_drive.py : Drive partagé
├── dwh_repository.py    # articles3, commandes_detaillees, tracabilite, achat.ot_transport (lecture seule)
├── sylob_api.py         # RECEPTIONAPI : lot temps réel du PO retenu
├── ocr_engine.py        # Texte natif -> cache -> RapidOCR -> tesseract
├── lecteur_gemini.py    # Repli Gemini (lignes structurées, cache, label app=fiche-controle)
├── gcp_auth.py / azure_auth.py
├── pdf_extractor.py · code_resolver.py · excel_handler.py · data_loader.py
├── scanner_app.py       # Ancienne boucle console (exe) ; preflight.py : --verifier-poste
deploy/webapp/  # Terraform, deployer_infra.ps1, appliquer_role_fichectrl.py, README (runbook)
deploy/gcp/     # creer_projet_fichectrl.ps1
.github/workflows/deploy-azure.yml  # tests, puis déploiement si vars.DEPLOIEMENT_ACTIF == 'true'
docs/           # point de reprise, recette Flo, tickets GLPI
tests/          # pytest (33)
```

## Sources de données (ordre)
Packing List (simple indice) → **DWH** (choisit le PO : `public.commandes_detaillees`, jamais les tables
numérotées figées) → **API Sylob** (lot du PO, temps réel) → CSV historique. Interroger Sylob par le seul EAN
rend une réception quelconque : interdit.

## Credentials (noms uniquement)
- `kv-dtpf-prod` :
  - `tb-sylob-client` (JSON Sylob) ;
  - `psql-prod-fichectrl-app-login` / `-password` (rôle `dtpf_fichectrl_app_prod`, lecture seule, 6 tables) ;
  - `gcp-fichectrl-sa-key` (compte `compteserve@qualitefichecontrole.iam.gserviceaccount.com`) ;
  - `svc-fichectrl-ad-login` / `-password` (à venir, ticket Alban).
- GCP : projet `qualitefichecontrole`. Drive partagé « Fiche de Controle » `0ACZ6_BwnqSS_Uk9PVA`.
- Infra appliquée sous **`abezille@tbgroupefr.onmicrosoft.com`** (profil `$HOME\.azure-admin`), jamais sous
  `a.bezille@tb-groupe.fr` : pas de MFA en CLI, pas d'accès au state.

## Alertes actives
- `opencv-python` (non headless) interdit sur App Service (libGL) : la CI construit `.python_packages` et le
  vérifie.
- La cellule H6 (lot fournisseur) sort du gabarit : validation qualité requise à la recette.
- La bascule MyReport `public` → `myreport` imposera de repointer les tables et de rejouer
  `appliquer_role_fichectrl.py`.
- `.env` et exe historiques à retirer de `A:\QUALITE\...` après le go de Flo (accord écrit).
- `pdf_extractor.py` : doublon partiel avec `Rapport_Apave_Corim`, à extraire dans une bibliothèque commune.

## Standards TB Groupe
- Python 3.11, type hints, fonctions de 50 lignes au plus, `Config` centralisée.
- `logger = logging.getLogger(__name__)`, messages `[SUCCES]` / `[ECHEC]` / `[INFO]` / `[ATTENTION]`.
- Zéro credential en dur, zéro `.env` sur un partage. Un échec n'est jamais silencieux.
- Jamais de tiret cadratin.
