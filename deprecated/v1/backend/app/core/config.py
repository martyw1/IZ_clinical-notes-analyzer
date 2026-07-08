from pathlib import Path
import os
import platform

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL
from sqlalchemy.engine.url import make_url


REPO_ROOT = Path(__file__).resolve().parents[3]
REPO_ENV_FILE = REPO_ROOT / '.env'
LOCAL_DATABASE_HOSTS = {'localhost', '127.0.0.1', '::1'}
APP_FOLDER_NAME = 'IZ Clinical Notes Analyzer'
DEFAULT_RULES_CONFIG_PATH = 'config/rules/alleva_treatment_plan_completeness_rules.yaml'


def default_local_app_data_dir() -> Path:
    """Return the per-user app-data folder before Settings is initialized."""
    system = platform.system().lower()
    if system == 'darwin':
        return Path.home() / 'Library' / 'Application Support' / APP_FOLDER_NAME
    if system == 'windows':
        root = Path(os.environ.get('LOCALAPPDATA') or (Path.home() / 'AppData' / 'Local'))
        return root / APP_FOLDER_NAME
    return Path.home() / '.local' / 'share' / 'iz-clinical-notes-analyzer'


def user_env_file() -> Path:
    """Resolve the persistent per-user env file used by packaged desktop runs."""
    configured = os.environ.get('IZ_CNA_ENV_FILE')
    if configured:
        return Path(configured).expanduser()
    return default_local_app_data_dir() / '.env'


USER_ENV_FILE = user_env_file()


class Settings(BaseSettings):
    """Environment-backed configuration for local desktop, source, and Docker runs.

    The default runtime is intentionally local SQLite so a Windows 10/11 user can
    run a packaged desktop build without Docker, PostgreSQL, or server setup.
    PostgreSQL remains supported for developer/server scenarios by setting
    DATABASE_BACKEND=postgresql or DATABASE_URL to a local/Compose PostgreSQL DSN.
    """

    model_config = SettingsConfigDict(
        env_file=(str(REPO_ENV_FILE), str(USER_ENV_FILE), '.env'),
        env_file_encoding='utf-8',
        extra='ignore',
    )

    app_name: str = 'IZ Clinical Notes Analyzer'
    environment: str = 'local-client'
    secret_key: str = 'change-me-in-production'
    data_encryption_key: str = ''
    access_token_expire_minutes: int = 60
    database_backend: str = 'sqlite'
    database_url: str | None = None
    local_sqlite_db_path: str = 'clinical-notes-analyzer.sqlite3'
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
    header_logo_path: str = ''
    rules_config_path: str = DEFAULT_RULES_CONFIG_PATH
    max_upload_file_bytes: int = 50 * 1024 * 1024
    max_upload_total_bytes: int = 250 * 1024 * 1024
    max_upload_file_count: int = 40
    bootstrap_admin_username: str = 'admin'
    bootstrap_admin_password: str = 'change-me'
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
        """Return the SQLAlchemy DSN for the configured local database.

        SQLite is the safe default for the Windows desktop target because it is
        embedded in Python and needs no separate service. PostgreSQL is still
        allowed for local developer/Compose scenarios, but non-local PostgreSQL
        hosts are rejected to avoid accidental PHI egress.
        """
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

        if self.database_backend.lower() in {'sqlite', 'sqlite3', 'local'}:
            db_path = self.sqlite_db_path
            db_path.parent.mkdir(parents=True, exist_ok=True)
            return f'sqlite:///{db_path.as_posix()}'

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
    def sqlite_db_path(self) -> Path:
        configured = Path(self.local_sqlite_db_path).expanduser()
        if configured.is_absolute():
            return configured
        return self.local_app_data_dir / configured

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
    def header_logo_file(self) -> Path | None:
        """Return the configured or bundled header logo file, if available."""
        candidates: list[Path] = []
        if self.header_logo_path.strip():
            configured = Path(self.header_logo_path).expanduser()
            if configured.is_absolute():
                candidates.append(configured)
            else:
                candidates.append(self.local_app_data_dir / configured)
                candidates.append(REPO_ROOT / configured)
        candidates.append(REPO_ROOT / 'backend' / 'app' / 'assets' / 'r3-recovery-services-logo.png')
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        return None

    @property
    def rules_config_file(self) -> Path:
        """Resolve the YAML rules file used by the completeness-check engine."""
        configured = Path(self.rules_config_path).expanduser()
        if configured.is_absolute():
            return configured
        repo_candidate = REPO_ROOT / configured
        if repo_candidate.exists():
            return repo_candidate
        return self.local_app_data_dir / configured

    @property
    def local_app_data_dir(self) -> Path:
        """Return the per-user app-data folder for macOS, Windows, or Linux."""
        return default_local_app_data_dir()


settings = Settings()
