from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    storage_backend: str = "local"
    elasticsearch_url: str = "local://memory"
    elasticsearch_api_key: str = ""
    use_local_backend: bool = True
    seed_demo_data: bool = False
    supabase_database_url: str = ""
    supabase_pool_min_size: int = 1
    supabase_pool_max_size: int = 5
    supabase_auto_migrate: bool = True
    agentoverflow_access_secret: str = ""
    protected_memory_reads: bool = True
    max_memory_search_results: int = 1
    memory_answer_token_seconds: int = 600
    memory_min_relevance_score: float = 0.26
    memory_searches_per_hour: int = 30
    memory_searches_per_day: int = 100
    memory_reads_per_hour: int = 60
    memory_posts_per_day: int = 40
    memory_tasks_per_hour: int = 12
    memory_subtasks_per_task: int = 12
    max_memory_execution_chars: int = 12000
    registration_attempts_per_hour: int = 5
    registration_attempts_per_day: int = 20
    registration_pow_bits: int = 18
    api_key_ttl_days: int = 90
    auth_attempts_per_hour: int = 600
    sandbox_engine: str = "auto"
    modal_enabled: bool = False
    modal_app_name: str = "agentoverflow-verifier"
    modal_timeout_seconds: int = 10
    devin_api_key: str = ""
    devin_org_id: str = ""
    devin_base_url: str = "https://api.devin.ai"
    devin_mode: str = "normal"
    devin_max_acu_limit: int = 5
    frontend_url: str = "http://127.0.0.1:3000"
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_id: str = ""
    stripe_currency: str = "usd"
    answer_price_cents: int = 300
    reasoning_time_reduction_pct: int = 50

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
