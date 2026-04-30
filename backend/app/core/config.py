from pathlib import Path
import os
import platform

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL
from sqlalchemy.engine.url import make_url


REPO_ENV_FILE = Path(__file__).resolve().parents[3] / '.env'
LOCAL_DATABASE_HOSTS = {'localhost', '127.0.0.1', '::1'}


class Settings(BaseSettings):
    """Environment-backed configuration for local desktop and Docker runs."""

    model_config = SettingsConfigDict(env_file=(str(REPO_ENV_FILE), '.env'), env_file_encoding='utf-8', extra='ignore')

    app_name: str = 'IZ Clinical Notes Analyzer'
    environment: str = 'development'
    secret_key: str = 'change-me-in-production'
    data_encryption_key: str = ''
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
    allowed_hosts: str = 'localhost,127.0.0.1,::1,testserver'
    upload_dir: str = 'uploads'
    log_dir: str = 'logs'
    max_upload_file_bytes: int = 50 * 1024 * 1024
    max_upload_total_bytes: int = 250 * 1024 * 1024
    max_upload_file_count: int = 40
    bootstrap_admin_username: str = 'admin'
    bootstrap_admin_password: str = 'r3!@analyzer#123'
    reset_bootstrap_admin_on_startup: bool = True

    @property
    def frontend_origins_list(self) -> list[str]:
        origins = [origin.strip() for origin in self.frontend_origins.split(',') if origin.strip()]
        if not origins and self.frontend_origin:
            return [self.frontend_origin]
        return origins

    @property
    def allowed_hosts_list(self) -> list[str]:
        return [host.strip() for host in self.allowed_hosts.split(',') if host.strip()]

    @property
    def is_production_like(self) -> bool:
        return self.environment.lower() in {'prod', 'production', 'client', 'local-client'}

    @staticmethod
    def looks_placeholder_secret(value: str | None) -> bool:
        normalized = (value or '').strip().lower()
        if not normalized:
            return True
        return normalized in {'change-me', 'change-me-app', 'change-me-in-production', 'r3!@analyzer#123'} or normalized.startswith(
            ('change-me-', 'replace-with', 'placeholder')
        )

    @property
    def effective_data_encryption_secret(self) -> str:
        # DATA_ENCRYPTION_KEY is preferred so JWT rotation does not break file decryption.
        return self.data_encryption_key.strip() or self.secret_key

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

    @property
    def upload_dir_path(self) -> Path:
        """Resolve relative upload paths into OS-local app data, not the repo."""
        configured = Path(self.upload_dir).expanduser()
        if configured.is_absolute():
            return configured
        return self.local_app_data_dir / configured

    @property
    def log_dir_path(self) -> Path:
        """Resolve audit fallback logs beside other local app data by default."""
        configured = Path(self.log_dir).expanduser()
        if configured.is_absolute():
            return configured
        return self.local_app_data_dir / configured

    @property
    def local_app_data_dir(self) -> Path:
        """Return the per-user app-data folder for macOS, Windows, or Linux."""
        app_folder = 'IZ Clinical Notes Analyzer'
        system = platform.system().lower()
        if system == 'darwin':
            return Path.home() / 'Library' / 'Application Support' / app_folder
        if system == 'windows':
            root = Path(os.environ.get('LOCALAPPDATA') or (Path.home() / 'AppData' / 'Local'))
            return root / app_folder
        return Path.home() / '.local' / 'share' / 'iz-clinical-notes-analyzer'


settings = Settings()
