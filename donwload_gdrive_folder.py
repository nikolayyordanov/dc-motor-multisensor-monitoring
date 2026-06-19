"""
Download a specific Google Drive folder (recursively).

Auth options (pick one at runtime):
  1. Service account JSON key   -> --service-account key.json
  2. OAuth client (browser)     -> --oauth-client client_secret.json
  3. Public "anyone with link"  -> --public   (uses gdown, no credentials)

Examples
--------
  # Service account (folder must be shared with the SA's email)
  python download_gdrive_folder.py --url "<folder_url>" --dest ./out \
      --service-account sa.json

  # OAuth (authorize once in the browser; token cached as token.json)
  python download_gdrive_folder.py --folder-id <ID> --dest ./out \
      --oauth-client client_secret.json

  # Public folder, no credentials
  python download_gdrive_folder.py --url "<folder_url>" --dest ./out --public

Install deps:
  pip install google-api-python-client google-auth google-auth-oauthlib tqdm
  # only for --public:
  pip install gdown
"""
from __future__ import annotations

import argparse
import io
import os
import re
import sys
import time
from pathlib import Path

# Windows consoles default to cp1252 and crash when printing Cyrillic file
# names; force UTF-8 so progress output (and gdown's prints) never fail.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Use the OS (e.g. Windows) certificate store so corporate TLS-inspection
# proxies, whose CA is trusted by the OS but not by certifi, work transparently.
try:
    import truststore as _truststore
    _truststore.inject_into_ssl()
except Exception:  # truststore optional; --ca-bundle/--insecure are fallbacks
    pass

FOLDER_MIME = "application/vnd.google-apps.folder"
# Google Workspace types that must be exported, with a sensible target format.
GOOGLE_EXPORT = {
    "application/vnd.google-apps.document":
        ("application/pdf", ".pdf"),
    "application/vnd.google-apps.spreadsheet":
        ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx"),
    "application/vnd.google-apps.presentation":
        ("application/pdf", ".pdf"),
    "application/vnd.google-apps.drawing":
        ("image/png", ".png"),
}
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def extract_folder_id(url_or_id: str) -> str:
    """Accept a full Drive URL or a bare folder ID."""
    s = url_or_id.strip()
    m = re.search(r"/folders/([A-Za-z0-9_-]+)", s)
    if m:
        return m.group(1)
    m = re.search(r"[?&]id=([A-Za-z0-9_-]+)", s)
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{10,}", s):
        return s
    raise ValueError(f"Could not parse a folder ID from: {url_or_id!r}")


def _make_progress(total, desc):
    """Return a tqdm byte progress bar, or None if tqdm isn't installed."""
    try:
        from tqdm import tqdm
    except ImportError:
        return None
    return tqdm(
        total=total,
        unit="B",
        unit_scale=True,
        unit_divisor=1024,
        desc=desc[:40],
        leave=False,
        dynamic_ncols=True,
    )


def safe_name(name: str) -> str:
    """Make a file/folder name safe for the local filesystem."""
    name = name.replace("\x00", "")
    # Strip characters illegal on Windows; collapse path separators.
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    name = name.rstrip(". ")  # Windows dislikes trailing dot/space
    return name or "unnamed"


def with_backoff(fn, *, retries: int = 5, base: float = 1.5, what: str = ""):
    """Run fn() with exponential backoff on transient errors."""
    from googleapiclient.errors import HttpError

    for attempt in range(1, retries + 1):
        try:
            return fn()
        except HttpError as e:
            status = getattr(e.resp, "status", None)
            if status in (403, 429, 500, 502, 503, 504) and attempt < retries:
                wait = base ** attempt
                print(f"  ! transient {status} on {what}; retry "
                      f"{attempt}/{retries} in {wait:.1f}s", file=sys.stderr)
                time.sleep(wait)
                continue
            raise
        except (TimeoutError, ConnectionError) as e:
            if attempt < retries:
                wait = base ** attempt
                print(f"  ! {type(e).__name__} on {what}; retry "
                      f"{attempt}/{retries} in {wait:.1f}s", file=sys.stderr)
                time.sleep(wait)
                continue
            raise


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
def build_service(args):
    from googleapiclient.discovery import build

    # API key works for PUBLIC (anyone-with-link) folders: no OAuth, no
    # service account. files.list/get_media succeed on public resources.
    if getattr(args, "api_key", None):
        return build("drive", "v3", developerKey=args.api_key,
                     cache_discovery=False)

    if args.service_account:
        from google.oauth2 import service_account
        creds = service_account.Credentials.from_service_account_file(
            args.service_account, scopes=SCOPES)
    elif args.oauth_client or (args.client_id and args.client_secret):
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow

        token_path = Path(args.token)
        creds = None
        if token_path.exists():
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if args.oauth_client:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        args.oauth_client, SCOPES)
                else:
                    client_config = {
                        "installed": {
                            "client_id": args.client_id,
                            "client_secret": args.client_secret,
                            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                            "token_uri": "https://oauth2.googleapis.com/token",
                            "redirect_uris": ["http://localhost"],
                        }
                    }
                    flow = InstalledAppFlow.from_client_config(
                        client_config, SCOPES)
                creds = flow.run_local_server(port=0)
            token_path.write_text(creds.to_json(), encoding="utf-8")
    else:
        raise SystemExit("No auth provided. Use --api-key, --service-account, "
                         "--oauth-client, --client-id/--client-secret, "
                         "or --public.")

    return build("drive", "v3", credentials=creds, cache_discovery=False)


# --------------------------------------------------------------------------- #
# Listing & downloading (API path)
# --------------------------------------------------------------------------- #
def list_children(service, folder_id: str):
    """Yield all child items of a folder, handling pagination."""
    page_token = None
    fields = ("nextPageToken, files(id, name, mimeType, size, "
              "md5Checksum, modifiedTime)")
    while True:
        resp = with_backoff(
            lambda: service.files().list(
                q=f"'{folder_id}' in parents and trashed = false",
                fields=fields,
                pageSize=1000,
                pageToken=page_token,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            ).execute(),
            what=f"list {folder_id}",
        )
        for f in resp.get("files", []):
            yield f
        page_token = resp.get("nextPageToken")
        if not page_token:
            break


def download_file(service, file_meta, dest_path: Path, *, overwrite: bool):
    from googleapiclient.http import MediaIoBaseDownload

    mime = file_meta["mimeType"]
    export = GOOGLE_EXPORT.get(mime)

    # Resume/skip: same size already on disk (for binary downloads).
    if dest_path.exists() and not overwrite:
        remote_size = file_meta.get("size")
        if remote_size is not None and dest_path.stat().st_size == int(remote_size):
            print(f"  = skip (exists)  {file_meta['name']}  ->  {dest_path}")
            return
        if export is not None:  # Google-native: no reliable size, skip if present
            print(f"  = skip (exists)  {file_meta['name']}  ->  {dest_path}")
            return

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest_path.with_suffix(dest_path.suffix + ".part")

    if export is not None:
        export_mime, _ = export
        request = service.files().export_media(
            fileId=file_meta["id"], mimeType=export_mime)
    else:
        request = service.files().get_media(
            fileId=file_meta["id"], supportsAllDrives=True)

    # Known size enables a real percentage bar (binary get_media only;
    # Google-native exports don't report a reliable size up front).
    total = None
    if export is None and file_meta.get("size") is not None:
        total = int(file_meta["size"])

    def _run():
        with io.FileIO(tmp, "wb") as fh:
            downloader = MediaIoBaseDownload(fh, request, chunksize=8 * 1024 * 1024)
            bar = _make_progress(total, dest_path.name)
            done = False
            while not done:
                status, done = downloader.next_chunk()
                if bar is not None and status is not None:
                    # status.resumable_progress is cumulative bytes downloaded.
                    bar.update(status.resumable_progress - bar.n)
            if bar is not None:
                if total is not None and bar.n < total:
                    bar.update(total - bar.n)
                bar.close()
        return True

    print(f"  > downloading  {file_meta['name']}  ->  {dest_path}")
    with_backoff(_run, what=f"download {file_meta['name']}")
    tmp.replace(dest_path)
    print(f"  + done         {file_meta['name']}  ->  {dest_path}")


def walk_and_download(service, folder_id: str, dest: Path, *,
                      recursive: bool, overwrite: bool):
    counts = {"files": 0, "folders": 0, "skipped": 0}

    def _walk(fid: str, local_dir: Path):
        local_dir.mkdir(parents=True, exist_ok=True)
        print(f"\n[folder] {local_dir}")
        for item in list_children(service, fid):
            name = safe_name(item["name"])
            if item["mimeType"] == FOLDER_MIME:
                counts["folders"] += 1
                sub = local_dir / name
                if recursive:
                    _walk(item["id"], sub)
                else:
                    print(f"  (skip subfolder, non-recursive) {name}")
            else:
                export = GOOGLE_EXPORT.get(item["mimeType"])
                target = local_dir / name
                if export is not None and not target.suffix:
                    target = target.with_suffix(export[1])
                before = target.exists()
                download_file(service, item, target, overwrite=overwrite)
                if before and not overwrite:
                    counts["skipped"] += 1
                else:
                    counts["files"] += 1

    _walk(folder_id, dest)
    return counts


# --------------------------------------------------------------------------- #
# Public path (gdown)
# --------------------------------------------------------------------------- #
def download_public(folder_id: str, dest: Path, *, verify=True):
    try:
        import gdown
    except ImportError:
        raise SystemExit("--public requires gdown:  pip install gdown")
    import inspect

    dest.mkdir(parents=True, exist_ok=True)
    url = f"https://drive.google.com/drive/folders/{folder_id}"

    # gdown's download_folder signature varies across versions; only pass
    # keyword arguments that the installed version actually accepts.
    candidate_kwargs = {
        "url": url,
        "output": str(dest),
        "quiet": False,
        "use_cookies": False,
        "remaining_ok": True,
        "verify": verify,
    }
    supported = set(inspect.signature(gdown.download_folder).parameters)
    kwargs = {k: v for k, v in candidate_kwargs.items() if k in supported}
    gdown.download_folder(**kwargs)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main():
    p = argparse.ArgumentParser(
        description="Download a Google Drive folder recursively.")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--url", help="Full Google Drive folder URL.")
    src.add_argument("--folder-id", help="Google Drive folder ID.")

    p.add_argument("--dest", required=True, help="Local destination directory.")

    auth = p.add_mutually_exclusive_group()
    auth.add_argument("--service-account", metavar="JSON",
                      help="Path to a service-account key file.")
    auth.add_argument("--oauth-client", metavar="JSON",
                      help="Path to an OAuth client_secret.json.")
    auth.add_argument("--api-key", metavar="KEY",
                      help="Google API key for PUBLIC folders (Drive API, "
                           "recursive; more reliable than --public/gdown).")
    auth.add_argument("--public", action="store_true",
                      help="Folder is public (anyone with link); uses gdown.")

    # OAuth provided as raw strings instead of a JSON file (desktop-app client).
    p.add_argument("--client-id", metavar="ID",
                   help="OAuth desktop client ID (use with --client-secret).")
    p.add_argument("--client-secret", metavar="SECRET",
                   help="OAuth desktop client secret (use with --client-id).")

    p.add_argument("--token", default="token.json",
                   help="Where to cache the OAuth token (default token.json).")
    p.add_argument("--no-recursive", action="store_true",
                   help="Do not descend into subfolders.")
    p.add_argument("--overwrite", action="store_true",
                   help="Re-download even if a same-size file exists.")
    p.add_argument("--ca-bundle", metavar="PEM",
                   help="Path to a corporate CA bundle (.pem) for TLS verify.")
    p.add_argument("--insecure", action="store_true",
                   help="Disable TLS certificate verification (last resort).")
    args = p.parse_args()

    # TLS verification target: a CA bundle path, False (insecure), or True.
    if args.ca_bundle:
        os.environ["REQUESTS_CA_BUNDLE"] = args.ca_bundle
        os.environ["SSL_CERT_FILE"] = args.ca_bundle
        verify = args.ca_bundle
    elif args.insecure:
        import urllib3
        urllib3.disable_warnings()
        print("WARNING: TLS verification disabled (--insecure).", file=sys.stderr)
        verify = False
    else:
        verify = True

    folder_id = extract_folder_id(args.url or args.folder_id)
    dest = Path(args.dest).expanduser().resolve()
    print(f"Folder ID : {folder_id}")
    print(f"Destination: {dest}")

    if args.public:
        download_public(folder_id, dest, verify=verify)
        print("Done (public).")
        return

    service = build_service(args)
    counts = walk_and_download(
        service, folder_id, dest,
        recursive=not args.no_recursive, overwrite=args.overwrite)
    print(f"\nDone. Downloaded {counts['files']} file(s), "
          f"{counts['folders']} folder(s), skipped {counts['skipped']}.")


if __name__ == "__main__":
    main()