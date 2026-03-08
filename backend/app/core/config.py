from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL
from sqlalchemy.engine.url import make_url


REPO_ENV_FILE = Path(__file__).resolve().parents[3] / '.env'
LOCAL_DATABASE_HOSTS = {'localhost', '127.0.0.1', '::1'}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(str(REPO_ENV_FILE), '.env'), env_file_encoding='utf-8', extra='ignore')

    app_name: str = 'IZ Clinical Notes Analyzer'
    environment: str = 'development'
    secret_key: str = 'change-me-in-production'
    access_token_expire_minutes: int = 60
    database_url: str | None = None
    database_host: str = '127.0.0.1'
    database_port: int = 5432
    database_name: str = 'iz_clinical_notes_analyzer'
    database_user: str = 'iz_clinical_notes_app'
    database_password: str = 'change-me-app'
    postgres_service_host: str = 'postgres'
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

    @property
    def database_url_value(self) -> str:
        if self.database_url:
            if self.database_url.startswith('postgresql'):
                parsed_url = make_url(self.database_url)
                allowed_hosts = LOCAL_DATABASE_HOSTS | {self.postgres_service_host}
                if parsed_url.host not in allowed_hosts:
                    raise ValueError(
                        'This app only supports its own isolated PostgreSQL instance. '
                        f'Configured host "{parsed_url.host}" is not allowed.'
                    )
            return self.database_url

        allowed_hosts = LOCAL_DATABASE_HOSTS | {self.postgres_service_host}
        if self.database_host not in allowed_hosts:
            raise ValueError(
                'This app only supports its own isolated PostgreSQL instance. '
                f'Configured host "{self.database_host}" is not allowed.'
            )

        return URL.create(
            'postgresql+psycopg',
            username=self.database_user,
            password=self.database_password,
            host=self.database_host,
            port=self.database_port,
            database=self.database_name,
        ).render_as_string(hide_password=False)


settings = Settings()
