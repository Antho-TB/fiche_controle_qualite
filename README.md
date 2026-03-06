# Fiche de Contrôle Qualité Scanner

Application de bureau automatisée pour le service Qualité. Elle permet de générer instantanément des fiches d'inspection de réception (au format Excel) à partir d'un simple scan de code-barre (EAN/Ref).

---

## 🚀 Comment ça marche ? (Sous le capot)

L'application a été pensée pour être la plus invisible et automatique possible pour l'opérateur. Voici ce qui se passe lorsqu'un code-barre est scanné :

1. **Scan et Détection :** 
   L'opérateur "bip" un produit. Le scanner envoie le code article (EAN ou Référence interne) à l'application.

2. **Recherche de la Commande (PDF) :** 
   L'application va fouiller dans le dossier `1_Packing_Lists_A_Traiter` pour lire le contenu des PDF (les bons de livraison fournisseurs). Elle cherche intelligemment le numéro de la commande (le fameux "PO") lié à cet article.

3. **Interrogation de l'ERP (Sylob) :** 
   Une fois le "PO" trouvé, l'application se connecte directement à l'ERP Sylob (via son API `API_LOT_PO`). Elle lui demande : *"Quel est le numéro de lot officiel interne qui a été attribué à cette commande ?"*. Sylob lui répond en temps réel.

4. **Création de la Fiche (Excel) :** 
   L'application récupère le modèle vierge situé dans `0_Modele_Et_Donnees`, le duplique, et le remplit automatiquement avec :
   - L'article, 
   - Le numéro de Commande (PO),
   - Le numéro de Lot officiel.
   
5. **Sauvegarde :** 
   La nouvelle fiche toute prête est enregistrée dans le dossier `2_Fiches_Creees` avec la date et l'heure dans le nom du fichier. Il n'y a plus qu'à réaliser les contrôles qualité !

---

## 🛠️ Utilisation au Quotidien

L'application est **"Portable" (Standalone)** : elle ne nécessite aucune installation de programme (comme Python) sur l'ordinateur de l'opérateur.

1. Extrayez l'archive de déploiement `Deploiement_Scanner_Qualite.zip` sur votre PC ou sur un lecteur réseau partagé.
2. Double-cliquez sur l'exécutable **`Scanner_Qualite.exe`** pour lancer l'interface de scan.
3. Glissez vos bons de livraison PDF dans le dossier `1_Packing_Lists_A_Traiter`.
4. Scannez !

---

## 🏗️ Architecture et IT (Mise en Production)

Ce projet est conçu pour une exécution locale résiliente avec une capacité de secours déconnectée, tout en restant aligné avec les standards d'architecture d'entreprise.

### 1. Résilience et Secours (Fallback)
Conformément aux principes de conception de production, l'application gère les pannes réseau :
- **API Sylob Inaccessible** : Si le serveur de l'ERP est injoignable ou lent (timeout), le système ne plante pas. Il s'adapte en se basant uniquement sur la lecture du PDF, ou le cas échéant, sur la petite base de secours technique (`article.csv` située dans le dossier Modèle), voire propose une saisie courte manuelle.
- **Approche Orientée API** : Au lieu de simuler des clics lourds sur l'interface complexe de l'ERP (approche RPA fragile), l'outil dialogue directement avec les bases de données (API).

### 2. Sécurité et Gestion des Données
- **Gestion des Secrets** : Les identifiants de connexion à Sylob sont stockés dans un fichier caché `.env` (qui n'est jamais poussé sur Github par sécurité). Il doit être paramétré une seule fois sur la machine de production.
- **Rotation et Nettoyage** : Les fichiers temporaires (PDF d'entrée) doivent être archivés (ou supprimés) régulièrement après traitement pour ne pas saturer le dossier de l'opérateur.

### 3. Alignement Cloud (Scénario Azure Futur)
Bien que l'application s'exécute localement à 100%, l'architecture reste prête pour une éventuelle migration de certains composants vers le Cloud (Azure) :
- **Région Azure** : Déploiement dans la région `North Europe` (politique groupe).
- **Convention de Nommage** : Respect du format `<Prefix>-qualite-scanner-<Env>` (exemple `func-qualite-scanner-prod`).
- **Tags d'entreprise** : Intégration systématique de `project` et `deployment`.

---

## 🐛 Historique de Résolution et Traçabilité

Afin d'assurer la traçabilité des modifications, voici l'historique des différents correctifs techniques appliqués à l'outil lors de la V2 :

1. **Correction des Dépendances (RequestsDependencyWarning)**
   - L'erreur venait de versions incompatibles de `urllib3` et `chardet` par défaut.
   - Les versions ont été strictement verrouillées (Pinnage) dans le fichier `requirements.txt` pour garantir la stabilité de l'exécutable sur tous les postes.

2. **Gestion robuste de la Base de Secours (article.csv)**
   - Initialement, l'absence du fichier CSV local de secours faisait complètement planter l'application à l'ouverture.
   - `src/data_loader.py` a été assoupli pour simplement déclencher un `WARNING` non bloquant. Le logiciel tente alors l'interrogation de l'API en direct sans s'arrêter.
   - Ajout au fichier CSV des colonnes `lot` et `po` afin d'avoir une capacité de secours déconnectée fiable sur les champs vitaux de l'entreprise.

3. **Environnement Packagé Standardisé (PyInstaller)**
   - Le système initial demandait des installations lourdes de Python sur chaque PC métier.
   - L'algorithme a été migré avec succès en un `.exe` unique et autonome. La gestion des Path Python et des ressources temporelles générées par le `.exe` (dans les dossiers temporaires Data Windows) ont été corrigés pour retrouver dynamiquement les dossiers métiers `1_Packing_Lists_...` et `2_Fiches_Creees`.

> [!IMPORTANT]
> Avant un grand déploiement inter-équipes, il est recommandé de tester l'application en simulant une coupure réseau pour confirmer la fluidité du comportement de secours (fallback).
