# Ticket GLPI : uniformiser les identités Google Workspace, AD et Entra ID

**Destinataire :** Alban
**Demandeur :** Anthony Bezille (Data)
**Priorité :** normale. Ce ticket ne bloque rien aujourd'hui, mais la gêne augmente à chaque nouvelle application Azure.
**Catégorie :** Active Directory / Entra ID / Google Workspace

---

**Titre :** Une seule identité par salarié (prenom-initiale.nom@tb-groupe.fr) dans l'AD, Entra ID et Google Workspace

Bonjour Alban,

En déployant les applications Data sur Azure (FUSEAU, puis la fiche de contrôle réception), j'ai
constaté que les identités des salariés ne sont pas alignées entre nos trois annuaires. Voici ce
que j'ai relevé le 09/10, **en lecture seule**, dans Entra ID et dans les attributs AD que Entra
Connect y recopie, puis ce que je propose.

## 1. Les trois annuaires aujourd'hui

| Annuaire | Rôle | Identifiant d'un salarié (exemple : Marlène Montbrizon) |
|---|---|---|
| **AD sur site** `interne.tarrerias-bonjean.fr` | Session Windows, partages (SRV-FILES-POM), source de la synchro Entra | `mmontbrizon` (sAMAccountName), UPN `mmontbrizon@interne.tarrerias-bonjean.fr` |
| **Entra ID** (tenant tbgroupefr) | Azure, applications métier (FUSEAU), Microsoft 365 | `mmontbrizon@tbgroupefr.onmicrosoft.com` |
| **Google Workspace** `tb-groupe.fr` | Messagerie Gmail, Drive, Google Cloud | `m.montbrizon@tb-groupe.fr` (format de l'adresse à confirmer) |

Trois identifiants différents pour la même personne, et a priori trois mots de passe : Windows
(AD), Google, et Entra (celui de l'AD si la synchronisation des mots de passe est active).

## 2. Ce que j'ai constaté

**a. L'identifiant Microsoft n'est pas l'adresse mail (cause confirmée).**
Les 162 comptes synchronisés par Entra Connect (dernière synchro le 09/10 à 11h) ont **tous**
l'UPN AD `@interne.tarrerias-bonjean.fr`. Ce domaine n'est pas vérifiable dans Entra, donc Entra
Connect le remplace par `@tbgroupefr.onmicrosoft.com`. Le domaine `tb-groupe.fr` est pourtant
**vérifié** dans le tenant. Conséquence : pour ouvrir FUSEAU, Marlène et Maxence doivent saisir
une adresse onmicrosoft qu'ils ne connaissent pas, leur adresse habituelle étant refusée.

**b. L'attribut mail est vide dans l'AD pour la plupart des comptes.**
137 comptes synchronisés sur 162 n'ont aucun mail. Sur les 25 qui en ont un, 23 sont en
`@tb-groupe.fr` et 2 sont encore sur l'ancien domaine `@tarrerias-bonjean.fr`. Rien ne relie donc
le compte AD à la boîte Gmail de la personne.

**c. Deux conventions de nommage cohabitent.**
- AD : initiale et nom collés (`vberthucat`, `pbernard`) ;
- Google : initiale, point, nom (`v.berthucat@`, `P.Bernard@` avec majuscules).

La correspondance est mécanique dans 22 cas sur 25. Les exceptions sont les homonymes, numérotés
dans l'AD (`mbrun1`, `adasilva1`) : il faut une table de correspondance validée, pas une règle
automatique.

**d. 7 personnes ont en plus un compte cloud créé à la main à leur adresse @tb-groupe.fr.**
Ce compte coexiste avec leur compte synchronisé, ce qui en fait des doublons. Si on aligne l'UPN AD
sur l'adresse mail, Entra Connect rencontre un doublon : la synchro de la personne échoue, ou
Entra lui attribue un identifiant de secours aléatoire.

| Personne | Compte cloud @tb-groupe.fr | Licences sur le cloud | Compte(s) synchronisé(s) |
|---|---|---|---|
| Anthony Bezille | `a.bezille@` | 2 | `abezille@`, `admin.abezille@` |
| Emmanuelle Georgeon | `e.georgeon@` | 1 | `egeorgeon@` |
| Guillaume Houillon | `g.houillon@` | 1 | `ghouillon@`, `admin.ghouillon@` (désactivés) |
| Julien Bégon | `j.begon@` | 0 | `jbegon@` |
| Rémi Printemps | `r.printemps@` | **3** | `rprintemps@` |
| Jérémy Reis | `j.reis@` | 1 | `jreis@` |
| Samuel Sellier | `s.sellier@` | 1 | `ssellier@`, `admin.ssellier@` |

**e. Les licences Microsoft sont posées sur les doublons.** Seuls 2 comptes synchronisés ont une
licence. Les autres licences sont sur les comptes cloud : il faudra les déplacer avant de retirer
un doublon.

**f. La synchro remonte des comptes qui n'ont rien à faire dans Entra.**
- 35 comptes **désactivés** dans l'AD (départs) sont encore synchronisés.
- Des **comptes partagés** de poste ou de machine : `trcariste1` à `5`, `prepa1` à `4`,
  `Conditionnement1`, `laser3030`, `lasert6000`, `L500`, `DMP70`, `BE3`.
- Des **comptes système Windows NT / IIS** : `IUSR_SERV_NT01`, `IWAM_SERV_NT01`. Ils ne devraient
  pas avoir d'identité cloud.

**g. Comptes de Nubo, à ne pas toucher.** `Admin-eplateforme@`, `admin-crachdi@`,
`Admin-jpolycarpe@`, `shsv.service_account@`, `dtpf.service_account@` sont aussi en
@tb-groupe.fr. Ce sont des comptes d'administration et de service, pas des personnes.

## 3. Cible proposée

**Une identité par salarié, `prenom-initiale.nom@tb-groupe.fr`, identique partout, avec l'AD comme
source unique** (arrivées, départs, changements de nom) :

1. **AD** : ajouter le suffixe UPN `tb-groupe.fr`, puis pour chaque salarié UPN = mail =
   l'adresse Gmail. L'ouverture de session Windows ne change pas (`INTERNE\compte`).
2. **Entra ID** : Entra Connect recopie l'UPN et le mail. Le compte garde son identifiant interne,
   donc les groupes, licences, rôles Azure et droits FUSEAU restent en place.
3. **Google Workspace** : faire d'Entra le fournisseur d'identité de Google, avec l'application
   d'entreprise « Google Cloud / G Suite Connector by Microsoft » (SSO SAML et provisionnement
   automatique). Résultat : un seul mot de passe et un seul MFA, et un départ désactivé dans l'AD
   coupe aussi Gmail et Drive. L'alternative, Google Cloud Directory Sync depuis l'AD, synchronise
   les comptes mais garde deux authentifications.
4. **Périmètre de synchro** : limiter Entra Connect aux OU des personnes. Exclure les comptes
   désactivés, les comptes de poste partagés et les comptes système.

## 4. Déroulé suggéré

1. **Inventaire et table de correspondance** compte AD ↔ adresse Gmail, validée à la main pour les
   homonymes. Je peux la préparer côté Entra si tu m'exportes la liste des utilisateurs Google
   (console d'administration, export CSV).
2. **Pilote** sur 2 ou 3 personnes sans doublon (Marlène, Maxence) :
   - suffixe UPN `tb-groupe.fr`, UPN et mail AD = adresse Gmail ;
   - synchro delta ;
   - vérifier la connexion à FUSEAU avec l'adresse habituelle.
3. **Doublons (tableau du 2.d)**, une personne à la fois :
   - recenser ce que porte le compte cloud (licences, groupes, rôles Azure, attributions
     d'applications, OneDrive) ;
   - le reporter sur le compte synchronisé ;
   - renommer le compte cloud (`prenom.nom.cloud@tbgroupefr.onmicrosoft.com`) et le désactiver ;
   - aligner ensuite l'UPN AD. On ne supprime le compte cloud qu'après un mois sans incident.
4. **Généralisation** en lot (`Set-ADUser -UserPrincipalName ... -EmailAddress ...`), hors doublons.
5. **Nettoyage du périmètre de synchro** (point 2.f).
6. **Google Workspace** : SSO et provisionnement depuis Entra, à planifier une fois les identifiants
   alignés. Avant, il faut confirmer côté console Google le format exact des adresses et la
   présence éventuelle d'alias.

## 5. Communication aux utilisateurs

« À partir du JJ/MM, connectez-vous aux applications Microsoft avec votre adresse habituelle
prenom.nom@tb-groupe.fr. Votre mot de passe Windows ne change pas. »

## 6. Ce que je n'ai pas pu vérifier

- La console d'administration Google Workspace (format exact des adresses, alias, groupes) : je
  n'y ai pas accès.
- Le mode d'authentification d'Entra Connect (synchronisation du hachage des mots de passe ou
  authentification directe).
- Les OU actuellement synchronisées.

Merci,
Anthony
