"""Dashboard package — FastAPI REST API + SPA frontend."""

from copypoly.dashboard.app import create_app, dashboard_app

__all__ = ["create_app", "dashboard_app"]
