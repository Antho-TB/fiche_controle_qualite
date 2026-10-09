# =============================================================================
# [IAC] FICHE DE CONTROLE - VARIABLES
# =============================================================================

variable "subscription_shsv" {
  description = "Souscription qui porte l'App Service (services partages prod)."
  type        = string
}

variable "subscription_management" {
  description = "Souscription de management (Key Vault, logs, state Terraform)."
  type        = string
}

variable "location" {
  description = "Region Azure. Doit rester celle du PostgreSQL."
  type        = string
  default     = "northeurope"
}

variable "prefix" {
  description = "Prefixe Nubo de la souscription hote."
  type        = string
  default     = "shsv"
}

variable "project_code" {
  description = "Code projet, utilise dans tous les noms de ressources (aligne sur svc-fichectrl)."
  type        = string
  default     = "fichectrl"
}

variable "environment" {
  description = "Environnement cible."
  type        = string
  default     = "prod"
}

variable "python_version" {
  description = "Version Python de la Web App (standard TB : 3.11)."
  type        = string
  default     = "3.11"
}

# --- Reseau -----------------------------------------------------------------

variable "vnet_shsv_name" {
  description = "VNet spoke qui heberge le subnet d'integration de la Web App."
  type        = string
  default     = "vnet-shsv-network-prod"
}

variable "vnet_shsv_rg" {
  description = "Groupe de ressources du VNet spoke shsv."
  type        = string
  default     = "rg-shsv-network-prod"
}

variable "subnet_webapp_name" {
  description = "Subnet d'integration du plan FUSEAU, partage par toutes ses applications. Lu, jamais modifie."
  type        = string
  default     = "snet-shsv-network-3-prod"
}

variable "plan_partage_name" {
  description = "Plan App Service de FUSEAU, mutualise (decision du 09/10/2026)."
  type        = string
  default     = "plan-shsv-fuseau-prod"
}

variable "plan_partage_rg" {
  description = "Groupe de ressources du plan FUSEAU."
  type        = string
  default     = "rg-shsv-fuseau-prod"
}

# --- Base de donnees et secrets --------------------------------------------

variable "key_vault_name" {
  description = "Key Vault qui porte les credentials (RBAC active)."
  type        = string
  default     = "kv-dtpf-prod"
}

variable "key_vault_rg" {
  description = "Groupe de ressources du Key Vault."
  type        = string
  default     = "rg-dtpf-mgmt-prod"
}

variable "pg_host" {
  description = "FQDN du serveur PostgreSQL. Toujours le FQDN, jamais l'IP."
  type        = string
  default     = "psql-dtpf-psql-prod.postgres.database.azure.com"
}

variable "pg_database" {
  description = "Base de donnees cible."
  type        = string
  default     = "dtpf_sylob_prod"
}

variable "secret_login_pg" {
  description = <<-EOT
    Secret Key Vault du login PostgreSQL de l'application. Compte de service
    dedie en LECTURE seule (sql/role_fichectrl_lecture.sql), jamais le compte
    nominatif d'Antho utilise aujourd'hui par l'executable.
  EOT
  type        = string
  default     = "psql-prod-fichectrl-app-login"
}

variable "secret_password_pg" {
  description = "Secret Key Vault du mot de passe du compte de service."
  type        = string
  default     = "psql-prod-fichectrl-app-password"
}

# --- Ressources sur site (VPN site a site) ----------------------------------

variable "sylob_hote" {
  description = "IP de srv-erp. Le DNS interne n'est pas resolu depuis Azure (constat du 09/10/2026)."
  type        = string
  default     = "192.168.102.38"
}

variable "secret_sylob" {
  description = "Secret JSON des identifiants de l'API Sylob, partage avec MyReport (socle section 4)."
  type        = string
  default     = "tb-sylob-client"
}

variable "smb_serveur" {
  description = "IP de SRV-FILES-POM, cible DFS reelle du lecteur A: (dossier QUALITE). On vise le serveur, pas l'espace DFS."
  type        = string
  default     = "192.168.102.55"
}

variable "smb_partage" {
  description = "Partage SMB sur SRV-FILES-POM."
  type        = string
  default     = "PARTAGE"
}

variable "smb_dossier_racine" {
  description = "Dossier du controle reception. L'annee est ajoutee par l'application (2026, 2027...)."
  type        = string
  default     = "QUALITE/R4 ACHATS/Contrôle réception"
}

variable "secret_smb_login" {
  description = "Secret du login du compte de service AD svc-fichectrl."
  type        = string
  default     = "svc-fichectrl-ad-login"
}

variable "secret_smb_password" {
  description = "Secret du mot de passe du compte de service AD svc-fichectrl."
  type        = string
  default     = "svc-fichectrl-ad-password"
}

# --- Gemini (repli OCR) ------------------------------------------------------

variable "gcp_projet_gemini" {
  description = <<-EOT
    Projet GCP DEDIE a la fiche de controle, rattache au compte de facturation
    TB, avec son propre budget : le cout Gemini se lit par projet (decision du
    09/10/2026). A creer avant d'activer l'OCR. Authentification visee :
    federation d'identite depuis l'identite managee Azure, sans cle JSON.
  EOT
  type        = string
  default     = "tb-ai-fichectrl-prod"
}

variable "gcp_region_gemini" {
  description = "Region Vertex AI. Europe pour que les Packing Lists restent traitees dans l'UE."
  type        = string
  default     = "europe-west1"
}

variable "gemini_modele" {
  description = "Modele Gemini du repli OCR. Flash suffit pour relire une Packing List."
  type        = string
  default     = "gemini-2.5-flash"
}

# --- Acces utilisateurs -------------------------------------------------------

variable "groupe_utilisateurs_object_id" {
  description = <<-EOT
    Object id du groupe Entra ID autorise a ouvrir l'application (service
    qualite). Renseigne : seul ce groupe passe Easy Auth. Vide : tout le tenant
    TB passe, comme FUSEAU. Une fiche de controle qualite engage la
    tracabilite, le groupe est donc fortement recommande.
  EOT
  type        = string
  default     = ""
}

# --- Observabilite ----------------------------------------------------------

variable "log_analytics_name" {
  description = "Puits de logs central TB Groupe."
  type        = string
  default     = "log-platform-logs-prod"
}

variable "log_analytics_rg" {
  description = "Groupe de ressources du puits de logs central."
  type        = string
  default     = "rg-platform-logs-prod"
}

variable "tags" {
  description = "Tags obligatoires (policy de tags active sur le tenant)."
  type        = map(string)
}

variable "depot_github" {
  description = "Depot GitHub autorise a deployer (sujet de la federation OIDC)."
  type        = string
  default     = "Antho-TB/fiche_controle_qualite"
}
