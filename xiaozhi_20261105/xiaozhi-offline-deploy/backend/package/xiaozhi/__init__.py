from dotenv import load_dotenv

load_dotenv(".env", override=True)

from concurrent.futures import ThreadPoolExecutor  # noqa: E402

from xiaozhi.config import config as config  # noqa: E402

try:
    from importlib.metadata import version

    __version__ = version("xiaozhi")
except Exception:
    __version__ = "unknown"

executor = ThreadPoolExecutor()  # noqa: E402


def get_version():
    """Return the Xiaozhi version."""
    return __version__
