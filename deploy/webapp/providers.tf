# =============================================================================
# [IAC] FICHE DE CONTROLE - FOURNISSEURS TERRAFORM
# =============================================================================
# Meme decoupage que FUSEAU (Data-Achat/deploy/terraform), dont ce projet
# reprend le patron d'hebergement :
#   - defaut      : shsv-prod, porte l'App Service
#   - management  : tb-management, porte le Key Vault kv-dtpf-prod, le puits de
#                   logs central et le state Terraform
# Pas de fournisseur dtpf : le peering shsv <-> dtpf existe deja et appartient
# au state FUSEAU. Le redeclarer ici ferait deux proprietaires pour une meme
# ressource, et le premier destroy de l'un casserait l'autre.
# =============================================================================

terraform {
  required_version = ">= 1.5"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.117"
    }
    azuread = {
      source  = "hashicorp/azuread"
      version = "~> 2.53"
    }
    time = {
      source  = "hashicorp/time"
      version = "~> 0.11"
    }
  }

  backend "azurerm" {
    resource_group_name  = "rg-platform-terraform-prod"
    storage_account_name = "stplatformtfstatestbprod"
    container_name       = "tfstates"
    key                  = "shsv-fichectrl.tfstate"
    subscription_id      = "70d5f67e-2e75-416d-a322-457493d18263"
    use_azuread_auth     = true
  }
}

provider "azurerm" {
  subscription_id = var.subscription_shsv
  features {}
}

provider "azurerm" {
  alias           = "management"
  subscription_id = var.subscription_management
  features {}
}

provider "azuread" {}
