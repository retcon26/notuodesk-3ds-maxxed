"""3ds Max style theme + input preferences (with backup / restore)."""

import json
import os

import bpy

# --- Palette (modelled on the 3ds Max 2017+ dark UI) ------------------------
BG = (0.267, 0.267, 0.267)          # main panel grey  (#444444)
BG_DARK = (0.215, 0.215, 0.215)     # headers / menu backs
FIELD = (0.20, 0.20, 0.20)          # spinner / text field
BUTTON = (0.36, 0.36, 0.36)         # buttons
OUTLINE = (0.17, 0.17, 0.17)
TEXT = (0.86, 0.86, 0.86)
ACCENT = (0.31, 0.52, 0.78)         # 3ds Max selection blue
SUB_SEL = (1.0, 0.0, 0.0)           # sub-object selection red


def _set(obj, attr, val):
    """Set a theme attribute, tolerating API differences between versions."""
    if obj is None or not hasattr(obj, attr):
        return
    try:
        cur = getattr(obj, attr)
        if isinstance(val, tuple) and hasattr(cur, "__len__") and not isinstance(cur, str):
            n = len(cur)
            if len(val) > n:
                val = val[:n]
            elif len(val) < n:
                val = tuple(val) + tuple(cur)[len(val):]
        setattr(obj, attr, val)
    except Exception as exc:  # pragma: no cover - version differences
        print(f"[3ds Maxxed] theme: could not set {attr}: {exc}")


def _widget(ui, name, inner, inner_sel=ACCENT, text=TEXT, outline=OUTLINE, item=None, text_sel=(1, 1, 1)):
    w = getattr(ui, name, None)
    if w is None:
        return
    _set(w, "inner", (*inner, 1.0))
    _set(w, "inner_sel", (*inner_sel, 1.0))
    _set(w, "outline", (*outline, 1.0))
    _set(w, "outline_sel", (*outline, 1.0))
    _set(w, "text", text)
    _set(w, "text_sel", text_sel)
    if item is not None:
        _set(w, "item", (*item, 1.0))
    _set(w, "roundness", 0.12)       # 3ds Max widgets are boxy
    _set(w, "show_shaded", False)


EDITORS = (
    "view_3d", "graph_editor", "file_browser", "nla_editor", "dopesheet_editor",
    "image_editor", "sequence_editor", "properties", "text_editor", "node_editor",
    "outliner", "info", "preferences", "console", "clip_editor", "topbar",
    "statusbar", "spreadsheet",
)


def apply_theme():
    theme = bpy.context.preferences.themes[0]
    ui = theme.user_interface

    # Widgets
    for name in ("wcol_regular", "wcol_tool", "wcol_radio", "wcol_toggle", "wcol_option"):
        _widget(ui, name, BUTTON)
    _widget(ui, "wcol_toolbar_item", (0.30, 0.30, 0.30))
    for name in ("wcol_num", "wcol_numslider", "wcol_text"):
        _widget(ui, name, FIELD, inner_sel=(0.16, 0.16, 0.16), item=ACCENT)
    _widget(ui, "wcol_menu", (0.33, 0.33, 0.33))
    _widget(ui, "wcol_pulldown", BG)
    _widget(ui, "wcol_menu_back", (0.235, 0.235, 0.235))
    _widget(ui, "wcol_pie_menu", (0.235, 0.235, 0.235))
    _widget(ui, "wcol_menu_item", (0.235, 0.235, 0.235))
    _widget(ui, "wcol_tooltip", (0.18, 0.18, 0.18))
    _widget(ui, "wcol_box", (0.30, 0.30, 0.30))
    _widget(ui, "wcol_tab", (0.22, 0.22, 0.22), inner_sel=BG)
    _widget(ui, "wcol_list_item", BG)
    _widget(ui, "wcol_scroll", (0.30, 0.30, 0.30), item=(0.45, 0.45, 0.45))

    _set(ui, "panel_header", (0.30, 0.30, 0.30, 1.0))
    _set(ui, "panel_back", (*BG, 1.0))
    _set(ui, "panel_sub_back", (0.0, 0.0, 0.0, 0.08))
    _set(ui, "panel_outline", (0.17, 0.17, 0.17, 1.0))
    _set(ui, "panel_roundness", 0.0)
    _set(ui, "editor_border", (0.13, 0.13, 0.13))
    _set(ui, "editor_outline", (0.20, 0.20, 0.20))
    _set(ui, "editor_outline_active", (0.92, 0.78, 0.25))   # yellow active-viewport border

    # Editors
    for ed in EDITORS:
        e = getattr(theme, ed, None)
        sp = getattr(e, "space", None) if e else None
        if sp is None:
            continue
        _set(sp, "back", BG)
        _set(sp, "header", (*BG_DARK, 1.0))
        _set(sp, "text", TEXT)
        _set(sp, "header_text", TEXT)
    _set(getattr(theme.topbar, "space", None), "back", BG_DARK)
    _set(getattr(theme.statusbar, "space", None), "back", BG_DARK)

    regions = getattr(theme, "regions", None)
    if regions is not None:
        _set(getattr(regions, "sidebars", None), "back", (*BG, 1.0))
        _set(getattr(regions, "sidebars", None), "tab_back", (*BG_DARK, 1.0))

    # 3D viewport
    v3d = theme.view_3d
    grad = getattr(v3d.space, "gradients", None)
    _set(grad, "background_type", "LINEAR")
    _set(grad, "high_gradient", (0.36, 0.36, 0.36))
    _set(grad, "gradient", (0.20, 0.20, 0.20))
    _set(v3d.space, "header", (*BG_DARK, 0.85))
    _set(v3d, "grid", (0.16, 0.16, 0.16, 0.55))
    _set(v3d, "grid_major", (0.10, 0.10, 0.10, 0.75))
    _set(v3d, "object_selected", (0.38, 0.95, 0.95))   # 3ds Max 2020+ cyan selection outline
    _set(v3d, "object_active", (0.55, 1.0, 1.0))
    _set(v3d, "vertex", (0.05, 0.15, 1.0))
    _set(v3d, "vertex_select", SUB_SEL)
    _set(v3d, "vertex_size", 4)
    _set(v3d, "edge_select", SUB_SEL)
    _set(v3d, "edge_mode_select", SUB_SEL)
    _set(v3d, "face_select", (*SUB_SEL, 0.35))
    _set(v3d, "face_mode_select", (*SUB_SEL, 0.35))
    _set(v3d, "editmesh_active", (1.0, 0.55, 0.0, 0.5))
    _set(v3d, "camera", (0.35, 0.55, 0.95))
    _set(v3d, "light", (1.0, 0.9, 0.35, 0.3))
    _set(v3d, "empty", (0.35, 0.85, 0.35))
    _set(v3d, "outline_width", 1)


def reset_theme():
    try:
        bpy.ops.preferences.reset_default_theme()
    except Exception as exc:
        print(f"[3ds Maxxed] could not reset theme: {exc}")


# --- Input / view preferences ---------------------------------------------------

# (path, 3ds-Max value)
PREF_VALUES = (
    ("inputs.view_rotate_method", "TURNTABLE"),
    ("inputs.use_zoom_to_mouse", True),       # "Zoom About Mouse Point"
    ("inputs.use_mouse_depth_navigate", True),
    ("inputs.use_auto_perspective", False),     # orbiting Top stays orthographic, like Max
    ("view.show_view_name", False),           # replaced by our [+] [Perspective] labels
    ("view.show_navigate_ui", False),         # no zoom / pan buttons in Max viewports
)


def _backup_path():
    try:
        folder = bpy.utils.extension_path_user(__package__, create=True)
    except Exception:
        folder = bpy.utils.user_resource("CONFIG")
    return os.path.join(folder, "max_mode_prefs_backup.json")


def _resolve(path):
    root = bpy.context.preferences
    *parts, attr = path.split(".")
    for p in parts:
        root = getattr(root, p)
    return root, attr


def _keyconfig_prefs():
    kc = bpy.context.window_manager.keyconfigs.active if bpy.context.window_manager else None
    return getattr(kc, "preferences", None) if kc else None


def apply_prefs():
    path = _backup_path()
    backup = {}
    for p, val in PREF_VALUES:
        try:
            obj, attr = _resolve(p)
            backup[p] = getattr(obj, attr)
            setattr(obj, attr, val)
        except Exception as exc:
            print(f"[3ds Maxxed] pref {p}: {exc}")
    kcp = _keyconfig_prefs()
    if kcp is not None and hasattr(kcp, "select_mouse"):
        backup["select_mouse"] = kcp.select_mouse
        kcp.select_mouse = "LEFT"
    if not os.path.exists(path):  # keep the *original* Blender values
        with open(path, "w") as fh:
            json.dump(backup, fh, indent=1)


def restore_prefs():
    path = _backup_path()
    if not os.path.exists(path):
        return
    with open(path) as fh:
        backup = json.load(fh)
    for p, val in backup.items():
        if p == "select_mouse":
            kcp = _keyconfig_prefs()
            if kcp is not None:
                kcp.select_mouse = val
            continue
        try:
            obj, attr = _resolve(p)
            setattr(obj, attr, val)
        except Exception as exc:
            print(f"[3ds Maxxed] restore {p}: {exc}")
    os.remove(path)
