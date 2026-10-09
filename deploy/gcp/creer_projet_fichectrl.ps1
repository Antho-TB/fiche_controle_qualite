# =============================================================================
# [OPS] Projet GCP dedie a la fiche de controle (Gemini et Drive partage)
# =============================================================================
# Decision du 09/10/2026 : un projet GCP par application, pour lire le cout
# Gemini projet par projet (Ops). Ce projet porte :
#   - l'API Vertex AI (repli de lecture des Packing Lists scannees) ;
#   - l'API Drive (depot des fiches tant que le partage SMB n'est pas ouvert) ;
#   - un compte de service unique, sa-fichectrl, dont la cle part DIRECTEMENT
#     au Key Vault kv-dtpf-prod (secret gcp-fichectrl-sa-key) puis est effacee
#     du disque.
#
# A lancer par Antho (creation de ressources), apres `gcloud auth login` avec
# son compte Google Workspace, et sous le compte Azure qui peut ecrire dans
# kv-dtpf-prod (meme profil que deployer_infra.ps1).
#
# Si la politique d'organisation interdit les cles de compte de service
# (iam.disableServiceAccountKeyCreation), l'etape 4 echoue : il faudra alors
# passer directement a la federation d'identite (voir src/gcp_auth.py).
#
# Usage : powershell -ExecutionPolicy Bypass -File deploy\gcp\creer_projet_fichectrl.ps1
# =============================================================================

$ErrorActionPreference = "Stop"
$Projet = "tb-ai-fichectrl-prod"
$Compte = "sa-fichectrl"
$Email = "$Compte@$Projet.iam.gserviceaccount.com"
$env:AZURE_CONFIG_DIR = Join-Path $HOME ".azure-admin"

function Confirmer([string]$Question) {
    return (Read-Host "$Question (o/N)") -match "^[oOyY]"
}

Write-Host "=== 1. Projet $Projet ===" -ForegroundColor Cyan
$existe = gcloud projects describe $Projet --format="value(projectId)" 2>$null
if (-not $existe) {
    if (-not (Confirmer "Creer le projet GCP $Projet ?")) { return }
    gcloud projects create $Projet --name="Fiche de controle reception" --labels=app=fiche-controle,equipe=data
}
Write-Host "Comptes de facturation disponibles :"
gcloud billing accounts list --format="table(name,displayName,open)"
$facturation = Read-Host "Identifiant du compte de facturation TB (billingAccounts/XXXXXX-XXXXXX-XXXXXX, sans le prefixe)"
gcloud billing projects link $Projet --billing-account=$facturation

Write-Host "=== 2. API ===" -ForegroundColor Cyan
gcloud services enable aiplatform.googleapis.com drive.googleapis.com --project=$Projet

Write-Host "=== 3. Compte de service ===" -ForegroundColor Cyan
$sa = gcloud iam service-accounts describe $Email --project=$Projet --format="value(email)" 2>$null
if (-not $sa) {
    gcloud iam service-accounts create $Compte --project=$Projet `
        --display-name="Fiche de controle (Web App Azure)"
}
gcloud projects add-iam-policy-binding $Projet --member="serviceAccount:$Email" `
    --role="roles/aiplatform.user" --condition=None | Out-Null
Write-Host "[SUCCES] $Email : roles/aiplatform.user."

Write-Host "=== 4. Cle du compte de service vers le Key Vault ===" -ForegroundColor Cyan
if (Confirmer "Generer une cle et la deposer dans kv-dtpf-prod/gcp-fichectrl-sa-key ?") {
    $fichier = Join-Path $env:TEMP ("sa_" + [guid]::NewGuid().ToString("N") + ".json")
    try {
        gcloud iam service-accounts keys create $fichier --iam-account=$Email --project=$Projet
        az keyvault secret set --vault-name kv-dtpf-prod --name gcp-fichectrl-sa-key `
            --file $fichier --content-type "application/json" `
            --tags projet=fiche-controle usage=drive-et-gemini --output none
        Write-Host "[SUCCES] Cle deposee au Key Vault."
    }
    finally {
        Remove-Item -Force -ErrorAction SilentlyContinue $fichier
    }
}

Write-Host "=== 5. Budget (alerte, ne coupe rien) ===" -ForegroundColor Cyan
if (Confirmer "Creer une alerte budgetaire a 20 EUR par mois sur ce projet ?") {
    gcloud billing budgets create --billing-account=$facturation `
        --display-name="fiche-controle mensuel" --budget-amount=20EUR `
        --filter-projects="projects/$Projet" `
        --threshold-rule=percent=0.5 --threshold-rule=percent=0.9 --threshold-rule=percent=1.0
}

Write-Host ""
Write-Host "Reste a faire a la main, dans Google Drive :" -ForegroundColor Yellow
Write-Host "  1. Creer le Drive partage 'Controle reception qualite' (ou reutiliser un existant)."
Write-Host "  2. Y ajouter $Email comme 'Gestionnaire de contenu'."
Write-Host "  3. Copier l'identifiant du dossier (fin de son URL) dans"
Write-Host "     deploy\webapp\variables.auto.tfvars : drive_dossier_id, puis gemini_actif = true."
Write-Host "  4. Relancer deploy\webapp\deployer_infra.ps1."
