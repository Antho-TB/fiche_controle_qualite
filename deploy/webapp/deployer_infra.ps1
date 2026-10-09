# =============================================================================
# [OPS] Deploiement de l'infrastructure de la Web App Fiche de controle
# =============================================================================
# A lancer par Antho, dans une fenetre PowerShell dediee, sous le compte
# abezille@tbgroupefr.onmicrosoft.com : c'est le seul a porter a la fois le
# droit d'ecrire les secrets de kv-dtpf-prod (Key Vault Administrator) et celui
# de lire le state Terraform (Storage Blob Data Contributor). Le compte cloud
# a.bezille@tb-groupe.fr n'a ni l'un ni l'autre, et sa session CLI ne porte pas
# de MFA, exige pour toute ecriture Azure (constate le 09/10/2026).
#
# Chaque etape demande confirmation. Le script est rejouable : une etape deja
# faite est detectee et sautee.
#
# Ordre : lancer d'abord deploy\gcp\creer_projet_fichectrl.ps1 et renseigner
# drive_dossier_id dans variables.auto.tfvars. Avec stockage = "drive" et un
# dossier vide, l'application refuse de demarrer (erreur nommee, voulue).
#
# Prerequis : VPN TB actif (le role PostgreSQL se pose sur la base privee),
# Terraform, Azure CLI, gh (GitHub CLI) connecte, venv du projet installe.
#
# Usage, depuis la racine du depot :
#   powershell -ExecutionPolicy Bypass -File deploy\webapp\deployer_infra.ps1
# =============================================================================

$ErrorActionPreference = "Stop"
$CompteAttendu = "abezille@tbgroupefr.onmicrosoft.com"
$Tenant = "7c5e7e59-bf9f-42bf-87ae-f7b39ed22594"
$Racine = (Resolve-Path "$PSScriptRoot\..\..").Path
$Python = Join-Path $Racine ".venv\Scripts\python.exe"
$DossierTf = Join-Path $Racine "deploy\webapp"

function Confirmer([string]$Question) {
    $reponse = Read-Host "$Question (o/N)"
    return $reponse -match "^[oOyY]"
}

function Etape([string]$Titre) {
    Write-Host ""
    Write-Host "=== $Titre ===" -ForegroundColor Cyan
}

# Profil Azure CLI separe : n'affecte ni tes autres terminaux ni les sessions
# Claude, qui restent sur ton compte quotidien.
$env:AZURE_CONFIG_DIR = Join-Path $HOME ".azure-admin"

Etape "1. Connexion Azure sous $CompteAttendu"
$compte = ""
try { $compte = az account show --query user.name -o tsv 2>$null } catch { }
if ($compte -ne $CompteAttendu) {
    Write-Host "Connexion avec $CompteAttendu. Valide le MFA dans le navigateur."
    az login --tenant $Tenant --scope "https://management.core.windows.net//.default" | Out-Null
    $compte = az account show --query user.name -o tsv
}
if ($compte -ne $CompteAttendu) { throw "Connecte en '$compte' au lieu de $CompteAttendu." }
az account set --subscription "management"
Write-Host "[SUCCES] Connecte en $compte."

Etape "2. Secrets et role PostgreSQL en lecture seule"
Write-Host "Simulation d'abord (aucune ecriture) :"
& $Python (Join-Path $DossierTf "appliquer_role_fichectrl.py") --creer-secrets --dry-run
if ($LASTEXITCODE -ne 0) { throw "La simulation du role a echoue (VPN actif ?)." }
if (Confirmer "Creer les secrets manquants et appliquer le role dtpf_fichectrl_app_prod ?") {
    & $Python (Join-Path $DossierTf "appliquer_role_fichectrl.py") --creer-secrets
    if ($LASTEXITCODE -ne 0) { throw "Application du role en echec." }
}

Etape "3. Terraform"
Push-Location $DossierTf
try {
    terraform init -input=false
    if ($LASTEXITCODE -ne 0) { throw "terraform init en echec." }
    terraform plan -input=false -out tfplan
    if ($LASTEXITCODE -ne 0) { throw "terraform plan en echec." }
    Write-Host "RELIS le plan ci-dessus : seules des creations doivent apparaitre," -ForegroundColor Yellow
    Write-Host "aucune modification du plan ni du reseau FUSEAU." -ForegroundColor Yellow
    if (Confirmer "Appliquer ce plan ?") {
        terraform apply -input=false tfplan
        if ($LASTEXITCODE -ne 0) { throw "terraform apply en echec." }
    } else { return }

    Etape "4. Secret Easy Auth (hors state)"
    $app = terraform output -raw nom_application
    $rg = "rg-shsv-fichectrl-prod"
    $secret = terraform output -raw secret_auth_a_deposer
    az webapp config appsettings set -g $rg -n $app --subscription "shsv-prod" `
        --settings "MICROSOFT_PROVIDER_AUTHENTICATION_SECRET=$secret" --output none
    Remove-Variable secret
    Write-Host "[SUCCES] Secret Easy Auth depose sur $app."

    Etape "5. Identifiants de deploiement GitHub (OIDC, aucune cle)"
    $depot = "Antho-TB/fiche_controle_qualite"
    gh api --method PUT "repos/$depot/environments/production" --silent
    gh secret set AZURE_CLIENT_ID --repo $depot --env production --body (terraform output -raw cicd_azure_client_id)
    gh secret set AZURE_TENANT_ID --repo $depot --env production --body (terraform output -raw cicd_azure_tenant_id)
    gh secret set AZURE_SUBSCRIPTION_ID --repo $depot --env production --body (terraform output -raw cicd_azure_subscription_id)
    gh variable set DEPLOIEMENT_ACTIF --repo $depot --body "true"
    Write-Host "[SUCCES] Environnement production et secrets OIDC poses sur $depot."
    Write-Host ""
    Write-Host "URL de l'application : $(terraform output -raw url_application)"
    Write-Host "Etape suivante : lancer le workflow 'Deploiement Fiche de controle' sur GitHub."
}
finally {
    Remove-Item -ErrorAction SilentlyContinue (Join-Path $DossierTf "tfplan")
    Pop-Location
}
