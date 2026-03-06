from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    app_name: str = 'Chart Review Workflow'
    environment: str = 'development'
    secret_key: str = 'change-me-in-production'
    access_token_expire_minutes: int = 60
    database_url: str = 'sqlite:///./chart_review.db'
    backend_port: int = 8000
    frontend_origin: str = 'http://localhost:5173'
    frontend_origins: str = 'http://localhost:5173'
    upload_dir: str = 'uploads'

    @property
    def frontend_origins_list(self) -> list[str]:
        origins = [origin.strip() for origin in self.frontend_origins.split(',') if origin.strip()]
        if not origins and self.frontend_origin:
            return [self.frontend_origin]
        return origins


settings = Settings()
