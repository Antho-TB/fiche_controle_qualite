# Déploiement de la fiche de contrôle sur Azure App Service

Runbook de la bascule du Scanner Qualité (exécutable PyInstaller sur
`A:\QUALITE\...`) vers une Web App Azure. Décision et arbitrages : ADR
`claude/.ai_memory/decisions_log/20261009_fiche_controle_webapp_azure.md`.

**Statut : rédigé, rien n'est appliqué.** Toutes les étapes ci-dessous créent ou
modifient des ressources : il faut l'accord écrit d'Antho avant chacune d'elles.

## Ce qui part en Azure, ce qui reste sur site

| Composant | Cible | Accès |
|---|---|---|
| Interface de scan, résolution, génération de la fiche | Web App `app-shsv-fichectrl-prod`, sur le **plan B1 de FUSEAU** | Easy Auth, groupe qualité |
| API Sylob `srv-erp` (192.168.102.38:8443) | Reste sur site, **utilisée en premier** (donnée instantanée) | VPN site à site, `tb-sylob-client` |
| DWH `dtpf_sylob_prod` | Azure, en complément et en repli (J-1) | Réseau privé, rôle `dtpf_fichectrl_app_prod` |
| Dossier `Contrôle réception` | `\\SRV-FILES-POM\PARTAGE\QUALITE` (192.168.102.55), cible réelle du DFS `A:` | SMB par le VPN, compte AD `svc-fichectrl` |
| Repli si le SMB est refusé | Drive partagé Google | API Drive, compte de service membre du Drive |
| Lecture des scans | Arbitrage en cours (voir l'ADR) | |

## Réseau

Tests faits le 09/10/2026 depuis la console Kudu de FUSEAU, qui est sur le même
réseau que la future application :

| Cible | Résultat |
|---|---|
| PostgreSQL 172.31.2.4:5432 | ouvert |
| API Sylob 192.168.102.38:8443 | ouvert, HTTP 200 |
| SRV-FILES-POM 192.168.102.55:445 | ouvert |
| DNS `srv-erp.interne.tarrerias-bonjean.fr` | **non résolu** |

Il n'y a aucun flux à ouvrir. Les hôtes sur site sont donc passés **par adresse
IP** dans les app settings. Si une IP change, il faut corriger une variable,
sans redéploiement.

La Web App partage le plan de FUSEAU, donc aussi son sous-réseau d'intégration
`snet-shsv-network-3-prod` et le peering vers dtpf. Ces trois ressources
restent dans le state FUSEAU et ne sont que lues ici. **Un `destroy` ou un
changement de SKU de FUSEAU touche aussi la fiche de contrôle.**

## Qui lance quoi

Ton compte quotidien `a.bezille@tb-groupe.fr` ne peut pas appliquer l'infrastructure (constat du
09/10/2026) :
- sa session CLI ne porte pas de MFA, alors que toute écriture Azure l'exige ;
- il n'a aucun droit sur le fichier d'état Terraform (state) ;
- il ne peut pas écrire de secret.

Le compte **`abezille@tbgroupefr.onmicrosoft.com`** (ton compte AD synchronisé) a ces droits. Les
scripts l'utilisent dans un profil Azure CLI séparé (`$HOME\.azure-admin`), sans toucher aux
autres terminaux.

## Déroulé, dans l'ordre

1. **Projet GCP dédié** (Gemini et Drive), après `gcloud auth login` :
   ```powershell
   powershell -ExecutionPolicy Bypass -File deploy\gcp\creer_projet_fichectrl.ps1
   ```
   Le script crée le projet `qualitefichecontrole`, active les API Vertex AI et Drive, crée le
   compte de service `compteserve`, dépose sa clé directement au Key Vault
   (`gcp-fichectrl-sa-key`) et pose une alerte budgétaire de 20 € par mois.
   Ensuite, dans Google Drive :
   - créer le Drive partagé qualité ;
   - y ajouter le compte de service comme « Gestionnaire de contenu » ;
   - reporter l'identifiant du dossier dans `variables.auto.tfvars` (`drive_dossier_id`) et passer
     `gemini_actif = true`.
2. **Groupe Entra du service qualité** : renseigner `groupe_utilisateurs_object_id`.
3. **Infrastructure** (VPN actif) :
   ```powershell
   powershell -ExecutionPolicy Bypass -File deploy\webapp\deployer_infra.ps1
   ```
   Chaque étape demande confirmation :
   - secrets et rôle PostgreSQL en lecture seule (`appliquer_role_fichectrl.py`, simulation
     d'abord) ;
   - `terraform plan`, **à relire**, puis `apply` ;
   - dépôt du secret Easy Auth (hors state) ;
   - environnement GitHub `production`, secrets OIDC et variable `DEPLOIEMENT_ACTIF`.
4. **Déploiement du code** : relancer le workflow « Déploiement Fiche de contrôle » sur GitHub, ou
   pousser sur `main`. Le workflow lance les tests, construit les dépendances, déploie, puis
   vérifie que le commit servi est bien le bon et que la racine est protégée par Entra.
5. **Passage au partage SMB**, quand Alban aura créé `svc-fichectrl` (ticket GLPI) :
   - déposer `svc-fichectrl-ad-login` et `svc-fichectrl-ad-password` au Key Vault ;
   - passer `stockage = "smb"` ;
   - relancer l'étape 3.

## Dépendances : pourquoi la CI les construit

`rapidocr_onnxruntime` exige `opencv-python`, dont l'import échoue sur App Service faute de
`libGL`. La CI installe donc les dépendances dans `.python_packages` :
- `opencv-python-headless` à la place d'`opencv-python` ;
- RapidOCR sans ses dépendances (`requirements-ocr.txt`).

La Web App ne lance pas de build Oryx (`SCM_DO_BUILD_DURING_DEPLOYMENT=0`, `PYTHONPATH` pointé sur
`.python_packages`).

## Vérifications de recette

1. En navigation privée, l'URL répond par un 302 vers le login Microsoft. Un
   200 anonyme serait une faille, pas un succès.
2. Un compte hors du groupe qualité est refusé (erreur AADSTS50105).
3. `/api/health` est vert, ce qui prouve que le Key Vault est lu, que le réseau
   privé est traversé et que les six tables sont accessibles.
4. Scanner un carton d'une réception postérieure au 04/08 : le PO doit sortir.
   C'est le test qui aurait échoué avec `commandes_detaillees27`.
5. Les logs arrivent dans `log-platform-logs-prod`.

## Retour arrière

L'exécutable sur `A:\QUALITE` reste en place jusqu'à la recette. Un
`terraform destroy` sur ce dossier ne supprime que la Web App, son groupe de
ressources, ses identités et ses droits. Le plan et le réseau de FUSEAU ne sont
pas touchés.
