# =============================================================================
# [IAC] FICHE DE CONTROLE - IDENTITE DE DEPLOIEMENT GITHUB ACTIONS (OIDC)
# =============================================================================
# Copie du patron FUSEAU : identite de CI distincte d'Easy Auth, federation
# OIDC sans secret, droit limite a la seule Web App.
#
# Piege du sujet : le job de deploiement declarera `environment: production`,
# donc le `sub` du jeton vaut repo:<depot>:environment:production et non
# repo:<depot>:ref:refs/heads/main. Si l'environnement est retire du workflow,
# c'est cette ressource qu'il faut corriger.
# =============================================================================

resource "azuread_application" "cicd" {
  display_name     = "GitHub Actions - Fiche de controle (${var.depot_github})"
  owners           = [data.azuread_client_config.actuel.object_id]
  sign_in_audience = "AzureADMyOrg"
}

resource "azuread_service_principal" "cicd" {
  client_id = azuread_application.cicd.client_id
  owners    = [data.azuread_client_config.actuel.object_id]
}

resource "azuread_application_federated_identity_credential" "cicd_environnement" {
  application_id = azuread_application.cicd.id
  display_name   = "github-actions-fichectrl-production"
  description    = "Deploiement depuis l'environnement production du depot ${var.depot_github}."
  audiences      = ["api://AzureADTokenExchange"]
  issuer         = "https://token.actions.githubusercontent.com"
  subject        = "repo:${var.depot_github}:environment:production"
}

# Website Contributor sur la seule Web App : publier et redemarrer, rien d'autre.
resource "azurerm_role_assignment" "cicd_deploie_lapplication" {
  scope                = azurerm_linux_web_app.app.id
  role_definition_name = "Website Contributor"
  principal_id         = azuread_service_principal.cicd.object_id
}
