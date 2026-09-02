# fiche_de_controle — Contexte Claude

## Rôle
Qualité / Packing — génération automatique de fiches de contrôle réception.
Livrable : exécutable .exe Windows (PyInstaller) déployé sur le partage
`A:\QUALITE\R4 ACHATS\Contrôle réception\...`, utilisé par Flo (service qualité).

## Statut
**Production**, fiabilisation en cours. Voir
`claude/.ai_memory/decisions_log/20260902_fiche_controle_fiabilisation.md`.

## Stack
- Python 3.11 · API Sylob · extraction PDF · OCR local · génération Excel
- PyInstaller (compilation .exe), local uniquement (pas d'Azure Function)

## Structure
```
src/     # flat — pas de sous-dossiers
├── sylob_api.py       # Client API Sylob (credentials Key Vault)
├── code_resolver.py   # Résolution du code scanné (EAN13 / EAN14 PCB-SPCB / réf)
├── ocr_engine.py      # Texte natif -> cache -> OCR local (eng+fra+chi_sim)
├── pdf_extractor.py   # Parsing des Packing Lists par format fournisseur
├── excel_handler.py   # Génération Excel
├── data_loader.py     # Référentiel article
└── scanner_app.py     # Boucle de scan (CLI douchette)
scripts/  # diagnostic_codes.py, diagnostic_pl.py, migrer_secrets_sylob.py,
          # preparer_ocr_portable.ps1
tests/    # non-régression de la résolution des codes (pytest)
tools/    # binaires OCR portables, non versionnés, livrés dans le zip
```

## Credentials
Secret **unique** `tb-sylob-client` dans **`kv-dtpf-prod`** (charge utile JSON :
`user`, `password`, `unite_pers`, `session_id`, `base_url1`, `base_url`).
Source de vérité partagée avec MyReport et tout futur connecteur Sylob, cf.
skill `tb-data-socle-commun` §4. Un nom de secret Key Vault n'accepte pas
d'underscore, donc le nom réel est `tb-sylob-client` et non `tb_sylob_client`.
Replis dégradés, dans l'ordre : ancien vault `kv-tb-ia-agents-secrets` (secrets
unitaires `SYLOB-*`), puis `.env` local. **Le `.env` n'est plus déployé.**

## ⚠️ Alertes actives
- Le référentiel article vient encore de `0_Modele_Et_Donnees/article.csv`
  (8874 lignes, maintenu à la main). Cible : `public.articles3` du DWH via une
  dimension conforme `ref.article`. **Ne jamais pointer ce projet sur `achat.*`
  en direct** (gouvernance des schémas, socle §2).
- PO / lot / fournisseur doivent basculer sur `psql-dtpf-psql-prod`
  (`commandes_detaillees27`, `tracabilite`, `achat.ot_transport`) : les regex
  par format fournisseur plafonnent à 11 Packing Lists exploitables sur 19.
- OCR : exige `tools/tesseract` (langues eng, fra, chi_sim) et `tools/poppler`.
  Sans eux, les Packing Lists scannées sont inexploitables, et l'application le
  dit maintenant explicitement au démarrage.
- `pdf_extractor.py` : doublon partiel avec `Rapport_Apave_Corim/src/pdf_extractor.py`
  → extraire en lib `tb_document_ai`.
- Le `.env` historique reste à supprimer du partage `A:\QUALITE\...`.

## Standards TB Groupe
- Python 3.11, type hints partout, fonctions max 50 lignes
- `get_base_path()` obligatoire (le .exe PyInstaller change le chemin courant)
- `logger = logging.getLogger(__name__)`, messages balisés
  `[SUCCES]` / `[ECHEC]` / `[INFO]` / `[ATTENTION]` — jamais de `print()`
  hors sortie CLI destinée à l'opérateur
- Zéro credential en dur, zéro `.env` sur un partage réseau
- Un échec ne doit JAMAIS être silencieux : zéro article extrait est un `[ECHEC]`
  nommé, jamais un `[SUCCES]`
- Jamais de tiret cadratin, ni dans le code ni dans les logs
