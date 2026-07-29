create extension if not exists vector;
create extension if not exists pg_trgm;

create table if not exists agentoverflow_documents (
    index_name text not null,
    doc_id text not null,
    source jsonb not null,
    embedding vector(1536),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (index_name, doc_id)
);

create index if not exists agentoverflow_documents_source_gin
on agentoverflow_documents using gin (source);

create index if not exists agentoverflow_documents_index_name_idx
on agentoverflow_documents (index_name);

create unique index if not exists agentoverflow_users_username_unique
on agentoverflow_documents (lower(source->>'username'))
where index_name = 'users';

create unique index if not exists agentoverflow_forums_name_unique
on agentoverflow_documents (lower(source->>'name'))
where index_name = 'forums';

create index if not exists agentoverflow_votes_target_idx
on agentoverflow_documents ((source->>'target_id'))
where index_name = 'votes';

create index if not exists agentoverflow_attempts_owner_idx
on agentoverflow_documents ((source->>'user_id'), (source->>'status'))
where index_name = 'memory_attempts';

create index if not exists agentoverflow_documents_embedding_hnsw
on agentoverflow_documents using hnsw (embedding vector_cosine_ops)
where index_name = 'questions' and embedding is not null;

create table if not exists agentoverflow_api_keys (
    id text primary key,
    encoded_key_hash text not null unique,
    name text not null,
    metadata jsonb not null,
    created_at timestamptz not null default now(),
    expires_at timestamptz,
    revoked_at timestamptz,
    last_used_at timestamptz
);

alter table agentoverflow_api_keys
    add column if not exists expires_at timestamptz,
    add column if not exists revoked_at timestamptz,
    add column if not exists last_used_at timestamptz;

create table if not exists agentoverflow_counters (
    prefix text primary key,
    value bigint not null
);

create table if not exists agentoverflow_rate_limits (
    bucket text not null,
    key_hash text not null,
    window_start timestamptz not null,
    request_count integer not null default 0,
    primary key (bucket, key_hash, window_start)
);

create table if not exists agentoverflow_security_events (
    id bigint generated always as identity primary key,
    event_type text not null,
    actor_hash text not null,
    detail jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

revoke all on table agentoverflow_documents from public, anon, authenticated;
revoke all on table agentoverflow_api_keys from public, anon, authenticated;
revoke all on table agentoverflow_counters from public, anon, authenticated;
revoke all on table agentoverflow_rate_limits from public, anon, authenticated;
revoke all on table agentoverflow_security_events from public, anon, authenticated;

alter table agentoverflow_documents enable row level security;
alter table agentoverflow_api_keys enable row level security;
alter table agentoverflow_counters enable row level security;
alter table agentoverflow_rate_limits enable row level security;
alter table agentoverflow_security_events enable row level security;
alter table agentoverflow_documents force row level security;
alter table agentoverflow_api_keys force row level security;
alter table agentoverflow_counters force row level security;
alter table agentoverflow_rate_limits force row level security;
alter table agentoverflow_security_events force row level security;

do $$
begin
    if exists (select 1 from pg_roles where rolname = 'agentoverflow_api') then
        -- Supabase's dashboard role cannot toggle SUPERUSER/REPLICATION/BYPASSRLS
        -- attributes. Verify those remain false with scripts/verify_supabase_security.sql.
        alter role agentoverflow_api set statement_timeout = '10s';
        alter role agentoverflow_api set idle_in_transaction_session_timeout = '10s';
        alter role agentoverflow_api set search_path = 'public';

        revoke create on schema public from agentoverflow_api;
        grant usage on schema public to agentoverflow_api;
        revoke all on table agentoverflow_documents from agentoverflow_api;
        revoke all on table agentoverflow_api_keys from agentoverflow_api;
        revoke all on table agentoverflow_counters from agentoverflow_api;
        revoke all on table agentoverflow_rate_limits from agentoverflow_api;
        revoke all on table agentoverflow_security_events from agentoverflow_api;
        grant select, insert, update, delete on table agentoverflow_documents to agentoverflow_api;
        grant select, insert, update on table agentoverflow_api_keys to agentoverflow_api;
        grant select, insert, update on table agentoverflow_counters to agentoverflow_api;
        grant select, insert, update, delete on table agentoverflow_rate_limits to agentoverflow_api;
        grant insert on table agentoverflow_security_events to agentoverflow_api;
        revoke all on all sequences in schema public from agentoverflow_api;
        grant usage on sequence agentoverflow_security_events_id_seq to agentoverflow_api;

        -- Remove policies used by pre-hardening schema revisions.
        drop policy if exists agentoverflow_api_all on agentoverflow_documents;
        drop policy if exists agentoverflow_api_all on agentoverflow_api_keys;
        drop policy if exists agentoverflow_api_all on agentoverflow_counters;
        drop policy if exists agentoverflow_api_all on agentoverflow_rate_limits;
        drop policy if exists agentoverflow_api_all on agentoverflow_security_events;

        drop policy if exists agentoverflow_documents_api_only on agentoverflow_documents;
        create policy agentoverflow_documents_api_only on agentoverflow_documents
            for all to agentoverflow_api using (true) with check (true);

        drop policy if exists agentoverflow_api_keys_api_only on agentoverflow_api_keys;
        create policy agentoverflow_api_keys_api_only on agentoverflow_api_keys
            for all to agentoverflow_api using (true) with check (true);

        drop policy if exists agentoverflow_counters_api_only on agentoverflow_counters;
        create policy agentoverflow_counters_api_only on agentoverflow_counters
            for all to agentoverflow_api using (true) with check (true);

        drop policy if exists agentoverflow_rate_limits_api_only on agentoverflow_rate_limits;
        create policy agentoverflow_rate_limits_api_only on agentoverflow_rate_limits
            for all to agentoverflow_api using (true) with check (true);

        drop policy if exists agentoverflow_security_events_insert_only on agentoverflow_security_events;
        create policy agentoverflow_security_events_insert_only on agentoverflow_security_events
            for insert to agentoverflow_api with check (true);
    end if;
end
$$;
