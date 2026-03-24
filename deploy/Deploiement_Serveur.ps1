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

# 2. Liste des éléments essentiels à copier
$foldersToCopy = @("0_Modele_Et_Donnees", "1_Packing_Lists_A_Traiter", "2_Fiches_Creees")
$filesToCopy = @(".env", "dist\Scanner_Qualite.exe")

# --- Nettoyage des anciennes versions Python ---
$oldItems = @("src", "requirements.txt", "LANCER_SCANNER.bat", "data", "outputs")
foreach ($old in $oldItems) {
    $oldPath = "$dest\$old"
    if (Test-Path $oldPath) {
        Remove-Item $oldPath -Recurse -Force
        Write-Host "  -> Ancien élément $old supprimé." -ForegroundColor Gray
    }
}

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

# On cache le fichier .env
$hiddenItems = @(".env")
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
Write-Host "Votre collègue n'a plus qu'à double-cliquer sur 'Scanner_Qualite.exe' dans:"
Write-Host "$dest"
Write-Host "Appuyez sur une touche pour quitter..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
