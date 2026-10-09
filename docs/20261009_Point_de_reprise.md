# Point de reprise : fiche de contrôle, fin de journée du 09/10/2026

À lire en premier à la reprise. Il complète l'ADR
`claude/.ai_memory/decisions_log/20261009_fiche_controle_webapp_azure.md` (le pourquoi) et le
runbook `deploy/webapp/README.md` (le comment).

## Où on en est, en une phrase

L'application web est codée, testée (33 tests, CI verte) et poussée sur `main`. **Rien n'est
encore déployé sur Azure** : il reste trois actions manuelles d'Antho, puis la recette avec Flo.
En production, Flo utilise toujours `Scanner_Qualite.exe` du 28/04.

## Reprendre ici, dans l'ordre

| # | Action | Qui | Comment | État |
|---|---|---|---|---|
| 1 | Créer le groupe Entra **`sg-team-qualite`** (Sécurité, Attribué), membres Flo et Antho sous leurs comptes `@tbgroupefr.onmicrosoft.com`. Prévenir Nubo du préfixe `sg-team-`. | Antho | Portail Azure, Entra ID, Groupes, Nouveau groupe | **À faire** |
| 2 | Reporter l'ID d'objet du groupe dans `deploy/webapp/variables.auto.tfvars` (`groupe_utilisateurs_object_id`) | Antho ou Claude | Une ligne | **À faire** |
| 3 | Sur le Drive partagé « Fiche de Controle », passer `compteserve@…` d'**Administrateur** à **Gestionnaire de contenu** | Antho | Gérer les membres | **À faire** |
| 4 | `deploy\gcp\creer_projet_fichectrl.ps1` : API Vertex AI et Drive, rôle `roles/aiplatform.user`, clé au Key Vault, alerte budgétaire de 20 € | Antho | Voir le README. Être connecté à Azure en `abezille@tbgroupefr.onmicrosoft.com` (profil `$HOME\.azure-admin`) | **À faire** |
| 5 | `deploy\webapp\deployer_infra.ps1`, **VPN actif** : rôle PostgreSQL, `terraform plan` à relire puis `apply`, secret Easy Auth, environnement GitHub | Antho | Chaque étape demande confirmation | **À faire** |
| 6 | Premier déploiement : relancer le workflow GitHub « Déploiement Fiche de contrôle » | Antho ou Claude | Il vérifie que le commit servi est le bon et que l'accès anonyme est refusé | Après 5 |
| 7 | Tester Gemini sur les 4 Packing Lists scannées que l'OCR n'exploite pas (`1_Packing_Lists_A_Traiter/archives`, 0 caractère natif) | Claude | Possible dès que la clé `gcp-fichectrl-sa-key` est au coffre | Après 4 |
| 8 | Recette avec Flo | Antho et Flo | `docs/20261009_Recette_WebApp_Flo.md` | Après 6 |
| 9 | Après un go de Flo : retirer `Scanner_Qualite.exe` et le `.env` de `A:\QUALITE\R4 ACHATS\Contrôle réception\2026\Contrôle TB` | Antho | Accord écrit requis | Après 8 |
| 10 | Quand Alban aura créé `svc-fichectrl` : secrets `svc-fichectrl-ad-login` et `-password` au coffre, `stockage = "smb"`, relancer l'étape 5 | Antho | Ticket GLPI envoyé le 09/10 | En attente d'Alban |

## Ce qui a été fait le 09/10

- **Commandes** : `commandes_detaillees27` ne bouge plus depuis le 04/08. On lit maintenant
  `public.commandes_detaillees`, alimentée chaque nuit (`c94edef`).
- **Ordre des sources corrigé sur données réelles** : le DWH choisit le PO, et l'API Sylob donne
  le lot de ce PO en temps réel. Interrogée par le seul EAN, Sylob rendait une réception soldée
  (00147459 au lieu de 00184449 pour l'article 10120214).
- **Application web** : FastAPI et une page HTML aux couleurs du design system TB (couche
  corporate). Le scan se fait entièrement au clavier. La fiche Excel est générée en mémoire,
  déposée puis téléchargée.
- **Dépôt des fichiers** : local (poste), SMB (SRV-FILES-POM, cible) ou **Drive partagé**, le
  repli en service tant que le compte AD n'existe pas.
- **Lecture des Packing Lists** : texte natif, puis RapidOCR, puis Gemini. Mesure sur 5 scans :
  tesseract 0, RapidOCR 1. Ce sont les règles d'extraction propres à chaque fournisseur qui
  bloquent, d'où le repli Gemini, qui renvoie des lignes structurées.
- **Infrastructure** : Terraform de la Web App sur le plan FUSEAU, script du rôle PostgreSQL en
  lecture seule, script de déploiement, script GCP, workflow GitHub (tests, déploiement,
  vérification).
- **Réseau vérifié depuis Azure**, par la console Kudu de FUSEAU : PostgreSQL, API Sylob
  (192.168.102.38:8443) et SRV-FILES-POM (192.168.102.55:445) sont joignables. Le DNS interne
  n'est pas résolu, d'où l'usage des IP.
- **GCP** (créé par Antho) : projet `qualitefichecontrole`, compte
  `compteserve@qualitefichecontrole.iam.gserviceaccount.com`, Drive partagé « Fiche de Controle »
  (`0ACZ6_BwnqSS_Uk9PVA`).
- **Tickets GLPI pour Alban**, envoyés :
  - `docs/20261009_ticket_GLPI_svc-fichectrl.md` (compte de service AD) ;
  - `docs/20261009_ticket_GLPI_UPN_tb-groupe.md` (uniformisation des identités Google, AD et
    Entra).

## Pièges à connaître avant de reprendre

- **Comptes Azure d'Antho** :
  - `a.bezille@tb-groupe.fr` est un doublon cloud. Sa session CLI n'a pas de MFA, il n'a pas
    accès au state Terraform et ne peut pas écrire de secret. Il lit seulement `kv-dtpf-prod`,
    grâce à une attribution directe faite le 09/10.
  - **`abezille@tbgroupefr.onmicrosoft.com`** est le vrai compte, synchronisé depuis l'AD.
    C'est avec lui qu'on applique l'infra.
- **Connexion `az` partagée** : toutes les sessions Claude et les terminaux utilisent la même. Un
  `az logout` dans une session déconnecte les autres. Les scripts de déploiement utilisent un
  profil séparé, `$HOME\.azure-admin`.
- **opencv** : ne jamais laisser `opencv-python` (non headless) partir sur App Service. La CI
  construit les dépendances et vérifie ce point.
- **H6** (lot fournisseur) sort du gabarit FOR-ACH-30-2 : la qualité doit la valider pendant la
  recette.
- **Lancement local** : `.claude/launch.json` (non versionné) démarre l'application sur le port
  8765 avec un dépôt dans le scratchpad.
