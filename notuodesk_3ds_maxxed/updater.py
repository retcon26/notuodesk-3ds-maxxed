"""One-click updates from GitHub Releases.

Check for Updates asks GitHub for the latest release of the repository set in the
add-on preferences; Update Now downloads its .zip asset and installs it over this
add-on with Blender's own extension installer. Private repositories need a GitHub
token with read access to the repo (stored in Blender's preferences).
Respects Blender's "Allow Online Access" setting.
"""

import json
import os
import re
import tempfile
import threading
import urllib.error
import urllib.request

import bpy
from bpy.types import Operator

API = "https://api.github.com/repos/{repo}/releases/latest"

# Shared state (written by the worker thread, read by the UI)
status = {"state": "idle", "message": "", "latest": None, "current": None,
          "asset_url": None, "asset_name": None, "browser_url": None, "notes": "", "zip_path": None}
BUSY = {"checking", "downloading", "downloaded", "installing"}
_lock = threading.Lock()


def _set(**kw):
    """Thread-safe: only touches the status dict (never bpy)."""
    with _lock:
        status.update(kw)


def _poll():
    """Main-thread timer: redraws the UI while a check/download runs and installs when ready."""
    wm = bpy.context.window_manager
    if wm is not None:
        for w in wm.windows:
            for a in w.screen.areas:
                a.tag_redraw()
    with _lock:
        state, path = status["state"], status["zip_path"]
    if state == "downloaded" and path:
        _set(state="installing", message="Installing...")
        _install(path)
        return None
    return 0.25 if state in BUSY else None


def _start(target, *args):
    threading.Thread(target=target, args=args, daemon=True).start()
    if not bpy.app.timers.is_registered(_poll):
        bpy.app.timers.register(_poll, first_interval=0.25)


def _addon_dir():
    return os.path.dirname(os.path.abspath(__file__))


def current_version():
    path = os.path.join(_addon_dir(), "blender_manifest.toml")
    try:
        with open(path, encoding="utf-8") as fh:
            m = re.search(r'^version\s*=\s*"([^"]+)"', fh.read(), re.M)
            if m:
                return m.group(1)
    except OSError:
        pass
    from . import bl_info
    return ".".join(str(v) for v in bl_info["version"])


def parse_version(text):
    nums = re.findall(r"\d+", text or "")
    return tuple(int(n) for n in nums[:3]) + (0,) * (3 - len(nums[:3]))


def _prefs():
    from . import get_prefs
    return get_prefs()


def _headers(token, accept="application/vnd.github+json"):
    h = {"Accept": accept, "User-Agent": "NotuoDesk-3ds-Maxxed-Updater",
         "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        h["Authorization"] = f"Bearer {token.strip()}"
    return h


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _online_ok(op=None):
    if not bpy.app.online_access:
        msg = "Online access is off: Preferences > System > Network > Allow Online Access"
        _set(state="error", message=msg)
        if op:
            op.report({"WARNING"}, msg)
        return False
    return True


# ---------------------------------------------------------------------------
# worker functions (run in a background thread)
# ---------------------------------------------------------------------------

def _check_worker(repo, token):
    cur = current_version()
    _set(state="checking", message=f"Checking {repo}...", current=cur)
    try:
        req = urllib.request.Request(API.format(repo=repo), headers=_headers(token))
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            msg = ("No release found. If the repository is private, add a GitHub token in the "
                   "add-on settings (or make the repository public)")
        elif exc.code in (401, 403):
            msg = f"GitHub refused access ({exc.code}): check the token"
        else:
            msg = f"GitHub error {exc.code}"
        _set(state="error", message=msg)
        return
    except Exception as exc:
        _set(state="error", message=f"Could not reach GitHub: {exc}")
        return
    tag = data.get("tag_name", "")
    asset = next((a for a in data.get("assets", []) if a.get("name", "").endswith(".zip")), None)
    if asset is None:
        _set(state="error", message=f"Release {tag} has no .zip to install")
        return
    newer = parse_version(tag) > parse_version(cur)
    _set(state="available" if newer else "uptodate", latest=tag.lstrip("v"),
         asset_url=asset.get("url"), asset_name=asset.get("name"),
         browser_url=asset.get("browser_download_url"), notes=(data.get("body") or "")[:2000],
         message=(f"Version {tag.lstrip('v')} is available (you have {cur})" if newer
                  else f"You have the latest version ({cur})"))


def _download_worker(token):
    with _lock:
        url, name, browser = status["asset_url"], status["asset_name"], status["browser_url"]
    _set(state="downloading", message=f"Downloading {name}...")
    target = os.path.join(tempfile.mkdtemp(prefix="maxxed_update_"), name)
    try:
        if token:
            # API asset URL -> 302 to a signed download URL that must be fetched without the token
            opener = urllib.request.build_opener(_NoRedirect)
            req = urllib.request.Request(url, headers=_headers(token, "application/octet-stream"))
            try:
                with opener.open(req, timeout=30) as resp:
                    payload = resp.read()
            except urllib.error.HTTPError as exc:
                if exc.code not in (301, 302, 303, 307, 308):
                    raise
                loc = exc.headers.get("Location")
                with urllib.request.urlopen(urllib.request.Request(
                        loc, headers={"User-Agent": "NotuoDesk-3ds-Maxxed-Updater"}), timeout=60) as resp:
                    payload = resp.read()
        else:
            with urllib.request.urlopen(urllib.request.Request(
                    browser, headers={"User-Agent": "NotuoDesk-3ds-Maxxed-Updater"}), timeout=60) as resp:
                payload = resp.read()
        if payload[:2] != b"PK":
            raise ValueError("download is not a zip file")
        with open(target, "wb") as fh:
            fh.write(payload)
    except Exception as exc:
        _set(state="error", message=f"Download failed: {exc}")
        return
    _set(state="downloaded", zip_path=target, message="Downloaded, installing...")


def _install(path):
    """Runs on the main thread (timer)."""
    pkg = __package__
    try:
        if pkg.startswith("bl_ext."):
            repo_module = pkg.split(".")[1]
            bpy.ops.extensions.package_install_files(filepath=path, repo=repo_module,
                                                     enable_on_install=True, overwrite=True)
        else:   # installed as a legacy add-on
            bpy.ops.preferences.addon_install(filepath=path, overwrite=True)
            bpy.ops.preferences.addon_enable(module=pkg)
    except Exception as exc:
        _set(state="error", message=f"Install failed: {exc}")
        return None
    _set(state="done", message="Updated! Restart Blender if anything looks off.")
    return None


# ---------------------------------------------------------------------------
# operators
# ---------------------------------------------------------------------------

class MAX_OT_check_update(Operator):
    """Check GitHub for a newer version of NotuoDesk 3ds Maxxed"""
    bl_idname = "max.check_update"
    bl_label = "Check for Updates"

    def execute(self, context):
        if not _online_ok(self):
            return {"CANCELLED"}
        p = _prefs()
        _start(_check_worker, p.update_repo, p.github_token)
        return {"FINISHED"}


class MAX_OT_install_update(Operator):
    """Download the latest release from GitHub and install it over this add-on"""
    bl_idname = "max.install_update"
    bl_label = "Update Now"

    @classmethod
    def poll(cls, context):
        return status["state"] == "available"

    def execute(self, context):
        if not _online_ok(self):
            return {"CANCELLED"}
        _start(_download_worker, _prefs().github_token)
        return {"FINISHED"}


class MAX_OT_open_online_prefs(Operator):
    """Open Preferences > System to allow online access"""
    bl_idname = "max.open_online_prefs"
    bl_label = "Allow Online Access..."

    def execute(self, context):
        context.preferences.active_section = "SYSTEM"
        bpy.ops.screen.userpref_show("INVOKE_DEFAULT")
        return {"FINISHED"}


def draw_update_box(layout, prefs=None):
    box = layout.box()
    st = status["state"]
    head = box.row()
    head.label(text=f"Updates  (installed: {current_version()})", icon="URL")
    row = box.row(align=True)
    row.operator("max.check_update", icon="FILE_REFRESH")
    if st == "available":
        row.operator("max.install_update", text=f"Update to {status['latest']}", icon="IMPORT")
    if status["message"]:
        r = box.row()
        r.alert = st == "error"
        r.label(text=status["message"], icon={"error": "ERROR", "available": "INFO", "done": "CHECKMARK",
                                              "uptodate": "CHECKMARK"}.get(st, "TIME"))
    if not bpy.app.online_access:
        box.operator("max.open_online_prefs", icon="PREFERENCES")
    if prefs is not None:
        col = box.column(align=True)
        col.prop(prefs, "update_repo")
        col.prop(prefs, "github_token")
        col.prop(prefs, "auto_check_updates")
        if prefs.github_token:
            col.label(text="The token is saved in Blender's preferences file.", icon="INFO")


def _auto_check():
    p = _prefs()
    if p is not None and p.auto_check_updates and bpy.app.online_access:
        _start(_check_worker, p.update_repo, p.github_token)
    return None


classes = (MAX_OT_check_update, MAX_OT_install_update, MAX_OT_open_online_prefs)


def register_auto_check():
    if not bpy.app.background:
        bpy.app.timers.register(_auto_check, first_interval=8.0)
