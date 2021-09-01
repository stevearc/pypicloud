import os


def get_sqlite_url() -> str:
    return "sqlite://"


def get_mysql_url() -> str:
    user = os.environ.get("MYSQL_USER", "root")
    pw = os.environ.get("MYSQL_PASSWORD")
    if pw is None:
        pw = ""
    else:
        pw = ":" + pw
    host = os.environ.get("MYSQL_HOST", "127.0.0.1")
    port = os.environ.get("MYSQL_PORT", "3306")
    db = os.environ.get("MYSQL_DB", "test")
    return f"mysql://{user}{pw}@{host}:{port}/{db}?charset=utf8mb4"


def get_postgres_url() -> str:
    user = os.environ.get("POSTGRES_USER", "postgres")
    pw = os.environ.get("POSTGRES_PASSWORD")
    if pw is None:
        pw = ""
    else:
        pw = ":" + pw
    host = os.environ.get("POSTGRES_HOST", "127.0.0.1")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB", "postgres")
    return f"postgresql://{user}{pw}@{host}:{port}/{db}"
