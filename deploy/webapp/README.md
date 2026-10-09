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

## Prérequis avant le premier apply

1. **Droits sur le state** : `Storage Blob Data Contributor` sur
   `stplatformtfstatestbprod`. Antho l'a déjà depuis FUSEAU.
2. **Compte de service PostgreSQL en lecture seule** :
   ```powershell
   az keyvault secret set --vault-name kv-dtpf-prod --name psql-prod-fichectrl-app-login --value dtpf_fichectrl_app_prod
   az keyvault secret set --vault-name kv-dtpf-prod --name psql-prod-fichectrl-app-password --value "<secret genere, jamais commite>"
   ```
   Puis lancer `sql/role_fichectrl_lecture.sql` avec le compte admin (la
   procédure est dans l'en-tête du fichier). Le contrôle en fin de script doit
   lister exactement six tables, toutes en `SELECT`.
3. **Groupe Entra du service qualité** : renseigner son object id dans
   `variables.auto.tfvars` (`groupe_utilisateurs_object_id`). Si la variable
   reste vide, tout le tenant TB peut ouvrir l'application.
4. **Compte de service AD `svc-fichectrl`** (ticket GLPI, Alban) avec le droit
   de modifier `QUALITE\R4 ACHATS\Contrôle réception`. Antho dépose ensuite le
   login et le mot de passe dans `svc-fichectrl-ad-login` et
   `svc-fichectrl-ad-password`.

## Déroulé

```powershell
cd deploy/webapp
terraform init
terraform plan -out tfplan        # A RELIRE avant l'apply
terraform apply tfplan

$secret = terraform output -raw secret_auth_a_deposer
az webapp config appsettings set -g rg-shsv-fichectrl-prod -n app-shsv-fichectrl-prod `
  --settings MICROSOFT_PROVIDER_AUTHENTICATION_SECRET=$secret
Remove-Variable secret
```

Ensuite, reporter `cicd_azure_client_id`, `cicd_azure_tenant_id` et
`cicd_azure_subscription_id` dans les secrets GitHub du dépôt
`Antho-TB/fiche_controle_qualite`, puis créer l'environnement `production`.
La fédération OIDC attend le sujet `repo:<depot>:environment:production`.

## Code à écrire avant le premier déploiement

Le Terraform suppose les éléments suivants, qui **n'existent pas encore** :
- `src/web_app.py` : une application FastAPI avec une page de scan (un champ
  qui reçoit la saisie de la douchette, envoyée par Entrée), le dépôt de la
  Packing List, le téléchargement de la fiche, et `/api/health` qui teste un
  `SELECT` sur chacune des six tables ;
- `dwh_repository` et `sylob_api` doivent lire leurs paramètres dans
  l'environnement (`KEY_VAULT_NAME`, `PG_*`, `SYLOB_*`, `SMB_*`, `OCR_ACTIVE`)
  au lieu des constantes actuelles ;
- un module `depot_fichiers` doit lire les Packing Lists et écrire les fiches en
  SMB (`smbprotocol`), avec le dossier de l'année calculé et non figé sur 2026,
  et un repli vers le Drive derrière la même interface ;
- l'identité de l'opérateur (en-tête `X-MS-CLIENT-PRINCIPAL-NAME` injecté par
  Easy Auth) doit être inscrite sur la fiche et dans le journal ;
- `.github/workflows/deploy-azure.yml`, sur le modèle de Data-Achat.

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
