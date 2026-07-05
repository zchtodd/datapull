"""Download capture helper."""
import logging
from pathlib import Path

log = logging.getLogger("prime")


def capture_download(page, click_action, temp_dir: Path, timeout_ms: int):
    """Runs click_action, captures the resulting download, saves it to temp_dir.
    Returns (temp_path, suggested_filename). Raises on timeout/failure."""
    temp_dir.mkdir(parents=True, exist_ok=True)
    with page.expect_download(timeout=timeout_ms) as dl_info:
        click_action()
    download = dl_info.value
    suggested = download.suggested_filename or "download.bin"
    temp_path = temp_dir / suggested
    n = 1
    while temp_path.exists():
        temp_path = temp_dir / f"{Path(suggested).stem}_{n}{Path(suggested).suffix}"
        n += 1
    download.save_as(str(temp_path))
    log.debug("download captured: suggested=%s temp=%s", suggested, temp_path)
    return temp_path, suggested
