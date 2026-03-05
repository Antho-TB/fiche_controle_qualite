# Script de deploiment vers le serveur cible

$source = (Get-Location).Path
$dest = "A:\QUALITE\R4 ACHATS\Contrôle réception\2026\Contrôle TB"

Write-Host "DEPLOIEMENT DE L'APPLICATION SCANNER QUALITE" -ForegroundColor Cyan
Write-Host "=============================================="

# 1. Création du dossier cible s'il n'existe pas
if (-not (Test-Path $dest)) {
    New-Item -ItemType Directory -Path $dest -Force | Out-Null
    Write-Host "Création du dossier cible: $dest" -ForegroundColor Green
}

# 2. Liste des éléments essentiels à copier (on ignore .git, .venv, tasks etc.)
$foldersToCopy = @("src", "data", "outputs")
$filesToCopy = @("LANCER_SCANNER.bat", ".env", "requirements.txt")

Write-Host "`nCopie des fichiers vers le serveur..." -ForegroundColor Yellow

foreach ($folder in $foldersToCopy) {
    if (Test-Path "$source\$folder") {
        Copy-Item -Path "$source\$folder" -Destination "$dest\$folder" -Recurse -Force
        Write-Host "  -> Dossier $folder copié."
    }
}

foreach ($file in $filesToCopy) {
    if (Test-Path "$source\$file") {
        Copy-Item -Path "$source\$file" -Destination "$dest\$file" -Force
        Write-Host "  -> Fichier $file copié."
    }
}

# 3. Masquer les fichiers techniques pour l'utilisateur
Write-Host "`nCréation de l'interface métier (masquage du code)..." -ForegroundColor Yellow

# On cache src, .env et requirements.txt
$hiddenItems = @("src", ".env", "requirements.txt")
foreach ($item in $hiddenItems) {
    $targetPath = "$dest\$item"
    if (Test-Path $targetPath) {
        # Modification des attributs pour rendre le fichier/dossier caché
        $fileObj = Get-Item $targetPath
        $fileObj.Attributes = $fileObj.Attributes -bor [System.IO.FileAttributes]::Hidden
    }
}

# --- Fin du script ---

Write-Host "`n=============================================="
Write-Host "DEPLOIEMENT TERMINE AVEC SUCCES !" -ForegroundColor Green
Write-Host "Votre collègue n'a plus qu'à double-cliquer sur 'LANCER_SCANNER.bat' dans:"
Write-Host "$dest"
Write-Host "Appuyez sur une touche pour quitter..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
