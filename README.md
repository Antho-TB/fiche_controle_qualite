# Fiche de Contrôle Qualité Scanner

Application automatisée pour le service Qualité permettant de générer les fiches d'inspection de réception (format Excel) à partir d'un simple scan de code-barre (EAN/Ref).

## Nouvelles Fonctionnalités
- **Lecture intelligente des PDF** : Le système extrait désormais le numéro de commande (PO) depuis les Packing Lists glissées dans le dossier `1_Packing_Lists_A_Traiter`.
- **Intégration API Sylob** : En utilisant le numéro de commande, l'outil interroge automatiquement Sylob (endpoint `API_LOT_PO`) pour récupérer le numéro de lot officiel, assurant une parfaite traçabilité.
- **Remplissage Excel Automatique** : La commande et le lot sont inscrits fidèlement dans le template Excel stocké dans `0_Modele_Et_Donnees`.
- **Version Exécutable Portable (Standalone)** : L'application est dorénavant compilée en `.exe` et packagée dans un `.zip` déployable sans installation.

## Comment l'utiliser ?
Veuillez extraire l'archive `Deploiement_Scanner_Qualite.zip` et double-cliquer sur `Scanner_Qualite.exe`.

---

## Architecture et Mise en Production

Ce projet est conçu pour une exécution locale résiliente avec une capacité de secours déconnectée, tout en restant aligné avec les standards d'architecture d'entreprise.

### 1. Déploiement (Environnement Client)
L'application est exécutée localement sur les postes Windows du service Qualité.
- **Point d'entrée** : L'opérateur extrait `Deploiement_Scanner_Qualite.zip` et lance l'exécutable `Scanner_Qualite.exe`.
- **Dépendances** : Application "Standalone" (PyInstaller). Aucune installation Python requise sur le poste final limitant ainsi les risques liés à l'environnement.
- **Validation** : Avant toute mise à jour, une régénération de l'exécutable (`pyinstaller`) suivie d'un packaging est obligatoire.

### 2. Résilience et Secours (Fallback)
Conformément aux principes de conception de production, l'application gère les pannes réseau:
- **API Sylob Inaccessible** : Si le serveur est injoignable (timeout), le système bascule sur la lecture du PDF (`1_Packing_Lists_A_Traiter`) pour extraire le PO ou demande une saisie courte manuelle.
- **IHM vs API** : Privilégie la manipulation via API et PDF au lieu des interactions lourdes dans le navigateur (RPA).

### 3. Sécurité et Gestion des Données
- **Gestion des Secrets** : Le fichier `.env` (identifiants Sylob) est ignoré dans Git. Il doit être paramétré manuellement sur la machine de production.
- **Nettoyage** : Les fichiers temporaires (PDF dans `1_Packing_Lists_A_Traiter`) doivent être gérés/archivés pour ne pas saturer le disque.

### 4. Alignement Cloud (Scénario Azure Futur)
Si des composants sont migrés vers Azure dans le futur, ils respecteront :
- **Région Azure** : Déploiement en région `North Europe`.
- **Convention de Nommage** : `<Prefix>-qualite-scanner-<Env>` (exemple `func-qualite-scanner-prod`).
- **Tags d'entreprise** : Intégration systématique de `project` et `deployment`.

> [!IMPORTANT]
> L'application doit être minutieusement testée en coupant le réseau (VPN ou direct) pour confirmer le bon fonctionnement de la saisie manuelle et du scan PDF déconnecté.
