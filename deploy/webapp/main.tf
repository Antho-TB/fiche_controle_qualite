# =============================================================================
# [IAC] FICHE DE CONTROLE - APP SERVICE, RESEAU, SECRETS, LOGS
# =============================================================================
# Le Scanner Qualite quitte l'executable PyInstaller copie sur A:\QUALITE pour
# une Web App unique : une seule version en service, deployee par CI/CD, et
# plus aucune identite Azure a gerer sur le poste de Flo (le poste n'est pas
# joint a Entra ID, ce qui a empeche Key Vault de fonctionner en production).
#
# Patron identique a FUSEAU : FastAPI derriere Easy Auth, integration VNet
# regionale, PostgreSQL prive joint par le peering shsv <-> dtpf deja en place
# (propriete du state FUSEAU), zone privee privatelink deja liee au spoke shsv.
#
# Sources : API Sylob sur site (donnee instantanee) en premier, DWH Azure (J-1)
# en complement et en repli. Les fiches sont deposees sur SRV-FILES-POM en SMB.
# Les deux hotes sur site sont joints par le VPN site a site, voir l'ADR du
# 09/10/2026.
# =============================================================================

locals {
  nom_base = "${var.prefix}-${var.project_code}-${var.environment}"
}

data "azurerm_client_config" "actuel" {}

data "azurerm_log_analytics_workspace" "logs_centraux" {
  provider            = azurerm.management
  name                = var.log_analytics_name
  resource_group_name = var.log_analytics_rg
}

data "azurerm_key_vault" "kv" {
  provider            = azurerm.management
  name                = var.key_vault_name
  resource_group_name = var.key_vault_rg
}

resource "azurerm_resource_group" "rg" {
  name     = "rg-${local.nom_base}"
  location = var.location
  tags     = var.tags
}

# -----------------------------------------------------------------------------
# RESEAU ET CALCUL MUTUALISES AVEC FUSEAU
# -----------------------------------------------------------------------------
# Decision du 09/10/2026 : la Web App tourne sur le plan B1 de FUSEAU. Toutes les
# applications d'un plan partagent son integration VNet : on reutilise donc le
# subnet snet-shsv-network-3-prod, sans le revendiquer. Plan et subnet restent
# la propriete du state FUSEAU (Data-Achat/deploy/terraform) : un destroy ou un
# changement de SKU cote FUSEAU touche aussi la fiche de controle.
#
# Chemins verifies le 09/10/2026 depuis la console Kudu de FUSEAU, meme reseau :
# PostgreSQL 172.31.2.4:5432, API Sylob 192.168.102.38:8443 (HTTP 200) et
# SRV-FILES-POM 192.168.102.55:445 sont joignables par le VPN site a site. Les
# noms internes (*.interne.tarrerias-bonjean.fr) ne sont PAS resolus : les
# hotes sur site sont donc passes par adresse IP en app settings.
data "azurerm_service_plan" "fuseau" {
  name                = var.plan_partage_name
  resource_group_name = var.plan_partage_rg
}

data "azurerm_subnet" "webapp" {
  name                 = var.subnet_webapp_name
  resource_group_name  = var.vnet_shsv_rg
  virtual_network_name = var.vnet_shsv_name
}

resource "azurerm_linux_web_app" "app" {
  name                = "app-${local.nom_base}"
  resource_group_name = azurerm_resource_group.rg.name
  location            = data.azurerm_service_plan.fuseau.location
  service_plan_id     = data.azurerm_service_plan.fuseau.id

  https_only                    = true
  virtual_network_subnet_id     = data.azurerm_subnet.webapp.id
  public_network_access_enabled = true

  site_config {
    always_on              = true
    vnet_route_all_enabled = true
    ftps_state             = "Disabled"
    minimum_tls_version    = "1.2"
    http2_enabled          = true

    application_stack {
      python_version = var.python_version
    }

    # Un worker : un ou deux postes reception, generation Excel en memoire.
    # Paquets construits par la CI dans .python_packages (pas de build Oryx :
    # il installerait opencv-python, dont l'import echoue faute de libGL).
    # Timeout large : la premiere lecture OCR d'un scan prend plusieurs
    # dizaines de secondes, ensuite le cache repond.
    app_command_line = "python -m gunicorn src.web_app:app --worker-class uvicorn.workers.UvicornWorker --workers 1 --timeout 300 --bind 0.0.0.0:8000"

    health_check_path                 = "/api/health"
    health_check_eviction_time_in_min = 5
  }

  app_settings = {
    "KEY_VAULT_NAME"     = var.key_vault_name
    "PG_HOST"            = var.pg_host
    "PG_DB"              = var.pg_database
    "PG_SSLMODE"         = "require"
    "PG_SECRET_LOGIN"    = var.secret_login_pg
    "PG_SECRET_PASSWORD" = var.secret_password_pg

    # CRITIQUE : interdit a azure_auth d'ouvrir une connexion navigateur. Sur
    # un serveur, elle bloquerait la requete jusqu'au timeout. L'identite
    # managee est prise par DefaultAzureCredential.
    "FICHE_CONTROLE_SANS_INTERACTION" = "1"

    # API Sylob sur site, joignable par le VPN : donnee instantanee, alors que
    # le DWH est une copie J-1. Hote en IP, le nom interne n'etant pas resolu.
    "SYLOB_ACTIVE" = "1"
    "SYLOB_HOTE"   = var.sylob_hote
    "SYLOB_SECRET" = var.secret_sylob

    # Depot des fiches : "drive" (repli en attendant le compte AD) ou "smb"
    # (partage qualite SRV-FILES-POM sous le compte de service svc-fichectrl).
    "STOCKAGE"            = var.stockage
    "DRIVE_DOSSIER_ID"    = var.drive_dossier_id
    "GCP_SECRET_SA"       = var.secret_gcp_sa
    "SMB_SERVEUR"         = var.smb_serveur
    "SMB_PARTAGE"         = var.smb_partage
    "SMB_DOSSIER_RACINE"  = var.smb_dossier_racine
    "SMB_SECRET_LOGIN"    = var.secret_smb_login
    "SMB_SECRET_PASSWORD" = var.secret_smb_password

    # Lecture des scans (schema valide le 09/10/2026) : texte natif, puis
    # RapidOCR (pip seul, pas de conteneur), puis Gemini en repli. Chaque valeur
    # lue est confirmee par Sylob ou le DWH avant d'atteindre la fiche.
    "OCR_ACTIVE"      = "1"
    "GEMINI_ACTIF"    = var.gemini_actif ? "1" : "0"
    "GEMINI_PROJET"   = var.gcp_projet_gemini
    "GEMINI_LOCATION" = var.gcp_region_gemini
    "GEMINI_MODELE"   = var.gemini_modele

    "WEBSITE_TIMEZONE"                    = "Europe/Paris"
    "SCM_DO_BUILD_DURING_DEPLOYMENT"      = "0"
    "PYTHONPATH"                          = "/home/site/wwwroot/.python_packages/lib/site-packages"
    "PYTHON_ENABLE_GUNICORN_MULTIWORKERS" = "false"
    "WEBSITE_DNS_SERVER"                  = "168.63.129.16"
  }

  identity {
    type = "SystemAssigned"
  }

  auth_settings_v2 {
    auth_enabled           = true
    require_authentication = true
    unauthenticated_action = "RedirectToLoginPage"
    default_provider       = "azureactivedirectory"
    require_https          = true

    active_directory_v2 {
      client_id                  = azuread_application.fichectrl.client_id
      tenant_auth_endpoint       = "https://login.microsoftonline.com/${data.azurerm_client_config.actuel.tenant_id}/v2.0"
      client_secret_setting_name = "MICROSOFT_PROVIDER_AUTHENTICATION_SECRET"
    }

    login {
      token_store_enabled = true
    }

    # Sonde de sante anonyme : etat de connexion a la base, aucune donnee metier.
    excluded_paths = ["/api/health"]
  }

  lifecycle {
    # Secret Easy Auth depose hors state par le pipeline (voir README).
    ignore_changes = [app_settings["MICROSOFT_PROVIDER_AUTHENTICATION_SECRET"]]
  }

  tags = var.tags
}

# -----------------------------------------------------------------------------
# SECRETS ET LOGS
# -----------------------------------------------------------------------------
# Portee au SECRET, pas au coffre : kv-dtpf-prod porte aussi les credentials
# admin PostgreSQL et ceux de MyReport. Un role au niveau du coffre donnerait a
# cette Web App la lecture de tout le reste.
locals {
  # Une attribution sur un secret qui n'existe pas encore echoue : les secrets
  # SMB ne sont lus qu'une fois le compte AD cree (stockage = "smb"), la cle
  # Google qu'une fois le projet GCP cree (Drive ou Gemini actif).
  secrets_lus = merge(
    {
      pg_login    = var.secret_login_pg
      pg_password = var.secret_password_pg
      sylob       = var.secret_sylob
    },
    var.stockage == "smb" ? {
      smb_login    = var.secret_smb_login
      smb_password = var.secret_smb_password
    } : {},
    var.stockage == "drive" || var.gemini_actif ? { gcp_sa = var.secret_gcp_sa } : {},
  )
}

resource "azurerm_role_assignment" "app_lit_ses_secrets" {
  for_each             = local.secrets_lus
  provider             = azurerm.management
  scope                = "${data.azurerm_key_vault.kv.id}/secrets/${each.value}"
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_linux_web_app.app.identity[0].principal_id
}

resource "azurerm_monitor_diagnostic_setting" "app_diag" {
  name                       = "diag-${azurerm_linux_web_app.app.name}"
  target_resource_id         = azurerm_linux_web_app.app.id
  log_analytics_workspace_id = data.azurerm_log_analytics_workspace.logs_centraux.id

  enabled_log {
    category = "AppServiceHTTPLogs"
  }

  enabled_log {
    category = "AppServiceConsoleLogs"
  }

  enabled_log {
    category = "AppServiceAppLogs"
  }

  metric {
    category = "AllMetrics"
    enabled  = true
  }
}
