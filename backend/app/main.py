"""ASGI factory: uvicorn app.main:create_application --factory."""

from .api import create_app
from .settings import Settings


def create_application():
    return create_app(Settings())
