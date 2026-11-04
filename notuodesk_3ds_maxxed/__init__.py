"""NotuoDesk 3ds Maxxed: makes Blender look and work like Autodesk 3ds Max.

* 3ds Max dark theme, yellow active-viewport border, white selection, red sub-objects
* A "3ds Max" workspace: Scene Explorer | quad viewports | Command Panel
* Quad viewports (Top / Front / Left / Perspective) with [+] [Perspective] labels
* 3ds Max hotkeys and navigation (MMB pan, Alt+MMB orbit, Q/W/E/R, 1-5 sub-objects...)
* Command Panel (Create / Modify / Hierarchy / Motion / Display / Utilities)
* Click-drag primitive creation, Max-named Modifier List (incl. Melt, Skew, Squeeze,
  Slice, Noise, Push, Spherify, FFD), quad menus, Main Toolbar
* Open / merge 3ds Max (.max) files and FBX from 3ds Max
* V-Ray workflow: VRayMtl, VRayLight, VRaySun, VRayPhysicalCamera, VRayPlane, and
  detection of Chaos "V-Ray for Blender" when installed
"""

bl_info = {
    "name": "NotuoDesk 3ds Maxxed",
    "author": "NotuoDesk",
    "version": (1, 4, 0),
    "blender": (4, 2, 0),
    "location": "3D Viewport > Sidebar > Command Panel",
    "description": "Makes Blender look and work like 3ds Max",
    "category": "Interface",
}

import bpy
from bpy.props import BoolProperty, EnumProperty, IntProperty

from . import create, keymap, max_import, operators, overlay, prims, theme, ui_menus, ui_panel, viewport_menus, vray, mtl_editor


_prefs_cache = [None]


def get_prefs():
    """Add-on preferences (cached: this is called on every viewport redraw)."""
    p = _prefs_cache[0]
    if p is not None:
        try:
            p.bl_rna  # still valid?
            return p
        except ReferenceError:
            pass
    addon = bpy.context.preferences.addons.get(__package__)
    _prefs_cache[0] = addon.preferences if addon else None
    return _prefs_cache[0]


def _update_keymap(self, context):
    if self.use_keymap:
        keymap.register_keymaps()
    else:
        keymap.unregister_keymaps()


def _redraw(self, context):
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()


class MaxxedPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    use_keymap: BoolProperty(name="3ds Max Hotkeys", default=True, update=_update_keymap,
                             description="Use 3ds Max default keyboard shortcuts and mouse navigation")
    show_toolbar: BoolProperty(name="Main Toolbar", default=True, update=_redraw,
                               description="Show the 3ds Max Main Toolbar in the viewport tool header")
    show_statusbar: BoolProperty(name="Status Bar Type-In", default=True, update=_redraw,
                                 description="Show X/Y/Z, Auto Key and Set Key in the status bar")
    show_labels: BoolProperty(name="Viewport Labels", default=True, update=_redraw,
                              description="Draw [+] [Perspective] [Standard] [Default Shading] labels")
    max_menubar: BoolProperty(name="3ds Max Menu Bar", default=True, update=_redraw,
                              description="Replace Blender's top menus and workspace tabs with the 3ds Max menu bar")
    random_colors: BoolProperty(name="Random Object Colors", default=True,
                                description="Give new objects a random wireframe/object color like 3ds Max")
    first_run_done: BoolProperty(default=False)

    def draw(self, context):
        lay = self.layout
        row = lay.row()
        row.scale_y = 1.4
        row.operator("max.apply", text="Apply 3ds Max Look", icon="CHECKMARK")
        row.operator("max.restore", text="Restore Blender Look", icon="LOOP_BACK")
        col = lay.column(heading="Features")
        for p in ("use_keymap", "max_menubar", "show_toolbar", "show_statusbar", "show_labels", "random_colors"):
            col.prop(self, p)

        box = lay.box()
        box.label(text="Hotkeys (active while '3ds Max Hotkeys' is on)", icon="KEYINGSET")
        grid = box.grid_flow(columns=3, even_columns=True)
        for keys, what in HOTKEY_CHEATSHEET:
            r = grid.row()
            r.label(text=keys)
            r.label(text=what)


HOTKEY_CHEATSHEET = (
    ("Q / W / E / R", "Select / Move / Rotate / Scale"),
    ("MMB / Alt+MMB", "Pan / Orbit"),
    ("Ctrl+Alt+MMB, Wheel", "Zoom"),
    ("Z / Ctrl+Shift+Z", "Zoom Extents Sel / All"),
    ("Alt+W", "Maximize viewport (quad)"),
    ("T F L B K P U C", "Top Front Left Bottom Back Persp User Camera"),
    ("1 2 3 4 5 (6)", "Vertex Edge Border Poly Element (exit)"),
    ("H", "Select From Scene"),
    ("Ctrl+A / D / I", "Select All / None / Invert"),
    ("Ctrl/Alt+Click", "Add / Remove from selection"),
    ("Right-click", "Quad menu"),
    ("Ctrl+Right-click", "Modeling quad menu"),
    ("F3 / F4", "Wireframe / Edged Faces"),
    ("Alt+X", "See-Through"),
    ("Alt+Q", "Isolate Selection"),
    ("G / X / 7", "Grid / Gizmo / Statistics"),
    ("S / A", "Snaps / Angle Snap"),
    ("N / K", "Auto Key / Set Key"),
    ("Ctrl+V", "Clone"),
    ("Ctrl+C", "Camera from view"),
    ("M / 8 / F10", "Material Ed / Environment / Render Setup"),
    ("Shift+Q / F9", "Render"),
    ("F12", "Transform Type-In"),
    ("Ctrl+X", "Expert Mode"),
    ("O", "Adaptive Degradation"),
    ("Shift+E", "Extrude (Edit Poly)"),
    ("Ctrl+Shift+E / C", "Connect / Chamfer"),
    ("Alt+C", "Cut"),
    ("Alt+L / Alt+R", "Loop / Ring"),
    ("Backspace", "Remove"),
    ("Ctrl+PgUp/PgDn", "Grow / Shrink"),
    ("PgUp / PgDn", "Select parent / child"),
    (", . Home End /", "Frame -/+ First Last Play"),
)


_classes = (
    (MaxxedPreferences,) + prims.classes + operators.classes + create.classes + vray.classes + max_import.classes
    + viewport_menus.classes + mtl_editor.classes
    + ui_menus.classes
    + ui_panel.classes + tuple(ui_panel.ROLLOUTS)
)


def _first_run():
    """Apply the look the first time the add-on is enabled."""
    p = get_prefs()
    if p is None or p.first_run_done:
        return None
    try:
        bpy.ops.max.apply()
        p.first_run_done = True
    except Exception as exc:
        print(f"[3ds Maxxed] first-run apply failed: {exc}")
    return None


def _unlock_quads_once():
    try:
        operators.unlock_max_workspace_quads()
    except Exception as exc:
        print(f"[3ds Maxxed] unlock quads: {exc}")
    return None


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    wm = bpy.types.WindowManager
    wm.max_cmd_tab = EnumProperty(name="Command Panel", items=ui_panel.TABS, default="CREATE")
    wm.max_create_cat = EnumProperty(name="Category", items=ui_panel.CREATE_CATS, default="GEOMETRY")
    wm.max_sublevel = IntProperty(default=0)
    wm.max_create_sub = EnumProperty(name="Type", items=[("STANDARD", "Standard", ""), ("VRAY", "V-Ray", "")])
    prims.register_props()
    ui_panel.register_props()
    vray.register_props()
    mtl_editor.register_props()
    ui_menus.register_draw()
    max_import.register_menus()
    overlay.register()
    p = get_prefs()
    if p is None or p.use_keymap:
        keymap.register_keymaps()
    if not bpy.app.background:
        bpy.app.timers.register(_first_run, first_interval=0.5)
        bpy.app.timers.register(_unlock_quads_once, first_interval=1.0)


def unregister():
    _prefs_cache[0] = None
    keymap.unregister_keymaps()
    overlay.unregister()
    max_import.unregister_menus()
    ui_menus.unregister_draw()
    wm = bpy.types.WindowManager
    mtl_editor.unregister_props()
    vray.unregister_props()
    ui_panel.unregister_props()
    prims.unregister_props()
    for prop in ("max_cmd_tab", "max_create_cat", "max_create_sub", "max_sublevel"):
        if hasattr(wm, prop):
            delattr(wm, prop)
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
