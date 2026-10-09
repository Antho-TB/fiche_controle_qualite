-- =============================================================================
-- [SQL] Role PostgreSQL de la Web App Fiche de controle, LECTURE SEULE
-- =============================================================================
-- Base   : dtpf_sylob_prod (psql-dtpf-psql-prod)
-- Execute: par l'admin PostgreSQL (secrets dtpf-psql-admin-*-prod), APRES accord
--          ecrit d'Antho. Creation de ressource : jamais lance par un agent.
--
-- Pourquoi un role dedie : l'executable lit aujourd'hui le DWH avec le compte
-- nominatif d'Antho. Une application hebergee ne doit jamais porter un compte
-- nominatif (regle azure-tb), et ce role ne doit pouvoir QUE lire les six tables
-- dont la fiche a besoin (scoping du 03/09/2026, ADR scoping_roles_pg_dtpf_prod).
--
-- Mot de passe : genere hors de ce fichier et depose AU PREALABLE dans
-- kv-dtpf-prod sous psql-prod-fichectrl-app-password. psql le lit lui-meme au
-- Key Vault (\set avec backquotes ci-dessous) : il ne passe ni en argument de
-- ligne de commande (visible dans la liste des processus) ni dans un fichier.
--   $env:PGPASSWORD = az keyvault secret show --vault-name kv-dtpf-prod `
--     --name dtpf-psql-admin-password-prod --query value -o tsv
--   psql "host=psql-dtpf-psql-prod.postgres.database.azure.com dbname=dtpf_sylob_prod sslmode=require user=<admin>" `
--     -f deploy/webapp/sql/role_fichectrl_lecture.sql
--   Remove-Item Env:\PGPASSWORD
--
-- Rejouable : CREATE au premier passage, ALTER ensuite.
-- =============================================================================

\set ON_ERROR_STOP on
\set mot_de_passe `az keyvault secret show --vault-name kv-dtpf-prod --name psql-prod-fichectrl-app-password --query value -o tsv`

SELECT format('CREATE ROLE dtpf_fichectrl_app_prod LOGIN PASSWORD %L CONNECTION LIMIT 5', :'mot_de_passe')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dtpf_fichectrl_app_prod')
\gexec

SELECT format('ALTER ROLE dtpf_fichectrl_app_prod LOGIN PASSWORD %L CONNECTION LIMIT 5', :'mot_de_passe')
\gexec

-- Aucune ecriture possible, meme si un GRANT trop large arrive un jour.
ALTER ROLE dtpf_fichectrl_app_prod SET default_transaction_read_only = on;
ALTER ROLE dtpf_fichectrl_app_prod SET statement_timeout = '30s';

GRANT CONNECT ON DATABASE dtpf_sylob_prod TO dtpf_fichectrl_app_prod;
GRANT USAGE ON SCHEMA public TO dtpf_fichectrl_app_prod;
GRANT USAGE ON SCHEMA achat TO dtpf_fichectrl_app_prod;

-- Sortie MyReport. ATTENTION : si l'ETL MyReport supprime et recree une table,
-- le GRANT disparait avec elle. La sonde /api/health de l'application teste un
-- SELECT sur chacune de ces tables pour que la perte soit visible, pas silencieuse.
GRANT SELECT ON TABLE public.articles3            TO dtpf_fichectrl_app_prod;
GRANT SELECT ON TABLE public.commandes_detaillees TO dtpf_fichectrl_app_prod;
GRANT SELECT ON TABLE public.fournisseurs2        TO dtpf_fichectrl_app_prod;
GRANT SELECT ON TABLE public.tracabilite          TO dtpf_fichectrl_app_prod;

-- Domaine FUSEAU : lecture du seul suivi de conteneur.
GRANT SELECT ON TABLE achat.ot_transport          TO dtpf_fichectrl_app_prod;
GRANT SELECT ON TABLE achat.ot_transport_bl       TO dtpf_fichectrl_app_prod;

-- Controle : doit lister exactement six tables, toutes en SELECT.
SELECT table_schema, table_name, string_agg(privilege_type, ',') AS droits
FROM information_schema.role_table_grants
WHERE grantee = 'dtpf_fichectrl_app_prod'
GROUP BY 1, 2
ORDER BY 1, 2;
