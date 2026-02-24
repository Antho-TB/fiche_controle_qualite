# Fiche de Contrôle Qualité Scanner

Application automatisée pour le service Qualité permettant de générer les fiches d'inspection de réception (format Excel) à partir d'un simple scan de code-barre (EAN/Ref).

## Nouvelles Fonctionnalités
- **Lecture intelligente des PDF** : Le système extrait désormais le numéro de commande (PO) depuis les Packing Lists glissées dans le dossier `data/packing_lists`.
- **Intégration API Sylob** : En utilisant le numéro de commande, l'outil interroge automatiquement Sylob (endpoint `API_LOT_PO`) pour récupérer le numéro de lot officiel, assurant une parfaite traçabilité.
- **Remplissage Excel Automatique** : La commande et le lot sont inscrits fidèlement dans le template Excel.

## Comment l'utiliser ?
Veuillez vous référer au fichier [NOTICE_UTILISATION.md](NOTICE_UTILISATION.md) pour les instructions détaillées destinées aux opérateurs.

Lancement facile via le script `LANCER_SCANNER.bat`.
