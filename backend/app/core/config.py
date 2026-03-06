from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    app_name: str = 'IZ Clinical Notes Analyzer'
    environment: str = 'development'
    secret_key: str = 'change-me-in-production'
    access_token_expire_minutes: int = 60
    database_url: str = 'postgresql+psycopg2://iz_clinical_notes:change-me@127.0.0.1:5432/iz_clinical_notes_analyzer'
    database_host_mode: str = Field(default='internal')  # internal | host | external
    use_internal_postgres: bool = True
    backend_port: int = 8000
    frontend_origin: str = 'http://localhost:5173'
    frontend_origins: str = 'http://localhost:5173'
    upload_dir: str = 'uploads'
    bootstrap_admin_username: str = 'admin'
    bootstrap_admin_password: str = 'r3'
    reset_bootstrap_admin_on_startup: bool = True

    @property
    def frontend_origins_list(self) -> list[str]:
        origins = [origin.strip() for origin in self.frontend_origins.split(',') if origin.strip()]
        if not origins and self.frontend_origin:
            return [self.frontend_origin]
        return origins


settings = Settings()
