from pathlib import Path

from authlib.integrations.starlette_client import OAuth
from starlette.templating import Jinja2Templates

from src.ai_newsletter.core.config import get_settings

settings = get_settings()
TEMPLATE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "frontend"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
oauth = OAuth()

oauth.register(
    name="google",
    client_id=settings.google_client_id,
    client_secret=settings.google_client_secret,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)
