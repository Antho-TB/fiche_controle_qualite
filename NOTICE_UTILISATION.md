# 📖 NOTICE D'UTILISATION - SCANNER QUALITÉ

Cet outil permet de générer automatiquement vos fiches d'inspection qualité (Excel) à l'aide d'une simple douchette.

---

## 🛠️ ÉTAPE 1 : Préparation (Optionnelle)
*Si vous avez un fichier PDF de type "Packing List" avec la commande fournisseur :*
1. Copiez votre fichier PDF.
2. Collez-le dans le dossier `data/packing_lists`.
*(L'outil lira automatiquement le N° de Commande depuis le PDF, puis interrogera Sylob pour récupérer le N° de Lot officiel).*


## 🚀 ÉTAPE 2 : Lancement
1. Allez dans le dossier du scanner Qualité.
2. **Double-cliquez** sur le fichier **`LANCER_SCANNER.bat`** (celui avec l'icône d'engrenage).
3. Une fenêtre noire s'ouvre : c'est normal. Ne la fermez pas tout de suite.

## 📇 ÉTAPE 3 : Contrôle au Scanner
1. Prenez votre produit.
2. Cliquez une fois avec votre souris à l'intérieur de la fenêtre noire pour être sûr qu'elle est "active".
3. **Scannez le code-barre** de l'article avec votre douchette.
4. L'outil va reconnaitre l'article et créer instantanément la Fiche d'Inspection Excel !

## 📁 ÉTAPE 4 : Où trouver ma Fiche Excel ?
- Allez dans le dossier **`outputs/`**.
- Vous y trouverez votre modèle Excel rempli, avec la bonne référence, la désignation, la date, et éventuellement la Commande et le Lot si vous aviez mis un PDF !

## 🛑 ÉTAPE 5 : Terminer
1. Quand vous avez fini de scanner tous vos articles, tapez simplement le mot **`STOP`** (puis Entrée) dans la fenêtre noire.
2. Le système vous demandera : *"Voulez-vous archiver les Packing Lists ?"*
   - Tapez **`O`** (puis Entrée) pour ranger automatiquement les PDF utilisés.
   - Tapez **`N`** (puis Entrée) si vous en avez encore besoin demain.
3. La fenêtre se ferme. C'est terminé !

---
*En cas de problème (code inconnu), vérifiez que l'article figure bien dans Sylob ou dans votre fichier de secours (article.csv).*
