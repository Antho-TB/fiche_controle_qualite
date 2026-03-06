# Stratégie de Mise en Production - Fiche de Contrôle Qualité Scanner

Ce document définit la stratégie de déploiement pour l'application de scan pour le contrôle qualité. Il a été rédigé en respectant strictement les principes de résilience et de sécurité locaux, tout en conservant un alignement avec les standards de l'entreprise.

## 1. Architecture de Déploiement (Environnement Client)

L'application est conçue pour être exécutée localement sur les postes de travail Windows des opérateurs du service Qualité.

- **Point d'entrée** : L'opérateur extrait le fichier `Deploiement_Scanner_Qualite.zip` et lance l'exécutable `Scanner_Qualite.exe`.
- **Dépendances et Robustesse** : Application fully-packagée (standalone) via PyInstaller. Aucune installation de Python ou de librairies n'est requise sur le poste final limitant ainsi les risques liés à l'environnement.
- **Validation Pré-déploiement** : Avant toute mise à jour sur les postes des opérateurs, une régénération de l'exécutable (`pyinstaller`) suivie d'un packaging est obligatoire.

## 2. Résilience et Gestion des Erreurs (Fallback)

Conformément à nos principes de conception pour les environnements de production, l'application doit être robuste face aux indisponibilités des systèmes critiques.

- **API Sylob** : Si l'endpoint `API_LOT_PO` est inaccessible (time-out dépassé ou serveur injoignable), le système s'adapte en extrayant directement les informations depuis les Packing Lists au format PDF (mode de secours). En dernier recours, l'application propose une saisie manuelle courte.
- **Gestion des IHM** : L'application privilégie les interactions via API et la manipulation de documents locaux au lieu d'une navigation automatisée sur des interfaces ERP complexes et lourdes.
- **Time-out** : Toute requête ayant un échange avec une ressource réseau (API, ERP) possède un seuil d'abandon défini.

## 3. Sécurité et Gestion des Données

La confidentialité des accès et le bon fonctionnement de l'espace de stockage local sont essentiels.

- **Gestion des Secrets** : Le fichier `.env` contenant les identifiants et clés (notamment pour l'API Sylob) est strictement exclu du suivi de versions via `.gitignore`. Il doit être configuré manuellement et sécurisé sur chaque poste cible.
- **Rotation et Nettoyage** : Les fichiers de données en transit (notamment les PDF placés dans `1_Packing_Lists_A_Traiter`) doivent être archivés automatiquement après traitement pour ne pas saturer le dossier de l'opérateur.

## 4. Alignement avec les Standards TB-Groupe (Scénario Cloud)

Bien que l'application s'exécute actuellement en local, l'architecture reste prête pour une éventuelle migration de certains composants vers le Cloud (Azure), en respectant les politiques de gouvernance :

- **Région Azure** : Si une infrastructure cloud venait à intégrer le projet, son déploiement se ferait exclusivement sur la région `North Europe`.
- **Convention de Nommage** : Respect scrupuleux du format `<Prefix>-qualite-scanner-<Env>` (exemple : `func-qualite-scanner-prod`).
- **Tags** : Intégration systématique des tags `project` et `deployment`.
- **Infrastructure as Code** : Les ressources seraient déployées via les modules Terraform standards (comme `mod-landing-zone`).

> [!IMPORTANT]
> Instruction finale avant déploiement : L'application doit être minutieusement testée en condition de coupure réseau afin de certifier le fonctionnement du comportement de secours (fallback).
