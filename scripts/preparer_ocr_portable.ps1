# Prepare les binaires OCR portables dans tools/, pour livraison dans le zip.
#
# A executer UNE FOIS sur le poste de developpement, avant de compiler l .exe.
# Telecharge tesseract (avec les langues anglais, francais et chinois simplifie)
# et poppler, puis les range dans tools/ a cote de l executable. Le module
# src/ocr_engine.py les detecte automatiquement.
#
# Rien n est installe sur le poste : tout reste dans le dossier du projet.

$ErrorActionPreference = "Stop"
$racine = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$outils = Join-Path $racine "tools"
$temp = Join-Path $env:TEMP "ocr_portable"

New-Item -ItemType Directory -Force -Path $outils, $temp | Out-Null

# --- poppler (rendu des pages PDF en images, requis par pdf2image) ---
$popplerZip = Join-Path $temp "poppler.zip"
$popplerUrl = "https://github.com/oschwartz10612/poppler-windows/releases/download/v24.08.0-0/Release-24.08.0-0.zip"
if (-not (Test-Path (Join-Path $outils "poppler\bin\pdftoppm.exe"))) {
    Write-Host "Telechargement de poppler..." -ForegroundColor Yellow
    Invoke-WebRequest -Uri $popplerUrl -OutFile $popplerZip
    Expand-Archive -Path $popplerZip -DestinationPath $temp -Force
    $bin = Get-ChildItem $temp -Recurse -Filter pdftoppm.exe | Select-Object -First 1
    if (-not $bin) { throw "pdftoppm.exe introuvable dans l archive poppler." }
    Copy-Item (Split-Path -Parent (Split-Path -Parent $bin.FullName)) `
        -Destination (Join-Path $outils "poppler") -Recurse -Force
    Write-Host "  -> poppler installe dans tools\poppler" -ForegroundColor Green
} else {
    Write-Host "poppler deja present." -ForegroundColor Gray
}

# --- tesseract ---
# Le paquet officiel UB-Mannheim est un installeur, non une archive. Le plus
# simple et le plus reproductible est de l installer une fois sur le poste de
# developpement, puis de copier son dossier dans tools\tesseract.
$sources = @(
    "C:\Program Files\Tesseract-OCR",
    "C:\Program Files (x86)\Tesseract-OCR",
    (Join-Path $env:LOCALAPPDATA "Programs\Tesseract-OCR")
)
$source = $sources | Where-Object { Test-Path (Join-Path $_ "tesseract.exe") } |
    Select-Object -First 1

if (-not $source) {
    Write-Host ""
    Write-Host "tesseract n est pas installe sur ce poste." -ForegroundColor Red
    Write-Host "Installer d abord (une seule fois) :" -ForegroundColor Yellow
    Write-Host "  winget install --id UB-Mannheim.TesseractOCR" -ForegroundColor Cyan
    Write-Host "En cochant les langues French et Chinese (Simplified), puis relancer ce script."
    exit 1
}

if (-not (Test-Path (Join-Path $outils "tesseract\tesseract.exe"))) {
    Write-Host "Copie de tesseract depuis $source..." -ForegroundColor Yellow
    Copy-Item $source -Destination (Join-Path $outils "tesseract") -Recurse -Force
}

$tessdata = Join-Path $outils "tesseract\tessdata"
foreach ($langue in @("eng", "fra", "chi_sim")) {
    $fichier = Join-Path $tessdata "$langue.traineddata"
    if (Test-Path $fichier) {
        Write-Host "  -> langue $langue presente" -ForegroundColor Green
    } else {
        Write-Host "  -> langue $langue MANQUANTE dans $tessdata" -ForegroundColor Red
        Write-Host "     Relancer l installeur tesseract en cochant cette langue."
    }
}

$taille = (Get-ChildItem $outils -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB
Write-Host ""
Write-Host ("tools/ pret : {0:N0} Mo, a inclure dans le zip de livraison." -f $taille) -ForegroundColor Cyan
