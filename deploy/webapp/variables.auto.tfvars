# Valeurs de production. Aucun secret ici : les credentials PostgreSQL viennent
# du Key Vault, le secret Easy Auth est genere par Terraform.

subscription_shsv       = "cef4660c-cb19-43f7-b3f3-c6575a4f836a"
subscription_management = "70d5f67e-2e75-416d-a322-457493d18263"

location     = "northeurope"
prefix       = "shsv"
project_code = "fichectrl"
environment  = "prod"

# A renseigner avant l'apply : object id du groupe Entra du service qualite.
groupe_utilisateurs_object_id = ""

# Tag owner volontairement absent : la policy tag-owner-a refuse toute adresse
# mail (constat FUSEAU du 03/09/2026, remonte a Nubo).
tags = {
  project    = "FicheControle-Qualite"
  deployment = "IaC"
}
