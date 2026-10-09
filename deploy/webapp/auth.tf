# =============================================================================
# [IAC] FICHE DE CONTROLE - ENREGISTREMENT D'APPLICATION ENTRA ID
# =============================================================================
# Easy Auth exige un enregistrement d'application. Difference avec FUSEAU :
# l'acces peut etre restreint a un groupe (service qualite) en rendant
# l'attribution obligatoire sur le principal de service. Une fiche de controle
# reception engage la tracabilite produit : savoir QUI l'a produite compte.
# =============================================================================

data "azuread_client_config" "actuel" {}

locals {
  acces_restreint = var.groupe_utilisateurs_object_id != ""
}

resource "azuread_application" "fichectrl" {
  display_name     = "Fiche de controle reception - Qualite"
  owners           = [data.azuread_client_config.actuel.object_id]
  sign_in_audience = "AzureADMyOrg"

  web {
    redirect_uris = [
      "https://app-${var.prefix}-${var.project_code}-${var.environment}.azurewebsites.net/.auth/login/aad/callback",
    ]

    implicit_grant {
      id_token_issuance_enabled = true
    }
  }

  required_resource_access {
    # Microsoft Graph, User.Read delegue : suffisant pour identifier l'operateur.
    resource_app_id = "00000003-0000-0000-c000-000000000000"

    resource_access {
      id   = "e1fe6dd8-ba31-4d61-89e7-88639da4683d"
      type = "Scope"
    }
  }
}

resource "time_rotating" "secret_auth" {
  rotation_days = 300
}

resource "azuread_application_password" "fichectrl" {
  application_id    = azuread_application.fichectrl.id
  display_name      = "easy-auth-app-service"
  end_date_relative = "8760h"

  rotate_when_changed = {
    rotation = time_rotating.secret_auth.id
  }
}

resource "azuread_service_principal" "fichectrl" {
  client_id                    = azuread_application.fichectrl.client_id
  owners                       = [data.azuread_client_config.actuel.object_id]
  app_role_assignment_required = local.acces_restreint
}

# Role par defaut (id nul) : "acces a l'application", sans role metier.
resource "azuread_app_role_assignment" "groupe_qualite" {
  count               = local.acces_restreint ? 1 : 0
  app_role_id         = "00000000-0000-0000-0000-000000000000"
  principal_object_id = var.groupe_utilisateurs_object_id
  resource_object_id  = azuread_service_principal.fichectrl.object_id
}
