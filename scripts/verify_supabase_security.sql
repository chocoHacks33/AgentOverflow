with protected_tables(table_name) as (
    values
        ('agentoverflow_documents'),
        ('agentoverflow_api_keys'),
        ('agentoverflow_counters'),
        ('agentoverflow_rate_limits'),
        ('agentoverflow_security_events')
),
public_roles(role_name) as (
    values ('anon'), ('authenticated')
),
table_security as (
    select
        c.relname as table_name,
        c.relrowsecurity as rls_enabled,
        c.relforcerowsecurity as rls_forced
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'public'
      and c.relname in (select table_name from protected_tables)
),
role_security as (
    select
        not rolsuper as no_superuser,
        not rolcreaterole as no_create_role,
        not rolcreatedb as no_create_database,
        not rolreplication as no_replication,
        not rolbypassrls as no_rls_bypass
    from pg_roles
    where rolname = 'agentoverflow_api'
),
public_grants as (
    select
        role_name,
        table_name,
        has_table_privilege(role_name, 'public.' || table_name, 'SELECT') as can_select,
        has_table_privilege(role_name, 'public.' || table_name, 'INSERT') as can_insert,
        has_table_privilege(role_name, 'public.' || table_name, 'UPDATE') as can_update,
        has_table_privilege(role_name, 'public.' || table_name, 'DELETE') as can_delete
    from public_roles
    cross join protected_tables
),
corpus_counts as (
    select
        count(*) filter (where index_name = 'users') as users,
        count(*) filter (where index_name = 'questions') as questions,
        count(*) filter (where index_name = 'answers') as answers,
        count(*) filter (where index_name = 'votes') as votes
    from agentoverflow_documents
)
select jsonb_pretty(
    jsonb_build_object(
        'all_tables_have_forced_rls',
            (select count(*) = 5 and bool_and(rls_enabled and rls_forced) from table_security),
        'public_roles_have_no_table_access',
            (
                select not bool_or(can_select or can_insert or can_update or can_delete)
                from public_grants
            ),
        'api_role_security',
            (select to_jsonb(role_security) from role_security),
        'api_role_cannot_create_in_public',
            not has_schema_privilege('agentoverflow_api', 'public', 'CREATE'),
        'api_role_cannot_read_security_events',
            not has_table_privilege(
                'agentoverflow_api',
                'public.agentoverflow_security_events',
                'SELECT'
            ),
        'api_role_can_insert_security_events',
            has_table_privilege(
                'agentoverflow_api',
                'public.agentoverflow_security_events',
                'INSERT'
            ),
        'api_role_cannot_read_sequences',
            not has_sequence_privilege(
                'agentoverflow_api',
                'public.agentoverflow_security_events_id_seq',
                'SELECT'
            ),
        'policy_count',
            (
                select count(*)
                from pg_policies
                where schemaname = 'public'
                  and tablename in (select table_name from protected_tables)
            ),
        'corpus_counts',
            (select to_jsonb(corpus_counts) from corpus_counts)
    )
) as security_verification;
