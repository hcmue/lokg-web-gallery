"""Application settings. Secrets live only in environment variables."""
from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT/'.env')

@dataclass(frozen=True)
class Settings:
    env: str
    catalog_backend: str
    catalog_path: Path
    github_repository: str
    github_branch: str
    github_catalog_path: str
    github_token: str
    admin_password: str
    session_secret: str
    allowed_page_hosts: str
    analytics_enabled: bool
    analytics_store_queries: bool
    database_url: str
    analytics_secret: str
    analytics_retention_days: int
    analytics_allow_sqlite_production: bool
    public_frontend_origin: str

    @property
    def production(self):
        return self.env=='production'


def get_settings() -> Settings:
    return Settings(
        env=os.getenv('APP_ENV','development').lower().strip(),
        catalog_backend=os.getenv('CATALOG_BACKEND','local').lower().strip(),
        catalog_path=Path(os.getenv('CATALOG_PATH',str(ROOT/'data'/'catalog.yaml'))).resolve(),
        github_repository=os.getenv('GITHUB_REPOSITORY','').strip(),
        github_branch=os.getenv('GITHUB_BRANCH','main').strip(),
        github_catalog_path=os.getenv('GITHUB_CATALOG_PATH','data/catalog.yaml').strip('/'),
        github_token=os.getenv('GITHUB_TOKEN','').strip(),
        admin_password=os.getenv('ADMIN_PASSWORD',''),
        session_secret=os.getenv('SESSION_SECRET',''),
        allowed_page_hosts=os.getenv('ALLOWED_PAGE_HOSTS','*.github.io').lower().strip(),
        analytics_enabled=os.getenv('ANALYTICS_ENABLED','false').lower().strip() in {'true','1','yes'},
        analytics_store_queries=os.getenv('ANALYTICS_STORE_QUERIES','true').lower().strip() in {'true','1','yes'},
        database_url=os.getenv('DATABASE_URL','').strip(),
        analytics_secret=os.getenv('ANALYTICS_SECRET',os.getenv('SESSION_SECRET','')).strip(),
        analytics_retention_days=max(7,min(365,int(os.getenv('ANALYTICS_RETENTION_DAYS','90')))),
        analytics_allow_sqlite_production=os.getenv('ANALYTICS_ALLOW_SQLITE_PRODUCTION','false').lower().strip() in {'true','1','yes'},
        public_frontend_origin=os.getenv('PUBLIC_FRONTEND_ORIGIN','https://hcmue.github.io').strip().rstrip('/'),
    )
