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

create table if not exists agentoverflow_api_keys (
    id text primary key,
    encoded_key_hash text not null unique,
    name text not null,
    metadata jsonb not null,
    created_at timestamptz not null default now()
);

create table if not exists agentoverflow_counters (
    prefix text primary key,
    value bigint not null
);
