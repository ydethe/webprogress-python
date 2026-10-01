"""Reporter configuration (specification §5).

The reporter needs two inputs: a **credential token** (``key``) and a **server
base address** (``host``). Each may be supplied directly by the caller when
constructing the reporter, or through the program's environment. A value
supplied directly to the reporter takes precedence over these settings.

Environment variables (optionally via a local ``.env`` file)::

    WEBPROGRESS_HOST=http://localhost:8775
    WEBPROGRESS_KEY=<credential-token>
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """webprogress server coordinates for the reporter.

    Attributes:
        host: Base address of the webprogress server (the reporter appends the
            update-ingest path ``/handler``). The server listens on the fixed
            port 8775 (architecture §7).
        key: The credential token minted in the web UI that authenticates and
            routes this program's updates.
    """

    model_config = SettingsConfigDict(
        env_prefix="WEBPROGRESS_",
        env_file=".env",
        extra="ignore",
    )

    host: str = "http://localhost:8775"
    key: str = ""


# Module-level default, populated from the environment. Callers may also build
# their own ``Settings(host=..., key=...)`` and pass it as ``endpoint=``.
settings = Settings()
