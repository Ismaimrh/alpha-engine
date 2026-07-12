"""Supabase client (spec: /backend/app/utils/db.py).

Usage (spec Step 2 verification):
    from app.utils.db import supabase
    print(supabase.table("companies").select("*").limit(1).execute())

Uses the service-role key (server-side only — never expose it to the
frontend; the frontend gets the anon key via its own env in Step 11).

The client is created lazily on first attribute access so that importing
this module never fails or makes network calls — modules that don't touch
the DB (e.g. pure factor math) can be imported without a configured .env.
"""

from supabase import Client, create_client

from app.config import require


def get_client() -> Client:
    """Create a new Supabase client from env configuration."""
    return create_client(require("SUPABASE_URL"), require("SUPABASE_SERVICE_KEY"))


class _LazyClient:
    """Proxy that instantiates the real client on first use.

    Keeps the spec's `from app.utils.db import supabase` ergonomics while
    deferring env validation to the first actual query.
    """

    _client: Client | None = None

    def _get(self) -> Client:
        if self._client is None:
            self._client = get_client()
        return self._client

    def __getattr__(self, name: str):
        return getattr(self._get(), name)


supabase = _LazyClient()
