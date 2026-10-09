# Recette de la fiche de contrôle web avec Flo (service qualité)

**But :** valider sur de vraies réceptions que l'application web peut remplacer `Scanner_Qualite.exe`.
**Durée :** 1 h environ, au poste de réception, avec des colis réels du jour.
**Participants :** Flo (qualité), Antho (Data).
**Prérequis :** infrastructure appliquée et workflow vert (voir `deploy/webapp/README.md`). Flo
est membre du groupe Entra qualité.

L'exécutable reste sur `A:\QUALITE` pendant toute la recette : en cas de blocage, Flo le relance
comme avant.

## 1. Accès

| # | Action | Attendu | OK / KO |
|---|---|---|---|
| 1.1 | Flo ouvre l'URL de l'application dans son navigateur | Page de connexion Microsoft | |
| 1.2 | Elle se connecte avec son compte (aujourd'hui en `@tbgroupefr.onmicrosoft.com`, voir le ticket identités) | Page « Contrôle réception », son identité en haut | |
| 1.3 | Une personne hors du groupe qualité tente d'ouvrir l'URL | Accès refusé | |
| 1.4 | Badges d'état en tête de page | Sylob, DWH, dossier qualité et Packing Lists en vert | |

## 2. Scan et fiche, cas nominal

| # | Action | Attendu | OK / KO |
|---|---|---|---|
| 2.1 | Scanner l'EAN13 d'une unité d'un colis du jour | Article, PO, lot Sylob et fournisseur proposés en moins de 3 s, avec la source de chaque valeur | |
| 2.2 | Entrée sur « Générer la fiche » | Fiche téléchargée **et** déposée dans le dossier du jour ; le curseur revient sur le champ de scan | |
| 2.3 | Ouvrir la fiche | Mise en page FOR-ACH-30-2 intacte ; date, référence, désignation, PO, lot et fournisseur en rouge | |
| 2.4 | Scanner un **EAN14 carton** (PCB) du même article | Même article reconnu (« EAN14_PCB »), jamais un article voisin | |
| 2.5 | Enchaîner 5 colis sans souris (douchette, Entrée, Entrée) | Aucun clic nécessaire | |

## 3. Cas difficiles

| # | Action | Attendu | OK / KO |
|---|---|---|---|
| 3.1 | Article avec plusieurs commandes ouvertes | Liste des commandes candidates (fournisseur, quantité, état de réception) ; le choix d'une commande remplit son lot Sylob | |
| 3.2 | **Réception saisie dans Sylob le jour même** | Lot Sylob présent : il vient de l'API Sylob en temps réel, pas du DWH (J-1) | |
| 3.3 | Code inconnu (étiquette fournisseur quelconque) | Message « Code inconnu », aucune fiche générée | |
| 3.4 | Correspondance approximative | Case « Je confirme… » obligatoire avant la génération | |
| 3.5 | Déposer une Packing List **scannée** (image) | Statut OK ou PARTIEL dans la liste, lu par OCR ou par Gemini, avec le nombre d'articles | |
| 3.6 | Lot fournisseur différent du lot Sylob | Les deux lots apparaissent distinctement sur la fiche (G6 et H6) | |

## 4. Validation qualité de la fiche

| # | Point | Décision de Flo |
|---|---|---|
| 4.1 | Cellule **H6** « Lot frn : … » (sort du gabarit d'origine) : emplacement acceptable ? | |
| 4.2 | Rangement des fiches : Drive partagé (provisoire) puis `A:\QUALITE\...\2_Fiches_Creees` (cible) | |
| 4.3 | Nom des fichiers `Fiche_<ref>_<lot>_<horodatage>.xlsx` : convient ? | |

## 5. Décision

- [ ] **Go** : l'exécutable et le `.env` historique sont retirés de `A:\QUALITE` (par Antho,
  après accord écrit), et la fiche web devient l'outil officiel.
- [ ] **Go sous réserve** : corrections listées ci-dessous, puis nouvelle recette partielle.
- [ ] **No go** : motif.

Remarques de Flo :

&nbsp;
