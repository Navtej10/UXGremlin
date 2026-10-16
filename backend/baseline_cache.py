import json
import os
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

BASELINES_FILE = Path(__file__).parent / "baselines.json"
_lock = threading.Lock()


def normalize_cache_key(url: str, task: str) -> str:
    """Creates a normalized cache key from (url, task)."""
    parsed = urlparse(url.strip())
    # Normalize scheme + netloc (lowercased) + path (strip trailing slash)
    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/")
    norm_url = f"{scheme}://{netloc}{path}"
    norm_task = " ".join(task.strip().lower().split())
    return f"{norm_url}||{norm_task}"


def get_cached_baseline(url: str, task: str, file_path: Path | str | None = None) -> dict[str, Any] | None:
    """
    Retrieves a cached baseline result for a given (url, task) pair.
    Returns None if no cache exists or entry is not found.
    """
    target_path = Path(file_path) if file_path else BASELINES_FILE
    if not target_path.exists():
        return None

    key = normalize_cache_key(url, task)
    with _lock:
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get(key)
        except Exception as e:
            print(f"Warning: could not read baselines cache ({e})")
            return None


def save_baseline(
    url: str,
    task: str,
    expected_steps: int | None,
    path: list[dict[str, Any]],
    completed: bool,
    error: str = "",
    file_path: Path | str | None = None,
) -> dict[str, Any]:
    """
    Saves or updates a baseline run in the cache JSON file.
    """
    target_path = Path(file_path) if file_path else BASELINES_FILE
    key = normalize_cache_key(url, task)
    record = {
        "url": url.strip(),
        "task": task.strip(),
        "expected_steps": expected_steps,
        "path": path,
        "completed": completed,
        "error": error,
        "timestamp": time.time(),
    }

    with _lock:
        data: dict[str, Any] = {}
        if target_path.exists():
            try:
                with open(target_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}

        data[key] = record

        # Write to temporary file first then atomic rename
        tmp_path = target_path.with_suffix(".tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            # On Windows, replace requires removing existing file or os.replace
            os.replace(tmp_path, target_path)
        except Exception as e:
            print(f"Warning: could not write baselines cache ({e})")
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass

    return record


def clear_baseline_cache(file_path: Path | str | None = None) -> None:
    """Clears the baseline cache file. Useful for testing."""
    target_path = Path(file_path) if file_path else BASELINES_FILE
    with _lock:
        if target_path.exists():
            try:
                target_path.unlink()
            except Exception:
                pass
