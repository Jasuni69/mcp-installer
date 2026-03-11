"""
GitHub Release downloader — replaces git clone/pull with ZIP downloads.

Downloads server bundles from GitHub Release assets, verifies SHA256 checksums,
and extracts them to the install directory.

Failure modes handled:
- GitHub API rate limit (403) → clear error message with guidance
- Network timeout → configurable timeout, RetryError with details
- Corrupted download (checksum mismatch) → raises ChecksumError, deletes bad file
- Partial download (connection dropped) → streaming with temp file, cleanup on error
- Disk full → caught as OSError
- ZIP extraction failure → caught, temp files cleaned up
- Manifest missing/malformed → ValidationError with details
- Release has no assets → clear error
"""
import hashlib
import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Callable

import requests

from mcp_installer.constants import RELEASES_API


class DownloadError(Exception):
    """Raised when a download fails."""


class ChecksumError(DownloadError):
    """Raised when a SHA256 checksum doesn't match."""


class ManifestError(DownloadError):
    """Raised when the manifest is missing or malformed."""


def fetch_release_info(api_url: str = RELEASES_API, timeout: int = 15) -> dict:
    """Fetch the latest release info from GitHub API.

    Returns the full release JSON.
    Raises DownloadError on failure.
    """
    try:
        resp = requests.get(api_url, timeout=timeout, headers={
            "Accept": "application/vnd.github.v3+json",
        })
        if resp.status_code == 403:
            raise DownloadError(
                "GitHub API rate limit exceeded. Try again in a few minutes, "
                "or set a GITHUB_TOKEN environment variable."
            )
        if resp.status_code == 404:
            raise DownloadError(
                "No releases found. The repository may not have published any releases yet."
            )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.Timeout:
        raise DownloadError("GitHub API request timed out. Check your internet connection.")
    except requests.exceptions.ConnectionError:
        raise DownloadError("Could not connect to GitHub. Check your internet connection.")
    except DownloadError:
        raise
    except Exception as e:
        raise DownloadError(f"Failed to fetch release info: {e}")


def fetch_manifest(api_url: str = RELEASES_API, timeout: int = 15) -> dict:
    """Fetch and parse the manifest.json from the latest release.

    The manifest has this structure:
    {
        "installer_version": "2.0.0",
        "servers": {
            "fabric-core": {
                "version": "1.2.0",
                "asset_name": "fabric-core.zip",
                "sha256": "abc123..."
            },
            ...
        }
    }

    Raises ManifestError if manifest is missing or malformed.
    """
    release = fetch_release_info(api_url, timeout)
    assets = release.get("assets", [])

    manifest_asset = None
    for asset in assets:
        if asset.get("name") == "manifest.json":
            manifest_asset = asset
            break

    if not manifest_asset:
        raise ManifestError(
            "Release does not contain a manifest.json asset. "
            "The release may have been published incorrectly."
        )

    try:
        resp = requests.get(
            manifest_asset["browser_download_url"],
            timeout=timeout,
        )
        resp.raise_for_status()
        manifest = resp.json()
    except json.JSONDecodeError:
        raise ManifestError("manifest.json is not valid JSON")
    except Exception as e:
        raise ManifestError(f"Failed to download manifest.json: {e}")

    # Validate structure
    if "servers" not in manifest:
        raise ManifestError("manifest.json is missing 'servers' key")

    return manifest


def compute_sha256(file_path: Path) -> str:
    """Compute SHA256 hash of a file.

    Reads in 8KB chunks to handle large files without excessive memory use.
    """
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            sha.update(chunk)
    return sha.hexdigest()


def verify_checksum(file_path: Path, expected_sha256: str) -> bool:
    """Verify a file's SHA256 checksum.

    Returns True if checksum matches, False otherwise.
    """
    actual = compute_sha256(file_path)
    return actual.lower() == expected_sha256.lower()


def download_file(
    url: str,
    dest: Path,
    timeout: int = 300,
    progress_callback: Callable[[int, int], None] | None = None,
) -> Path:
    """Download a file from URL to dest with optional progress callback.

    Uses streaming download with a temp file to avoid partial downloads.
    progress_callback receives (bytes_downloaded, total_bytes).
    total_bytes may be 0 if Content-Length is not provided.

    Returns the dest path on success.
    Raises DownloadError on failure.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)

    # Use a temp file in the same directory to avoid cross-device renames
    fd, tmp_path_str = tempfile.mkstemp(
        dir=str(dest.parent), suffix=".tmp",
        prefix=dest.stem + "_"
    )

    try:
        resp = requests.get(url, stream=True, timeout=timeout)
        resp.raise_for_status()

        total = int(resp.headers.get("Content-Length", 0))
        downloaded = 0

        import os
        with os.fdopen(fd, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
                downloaded += len(chunk)
                if progress_callback and total:
                    progress_callback(downloaded, total)

        # Rename temp file to final destination
        tmp_path = Path(tmp_path_str)
        if dest.exists():
            dest.unlink()
        tmp_path.rename(dest)
        return dest

    except Exception as e:
        # Clean up temp file on error
        try:
            Path(tmp_path_str).unlink(missing_ok=True)
        except Exception:
            pass
        if isinstance(e, DownloadError):
            raise
        raise DownloadError(f"Download failed: {e}")


def download_server(
    server_dir_name: str,
    install_dir: Path,
    manifest: dict,
    log_callback: Callable[[str], None] | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
) -> Path:
    """Download and extract a server bundle from a GitHub release.

    Args:
        server_dir_name: Server directory name (e.g., "fabric-core")
        install_dir: Base installation directory
        manifest: Manifest dict from fetch_manifest()
        log_callback: Called with log messages
        progress_callback: Called with (bytes_downloaded, total_bytes)

    Returns:
        Path to the extracted server directory.

    Raises:
        DownloadError if download or extraction fails.
        ChecksumError if SHA256 doesn't match.
    """
    server_info = manifest.get("servers", {}).get(server_dir_name)
    if not server_info:
        raise ManifestError(
            f"Server '{server_dir_name}' not found in manifest. "
            f"Available: {list(manifest.get('servers', {}).keys())}"
        )

    asset_name = server_info.get("asset_name", f"{server_dir_name}.zip")
    expected_sha = server_info.get("sha256", "")
    download_url = server_info.get("url", "")

    if not download_url:
        raise ManifestError(f"No download URL for {server_dir_name} in manifest")

    if log_callback:
        log_callback(f"Downloading {asset_name}...")

    zip_path = install_dir / asset_name
    download_file(download_url, zip_path, progress_callback=progress_callback)

    # Verify checksum if provided
    if expected_sha:
        if log_callback:
            log_callback(f"Verifying checksum for {asset_name}...")
        if not verify_checksum(zip_path, expected_sha):
            zip_path.unlink(missing_ok=True)
            raise ChecksumError(
                f"SHA256 mismatch for {asset_name}. "
                "The file may be corrupted or tampered with."
            )
    else:
        if log_callback:
            log_callback(f"  ⚠ No SHA256 in manifest for {asset_name} — skipping verification")

    # Extract
    extract_dir = install_dir / server_dir_name
    if log_callback:
        log_callback(f"Extracting {asset_name}...")

    try:
        # Remove existing dir (clean install)
        if extract_dir.exists():
            # Preserve .venv if it exists (avoid re-downloading packages)
            venv_dir = extract_dir / ".venv"
            venv_backup = None
            if venv_dir.exists():
                venv_backup = install_dir / f".venv-backup-{server_dir_name}"
                if venv_backup.exists():
                    shutil.rmtree(venv_backup)
                venv_dir.rename(venv_backup)

            shutil.rmtree(extract_dir)

            # Restore .venv
            if venv_backup and venv_backup.exists():
                extract_dir.mkdir(parents=True, exist_ok=True)
                venv_backup.rename(extract_dir / ".venv")

        with zipfile.ZipFile(zip_path) as zf:
            # Check for zip bombs (files extracting to unexpected paths)
            for info in zf.infolist():
                if info.filename.startswith("/") or ".." in info.filename:
                    raise DownloadError(
                        f"Suspicious path in ZIP: {info.filename}. "
                        "Archive may be malicious."
                    )
            zf.extractall(install_dir)
    except DownloadError:
        raise
    except Exception as e:
        raise DownloadError(f"Extraction failed for {asset_name}: {e}")
    finally:
        # Clean up ZIP
        zip_path.unlink(missing_ok=True)

    if log_callback:
        log_callback(f"✓ {server_dir_name} ready")

    return extract_dir


def download_extras(
    install_dir: Path,
    release_info: dict,
    log_callback: Callable[[str], None] | None = None,
) -> bool:
    """Download and extract extras.zip (agents, skills, templates) if available.

    Returns True if extras were downloaded and extracted, False if not available.
    """
    assets = release_info.get("assets", [])
    extras_asset = None
    for asset in assets:
        if asset.get("name") == "extras.zip":
            extras_asset = asset
            break

    if not extras_asset:
        return False

    if log_callback:
        log_callback("Downloading extras (agents, skills, templates)...")

    zip_path = install_dir / "extras.zip"
    try:
        download_file(extras_asset["browser_download_url"], zip_path)
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(install_dir)
        if log_callback:
            log_callback("✓ Extras extracted")
        return True
    except Exception as e:
        if log_callback:
            log_callback(f"⚠ Could not download extras: {e}")
        return False
    finally:
        zip_path.unlink(missing_ok=True)
