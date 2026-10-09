# Ticket GLPI : compte de service pour la fiche de contrôle réception

**Destinataire :** Alban
**Demandeur :** Anthony Bezille (Data)
**Priorité :** normale
**Catégorie :** Active Directory / Droits sur les partages

---

**Titre :** Créer un compte de service AD `svc-fichectrl` avec droit d'écriture sur le dossier Contrôle réception

Bonjour Alban,

L'outil de fiche de contrôle réception, utilisé par le service qualité, va passer
d'un exécutable posé sur le partage à une application web hébergée sur Azure.
Pour déposer les fiches Excel dans le dossier habituel de la qualité, l'application
a besoin d'un compte de service AD dédié.

**Besoin**

1. Créer le compte de service **`svc-fichectrl`** dans l'AD
   `interne.tarrerias-bonjean.fr` :
   - mot de passe qui n'expire pas, ou expiration annuelle si la politique
     l'impose (dans ce cas, merci de me prévenir avant l'échéance) ;
   - pas d'ouverture de session interactive, pas de boîte mail ;
   - description : « Application Fiche de contrôle réception (Azure), contact
     A. Bezille ».

2. Lui donner les droits NTFS et de partage suivants, sur **SRV-FILES-POM** :
   - **Modification** (lecture, écriture, création, sans contrôle total) sur
     `\\SRV-FILES-POM\PARTAGE\QUALITE\R4 ACHATS\Contrôle réception`, héritée par
     les sous-dossiers, pour que les années suivantes (2027...) soient couvertes
     sans nouvelle demande ;
   - **aucun autre droit**, ni sur le reste de `QUALITE` ni ailleurs.

3. Me transmettre le mot de passe **hors GLPI** (Bitwarden Send ou en main
   propre). Je le dépose moi-même dans le coffre Azure `kv-dtpf-prod` ; il ne
   sera écrit nulle part ailleurs.

**Ce qui n'est pas nécessaire**

Aucune ouverture réseau. J'ai vérifié le 09/10 depuis Azure : le port 445 de
SRV-FILES-POM (192.168.102.55) et l'API Sylob (192.168.102.38:8443) sont déjà
joignables par le VPN site à site.

**Pour information**

L'application se connectera directement à SRV-FILES-POM, par adresse IP, et non
par l'espace DFS `\\interne.tarrerias-bonjean.fr\tb-groupe`, parce que les noms
internes ne sont pas résolus depuis Azure. Si le dossier QUALITE change un jour de
serveur, merci de me prévenir.

Merci,
Anthony
