# =============================================================================
# [IAC] FICHE DE CONTROLE - SORTIES
# =============================================================================

output "url_application" {
  description = "URL a communiquer au service qualite."
  value       = "https://${azurerm_linux_web_app.app.default_hostname}"
}

output "nom_application" {
  description = "Nom de la Web App, cible du pipeline de deploiement."
  value       = azurerm_linux_web_app.app.name
}

output "identite_application" {
  description = "Principal de l'identite managee de la Web App."
  value       = azurerm_linux_web_app.app.identity[0].principal_id
}

output "acces_restreint_au_groupe" {
  description = "Vrai si seul le groupe qualite peut ouvrir l'application."
  value       = local.acces_restreint
}

output "secret_auth_a_deposer" {
  description = "Secret Easy Auth, a deposer dans MICROSOFT_PROVIDER_AUTHENTICATION_SECRET par le pipeline."
  value       = azuread_application_password.fichectrl.value
  sensitive   = true
}

output "cicd_azure_client_id" {
  description = "A reporter dans le secret AZURE_CLIENT_ID du depot GitHub."
  value       = azuread_application.cicd.client_id
}

output "cicd_azure_tenant_id" {
  description = "A reporter dans le secret AZURE_TENANT_ID du depot GitHub."
  value       = data.azurerm_client_config.actuel.tenant_id
}

output "cicd_azure_subscription_id" {
  description = "A reporter dans le secret AZURE_SUBSCRIPTION_ID du depot GitHub."
  value       = var.subscription_shsv
}
