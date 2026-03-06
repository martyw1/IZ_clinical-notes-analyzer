from sqlalchemy import create_engine, inspect, text

from app.db.bootstrap import ensure_schema_compatibility


def test_ensure_schema_compatibility_adds_missing_legacy_columns(tmp_path):
    db_path = tmp_path / 'legacy.db'
    engine = create_engine(f'sqlite:///{db_path}')

    with engine.begin() as connection:
        connection.execute(
            text(
                'CREATE TABLE users ('
                'id INTEGER PRIMARY KEY, '
                'username VARCHAR(80) UNIQUE NOT NULL, '
                'password_hash VARCHAR(255) NOT NULL, '
                'role VARCHAR(20) NOT NULL'
                ')'
            )
        )

    ensure_schema_compatibility(engine)

    columns = {column['name'] for column in inspect(engine).get_columns('users')}
    assert 'must_reset_password' in columns
    assert 'failed_login_attempts' in columns
    assert 'is_locked' in columns
    assert 'created_at' in columns
