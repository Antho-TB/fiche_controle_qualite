# Injection des secrets de l'API Sylob vers Key Vault Centralisé

data "azurerm_key_vault" "central_kv" {
  name                = "kv-tb-ia-agents-secrets"
  resource_group_name = "rg-tb-ia-agents"
}

variable "sylob_user" { type = string }
variable "sylob_pass" { type = string }
variable "sylob_unite_pers" { type = string }
variable "sylob_session_id" { type = string }
variable "sylob_base_url1" { type = string }

resource "azurerm_key_vault_secret" "sylob_user" {
  name         = "SYLOB-USER"
  value        = var.sylob_user
  key_vault_id = data.azurerm_key_vault.central_kv.id
}

resource "azurerm_key_vault_secret" "sylob_pass" {
  name         = "SYLOB-PASS"
  value        = var.sylob_pass
  key_vault_id = data.azurerm_key_vault.central_kv.id
}

resource "azurerm_key_vault_secret" "sylob_unite_pers" {
  name         = "SYLOB-UNITE-PERS"
  value        = var.sylob_unite_pers
  key_vault_id = data.azurerm_key_vault.central_kv.id
}

resource "azurerm_key_vault_secret" "sylob_session_id" {
  name         = "SYLOB-SESSION-ID"
  value        = var.sylob_session_id
  key_vault_id = data.azurerm_key_vault.central_kv.id
}

resource "azurerm_key_vault_secret" "sylob_base_url1" {
  name         = "SYLOB-BASE-URL1"
  value        = var.sylob_base_url1
  key_vault_id = data.azurerm_key_vault.central_kv.id
}
