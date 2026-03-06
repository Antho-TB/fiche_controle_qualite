# Fiche de Contrôle Qualité Scanner

Application automatisée pour le service Qualité permettant de générer les fiches d'inspection de réception (format Excel) à partir d'un simple scan de code-barre (EAN/Ref).

## Nouvelles Fonctionnalités
- **Lecture intelligente des PDF** : Le système extrait désormais le numéro de commande (PO) depuis les Packing Lists glissées dans le dossier `1_Packing_Lists_A_Traiter`.
- **Intégration API Sylob** : En utilisant le numéro de commande, l'outil interroge automatiquement Sylob (endpoint `API_LOT_PO`) pour récupérer le numéro de lot officiel, assurant une parfaite traçabilité.
- **Remplissage Excel Automatique** : La commande et le lot sont inscrits fidèlement dans le template Excel stocké dans `0_Modele_Et_Donnees`.
- **Version Exécutable Portable (Standalone)** : L'application est dorénavant compilée en `.exe` et packagée dans un `.zip` déployable sans installation.

## Comment l'utiliser ?
Veuillez extraire l'archive `Deploiement_Scanner_Qualite.zip` et double-cliquer sur `Scanner_Qualite.exe`.
