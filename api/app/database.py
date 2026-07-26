from elasticsearch import AsyncElasticsearch

from app.config import settings
from app.local_store import LocalElasticsearch
from app.supabase_store import SupabasePostgres

es_client: AsyncElasticsearch | LocalElasticsearch | SupabasePostgres | None = None


async def init_es() -> AsyncElasticsearch | LocalElasticsearch | SupabasePostgres:
    """Initialize the storage client (called at app startup)."""
    global es_client
    backend = settings.storage_backend.lower().strip()
    if backend == "supabase":
        es_client = SupabasePostgres(
            settings.supabase_database_url,
            min_size=settings.supabase_pool_min_size,
            max_size=settings.supabase_pool_max_size,
            auto_migrate=settings.supabase_auto_migrate,
        )
    elif settings.use_local_backend or settings.elasticsearch_url.startswith("local://"):
        es_client = LocalElasticsearch(seed_demo_data=settings.seed_demo_data)
    else:
        es_client = AsyncElasticsearch(
            settings.elasticsearch_url,
            api_key=settings.elasticsearch_api_key,
            request_timeout=30,
            max_retries=3,
            retry_on_timeout=True,
        )
    return es_client


async def close_es():
    """Close the Elasticsearch client (called at app shutdown)."""
    global es_client
    if es_client:
        await es_client.close()
        es_client = None


def get_es() -> AsyncElasticsearch | LocalElasticsearch | SupabasePostgres:
    """Get the current storage client instance."""
    if es_client is None:
        raise RuntimeError("Elasticsearch client not initialized")
    return es_client
