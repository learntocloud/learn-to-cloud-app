-- Bootstrap PostgreSQL Entra roles after Terraform switches the server admin.
--
-- Run this as the dedicated PostgreSQL Microsoft Entra admin against the
-- postgres database. Required psql variables:
--   database_name         Target application database, for example learntocloud
--   api_role              API managed identity name, for example id-ltc-api-dev
--   api_object_id         API managed identity principal ID
--   migration_role        Migration service principal or managed identity name
--   migration_object_id   Migration principal object ID
--
-- Example:
--   psql "host=<server>.postgres.database.azure.com dbname=postgres sslmode=require user=<admin-group>" \
--     -v database_name=learntocloud \
--     -v api_role=id-ltc-api-dev \
--     -v api_object_id=<api-principal-id> \
--     -v migration_role=<migration-principal-name> \
--     -v migration_object_id=<migration-principal-object-id> \
--     -f infra/postgres-bootstrap.sql

\set ON_ERROR_STOP on

\if :{?database_name}
\else
  \echo 'Missing required psql variable: database_name'
  \quit 1
\endif

\if :{?api_role}
\else
  \echo 'Missing required psql variable: api_role'
  \quit 1
\endif

\if :{?api_object_id}
\else
  \echo 'Missing required psql variable: api_object_id'
  \quit 1
\endif

\if :{?migration_role}
\else
  \echo 'Missing required psql variable: migration_role'
  \quit 1
\endif

\if :{?migration_object_id}
\else
  \echo 'Missing required psql variable: migration_object_id'
  \quit 1
\endif

SELECT pg_catalog.pgaadauth_create_principal_with_oid(
    :'api_role',
    :'api_object_id',
    'service',
    false,
    false
)
WHERE NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = :'api_role'
);

SELECT pg_catalog.pgaadauth_create_principal_with_oid(
    :'migration_role',
    :'migration_object_id',
    'service',
    false,
    false
)
WHERE NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = :'migration_role'
);

SET app.api_role = :'api_role';
SET app.api_object_id = :'api_object_id';
SET app.migration_role = :'migration_role';
SET app.migration_object_id = :'migration_object_id';

DO $$
DECLARE
    api_role text := current_setting('app.api_role');
    api_object_id text := current_setting('app.api_object_id');
    migration_role text := current_setting('app.migration_role');
    migration_object_id text := current_setting('app.migration_object_id');
BEGIN
    EXECUTE format(
        'SECURITY LABEL FOR "pgaadauth" ON ROLE %I IS %L',
        api_role,
        'aadauth,oid=' || api_object_id || ',type=service'
    );
    EXECUTE format(
        'SECURITY LABEL FOR "pgaadauth" ON ROLE %I IS %L',
        migration_role,
        'aadauth,oid=' || migration_object_id || ',type=service'
    );
END
$$;

\connect :database_name

SET app.api_role = :'api_role';
SET app.migration_role = :'migration_role';

GRANT CONNECT ON DATABASE :"database_name" TO :"api_role";
GRANT CONNECT, CREATE ON DATABASE :"database_name" TO :"migration_role";

GRANT USAGE ON SCHEMA public TO :"api_role";
GRANT USAGE, CREATE ON SCHEMA public TO :"migration_role";

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO :"api_role";
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO :"api_role";

GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO :"migration_role";
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO :"migration_role";

ALTER DEFAULT PRIVILEGES FOR ROLE :"migration_role" IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO :"api_role";
ALTER DEFAULT PRIVILEGES FOR ROLE :"migration_role" IN SCHEMA public
    GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO :"api_role";

DO $$
DECLARE
    api_role text := current_setting('app.api_role');
BEGIN
    EXECUTE format('ALTER ROLE %I NOCREATEDB NOCREATEROLE', api_role);
    EXECUTE format('REVOKE azure_pg_admin FROM %I', api_role);
EXCEPTION
    WHEN undefined_object THEN
        NULL;
END
$$;

DO $$
DECLARE
    migration_role text := current_setting('app.migration_role');
    object record;
BEGIN
    FOR object IN
        SELECT schemaname, tablename
        FROM pg_catalog.pg_tables
        WHERE schemaname = 'public'
    LOOP
        EXECUTE format(
            'ALTER TABLE %I.%I OWNER TO %I',
            object.schemaname,
            object.tablename,
            migration_role
        );
    END LOOP;

    FOR object IN
        SELECT sequence_schema, sequence_name
        FROM information_schema.sequences
        WHERE sequence_schema = 'public'
    LOOP
        EXECUTE format(
            'ALTER SEQUENCE %I.%I OWNER TO %I',
            object.sequence_schema,
            object.sequence_name,
            migration_role
        );
    END LOOP;
END
$$;
