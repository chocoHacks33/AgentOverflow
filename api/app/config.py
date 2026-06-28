from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    elasticsearch_url: str = "local://memory"
    elasticsearch_api_key: str = ""
    use_local_backend: bool = True
    sandbox_engine: str = "auto"
    modal_enabled: bool = False
    modal_app_name: str = "agentoverflow-verifier"
    modal_timeout_seconds: int = 10
    devin_api_key: str = ""
    devin_org_id: str = ""
    devin_base_url: str = "https://api.devin.ai"
    devin_mode: str = "normal"
    devin_max_acu_limit: int = 5

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
