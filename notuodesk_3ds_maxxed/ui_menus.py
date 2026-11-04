"""Quad menus, Modifier List, top menus, the Main Toolbar and the status bar."""

import bpy
from bpy.types import Menu

# (Max name, "BLENDER_TYPE[:option]") grouped like the 3ds Max Modifier List
MODIFIER_LIST = [
    ("MESH EDITING", [
        ("Edit Poly", "EDIT_POLY"), ("Symmetry", "MIRROR"), ("Mirror", "MIRROR"),
        ("Vertex Weld", "WELD"), ("ProOptimizer", "DECIMATE"), ("Optimize", "DECIMATE:PLANAR"),
        ("MultiRes", "DECIMATE"), ("Turn to Mesh", "TRIANGULATE"), ("Delete Mesh", "MASK"),
        ("Smooth", "EDGE_SPLIT"), ("Edit Normals", "NORMAL_EDIT"), ("Weighted Normals", "WEIGHTED_NORMAL"),
        ("Retopology", "REMESH"), ("Quadify Mesh", "REMESH:QUAD"),
    ]),
    ("SUBDIVISION", [
        ("TurboSmooth", "SUBSURF"), ("MeshSmooth", "SUBSURF"), ("OpenSubdiv", "SUBSURF"),
        ("Tessellate", "SUBSURF:SIMPLE"), ("Subdivide", "SUBSURF:SIMPLE"), ("HSDS", "MULTIRES"),
    ]),
    ("GEOMETRY", [
        ("Shell", "SOLIDIFY"), ("Chamfer", "BEVEL"), ("Array", "ARRAY"), ("Boolean", "BOOLEAN"),
        ("ProBoolean", "BOOLEAN"), ("Lattice", "WIREFRAME"), ("Skin", "SKIN"), ("Slice", "GN:SLICE"),
        ("Displace", "DISPLACE"),
    ]),
    ("PARAMETRIC DEFORMERS", [
        ("Bend", "SIMPLE_DEFORM:BEND"), ("Twist", "SIMPLE_DEFORM:TWIST"), ("Taper", "SIMPLE_DEFORM:TAPER"),
        ("Stretch", "SIMPLE_DEFORM:STRETCH"), ("Skew", "GN:SKEW"), ("Squeeze", "GN:SQUEEZE"),
        ("Melt", "GN:MELT"), ("Noise", "GN:NOISE"), ("Push", "GN:PUSH"), ("Spherify", "GN:SPHERIFY"),
        ("Relax", "LAPLACIANSMOOTH"), ("Smooth Deform", "SMOOTH"), ("Wave", "WAVE"),
        ("Ripple", "WAVE:RIPPLE"), ("Affect Region", "WARP"),
    ]),
    ("FREE FORM / SURFACE", [
        ("FFD 2x2x2", "LATTICE:2"), ("FFD 3x3x3", "LATTICE:3"), ("FFD 4x4x4", "LATTICE:4"),
        ("FFD Box", "LATTICE:5"), ("Shrink Wrap", "SHRINKWRAP"), ("Conform", "SHRINKWRAP:PROJECT"),
        ("Path Deform", "CURVE"), ("Skin Wrap", "SURFACE_DEFORM"), ("Skin Morph", "MESH_DEFORM"),
        ("Skin", "ARMATURE"), ("Linked XForm", "HOOK"),
    ]),
    ("UV / SHAPE / ANIMATION", [
        ("UVW Map", "UV_PROJECT"), ("Unwrap UVW", "UNWRAP"), ("UVW XForm", "UV_WARP"),
        ("Extrude", "EXTRUDE_SHAPE"), ("Lathe", "SCREW"), ("Sweep / Renderable", "SWEEP"),
        ("Cloth", "CLOTH"), ("Flex", "SOFT_BODY"), ("Point Cache", "MESH_CACHE"),
        ("Particle Flow", "PARTICLE_SYSTEM"), ("Hair and Fur", "PARTICLE_SYSTEM:HAIR"),
        ("Ocean (Blender)", "OCEAN"),
    ]),
]


class MAX_MT_modifier_list(Menu):
    bl_label = "Modifier List"
    bl_idname = "MAX_MT_modifier_list"

    def draw(self, context):
        row = self.layout.row()
        for title, items in MODIFIER_LIST:
            col = row.column()
            col.label(text=title)
            for label, spec in items:
                col.operator("max.add_modifier", text=label).kind = f"{spec}|{label}"


# ---------------------------------------------------------------------------
# Quad menus
# ---------------------------------------------------------------------------

def _quad(layout):
    """Return four columns: top-left, top-right, bottom-left, bottom-right."""
    split = layout.split(factor=0.5)
    left, right = split.column(), split.column()
    return left, right


def _header(col, text):
    col.label(text=text)
    col.separator()


class MAX_MT_quad(Menu):
    """3ds Max default quad menu (right-click)"""
    bl_label = "Quad Menu"
    bl_idname = "MAX_MT_quad"

    def draw(self, context):
        layout = self.layout
        layout.operator_context = "INVOKE_DEFAULT"
        left, right = _quad(layout)
        edit = context.mode == "EDIT_MESH"

        # top-left: display  |  top-right: tools 1
        _header(left, "display")
        left.operator("max.object_cmd", text="Isolate Selection").cmd = "ISOLATE"
        left.operator("max.object_cmd", text="Unfreeze All").cmd = "UNFREEZE"
        left.operator("max.object_cmd", text="Freeze Selection").cmd = "FREEZE"
        left.operator("max.select_by_name", text="Unhide by Name")
        left.operator("max.object_cmd", text="Unhide All").cmd = "UNHIDE"
        left.operator("max.object_cmd", text="Hide Unselected").cmd = "HIDE_UNSEL"
        left.operator("max.object_cmd", text="Hide Selection").cmd = "HIDE_SEL"

        if edit:
            _header(right, "tools 1")
            for op, text in (("REPEAT", "Repeat Last"), ("SWIFT_LOOP", "SwiftLoop"), ("CUT", "Cut"),
                             ("CONNECT", "Connect"), ("EXTRUDE", "Extrude"), ("CHAMFER", "Chamfer"),
                             ("WELD", "Weld"), ("TARGET_WELD", "Target Weld"), ("BRIDGE", "Bridge")):
                if op == "REPEAT":
                    right.operator("screen.repeat_last", text=text)
                else:
                    right.operator("max.edit_poly", text=text).op = op
        else:
            _header(right, "tools 1")
            right.menu("MAX_MT_sublevels", text="Sub-objects")
            right.operator("max.object_cmd", text="Reset XForm").cmd = "RESET_XFORM"
            right.operator("max.object_cmd", text="Center Pivot").cmd = "CENTER_PIVOT"
            right.operator("max.object_cmd", text="Attach").cmd = "ATTACH"
            right.operator("object.shade_smooth", text="Smooth Shading")
            right.operator("object.shade_flat", text="Flat Shading")

        left.separator()
        right.separator()

        # bottom-left: tools 2   |  bottom-right: transform
        _header(left, "tools 2")
        if edit:
            for op in ("REMOVE", "COLLAPSE", "DETACH", "INSET", "FLIP", "CAP", "MAKE_PLANAR", "RELAX"):
                left.operator("max.edit_poly", text=op.replace("_", " ").title()).op = op
        else:
            left.operator("max.object_cmd", text="Select and Link").cmd = "LINK"
            left.operator("max.object_cmd", text="Unlink Selection").cmd = "UNLINK"
            left.operator("max.object_cmd", text="Mirror").cmd = "MIRROR"
            left.operator("max.object_cmd", text="Display as Box").cmd = "DISPLAY_BOX"
            left.operator("max.object_cmd", text="See-Through").cmd = "SEE_THROUGH"

        _header(right, "transform")
        right.operator("wm.tool_set_by_id", text="Move").name = "builtin.move"
        right.operator("wm.tool_set_by_id", text="Rotate").name = "builtin.rotate"
        right.operator("wm.tool_set_by_id", text="Scale").name = "builtin.scale"
        right.operator("wm.tool_set_by_id", text="Select").name = "builtin.select_box"
        if not edit:
            right.operator("object.select_grouped", text="Select Similar").type = "TYPE"
            right.operator("max.clone", text="Clone")
            right.operator("max.transform_typein", text="Object Properties / Type-In")
            right.operator("max.open_editor", text="Curve Editor...").editor = "CURVE_EDITOR"
            right.operator("max.open_editor", text="Dope Sheet...").editor = "DOPE_SHEET"
            right.menu("MAX_MT_convert", text="Convert To:")
        else:
            right.operator("max.subobject", text="Top-level").level = 0


class MAX_MT_quad_modeling(Menu):
    """Modeling quad (Ctrl+Right-click)"""
    bl_label = "Modeling"
    bl_idname = "MAX_MT_quad_modeling"

    def draw(self, context):
        left, right = _quad(self.layout)
        _header(left, "modeling")
        for lvl, name in ((1, "Vertex"), (2, "Edge"), (3, "Border"), (4, "Polygon"), (5, "Element"), (0, "Top-level")):
            left.operator("max.subobject", text=name).level = lvl
        _header(right, "tools")
        if context.mode == "EDIT_MESH":
            for op in ("EXTRUDE", "BEVEL", "OUTLINE", "INSET", "CHAMFER", "CONNECT", "BRIDGE", "CUT",
                       "SWIFT_LOOP", "OPEN_EDGES", "GROW", "SHRINK", "LOOP", "RING"):
                right.operator("max.edit_poly", text=op.replace("_", " ").title()).op = op
        else:
            right.menu("MAX_MT_convert", text="Convert To:")
            right.menu("MAX_MT_modifier_list", text="Add Modifier")


class MAX_MT_sublevels(Menu):
    bl_label = "Sub-object"
    bl_idname = "MAX_MT_sublevels"

    def draw(self, context):
        for lvl, name in ((0, "Top-level"), (1, "Vertex"), (2, "Edge"), (3, "Border"), (4, "Polygon"), (5, "Element")):
            self.layout.operator("max.subobject", text=name).level = lvl


class MAX_MT_convert(Menu):
    bl_label = "Convert To"
    bl_idname = "MAX_MT_convert"

    def draw(self, context):
        self.layout.operator("max.object_cmd", text="Convert to Editable Poly").cmd = "CONVERT_POLY"
        self.layout.operator("max.object_cmd", text="Convert to Editable Spline").cmd = "CONVERT_SPLINE"


# ---------------------------------------------------------------------------
# Top menu bar additions
# ---------------------------------------------------------------------------

class MAX_MT_create(Menu):
    bl_label = "Create"
    bl_idname = "MAX_MT_create"

    def draw(self, context):
        from . import create
        lay = self.layout
        lay.label(text="Standard Primitives")
        for k, (label, icon, _, _) in create.PRIMITIVES.items():
            lay.operator("max.create", text=label, icon=icon).kind = k
        lay.separator()
        lay.label(text="Shapes")
        for k, label, icon in create.SHAPES:
            lay.operator("max.create_shape", text=label, icon=icon).kind = k
        lay.separator()
        lay.label(text="Lights")
        for k, label, icon in create.LIGHTS:
            lay.operator("max.create_light", text=label, icon=icon).kind = k
        lay.separator()
        lay.operator("max.create_camera", text="Target Camera", icon="CAMERA_DATA").target = True
        lay.operator("max.create_camera", text="Physical Camera", icon="CAMERA_DATA").target = False
        lay.operator("max.camera_from_view", text="Create Camera From View", icon="VIEW_CAMERA")
        lay.separator()
        lay.label(text="V-Ray")
        lay.operator_menu_enum("max.vray_light", "kind", text="VRayLight")
        lay.operator("max.vray_camera", text="VRayPhysicalCamera", icon="CAMERA_DATA")
        lay.operator("max.vray_plane", text="VRayPlane", icon="MESH_PLANE")


class MAX_MT_views(Menu):
    bl_label = "Views"
    bl_idname = "MAX_MT_views"

    def draw(self, context):
        lay = self.layout
        lay.operator_context = "INVOKE_DEFAULT"
        for v, key in (("TOP", "T"), ("BOTTOM", "B"), ("FRONT", "F"), ("BACK", "K"), ("LEFT", "L"),
                       ("PERSP", "P"), ("ORTHO", "U"), ("CAMERA", "C")):
            lay.operator("max.set_view", text=f"{v.title()}    ({key})").view = v
        lay.separator()
        lay.operator("max.zoom_extents", text="Zoom Extents Selected   (Z)")
        lay.operator("max.toggle_quad", text="Maximize Viewport Toggle   (Alt+W)")
        lay.operator("max.expert_mode", text="Expert Mode   (Ctrl+X)")
        lay.operator("max.toggle", text="Show Grid   (G)").what = "GRID"
        lay.operator("max.toggle", text="Wireframe / Shaded   (F3)").what = "WIREFRAME"
        lay.operator("max.toggle", text="Edged Faces   (F4)").what = "EDGED_FACES"
        lay.operator("max.toggle", text="xView: Show Statistics   (7)").what = "STATS"
        lay.prop(context.scene.render, "use_simplify", text="Adaptive Degradation   (O)")


class MAX_MT_rendering(Menu):
    bl_label = "Rendering"
    bl_idname = "MAX_MT_rendering"

    def draw(self, context):
        lay = self.layout
        lay.operator_context = "INVOKE_DEFAULT"
        lay.operator("render.render", text="Render   (Shift+Q)", icon="RENDER_STILL").use_viewport = True
        lay.operator("max.open_editor", text="Render Setup...   (F10)").editor = "RENDER_SETUP"
        lay.operator("max.open_editor", text="Environment...   (8)").editor = "ENVIRONMENT"
        lay.operator("max.open_editor", text="Material Editor...   (M)").editor = "MATERIAL"
        lay.operator("render.view_show", text="Rendered Frame Window")
        lay.separator()
        lay.menu("MAX_MT_vray", text="V-Ray", icon="SHADING_RENDERED")


class MAX_MT_edit(Menu):
    bl_label = "Edit"
    bl_idname = "MAX_MT_edit"

    def draw(self, context):
        lay = self.layout
        lay.operator_context = "INVOKE_DEFAULT"
        lay.operator("ed.undo", text="Undo", icon="LOOP_BACK")
        lay.operator("ed.redo", text="Redo", icon="LOOP_FORWARDS")
        lay.menu("TOPBAR_MT_undo_history", text="Undo History")
        lay.separator()
        lay.operator("max.delete", text="Delete")
        lay.operator("max.clone", text="Clone")
        lay.separator()
        lay.operator("wm.tool_set_by_id", text="Move").name = "builtin.move"
        lay.operator("wm.tool_set_by_id", text="Rotate").name = "builtin.rotate"
        lay.operator("wm.tool_set_by_id", text="Scale").name = "builtin.scale"
        lay.operator("max.transform_typein", text="Transform Type-In...")
        lay.separator()
        lay.operator("max.select_all", text="Select All").action = "SELECT"
        lay.operator("max.select_all", text="Select None").action = "DESELECT"
        lay.operator("max.select_all", text="Select Invert").action = "INVERT"
        lay.operator("object.select_grouped", text="Select Similar").type = "TYPE"
        lay.operator("max.select_by_name", text="Select by Name...")
        lay.separator()
        lay.menu("TOPBAR_MT_edit", text="More (Blender Edit)")


class MAX_MT_tools(Menu):
    bl_label = "Tools"
    bl_idname = "MAX_MT_tools"

    def draw(self, context):
        lay = self.layout
        lay.operator_context = "INVOKE_DEFAULT"
        lay.operator("max.open_editor", text="Scene Explorer").editor = "SCENE_EXPLORER"
        lay.separator()
        lay.operator("max.object_cmd", text="Isolate Selection").cmd = "ISOLATE"
        lay.operator("max.object_cmd", text="Mirror...").cmd = "MIRROR"
        lay.operator("max.add_modifier", text="Array...").kind = "ARRAY|Array"
        lay.operator("max.object_cmd", text="Align...").cmd = "ALIGN"
        lay.operator("object.duplicate_move", text="Snapshot")
        lay.separator()
        lay.operator("view3d.snap_cursor_to_selected", text="Grid to Selection")
        lay.operator("max.object_cmd", text="Reset XForm").cmd = "RESET_XFORM"


class MAX_MT_group(Menu):
    bl_label = "Group"
    bl_idname = "MAX_MT_group"

    def draw(self, context):
        lay = self.layout
        lay.operator("max.group", text="Group...").action = "GROUP"
        lay.operator("max.group", text="Ungroup").action = "UNGROUP"
        lay.separator()
        lay.operator("object.move_to_collection", text="Move to Layer (Collection)...")


class MAX_MT_animation(Menu):
    bl_label = "Animation"
    bl_idname = "MAX_MT_animation"

    def draw(self, context):
        lay = self.layout
        lay.operator_context = "INVOKE_DEFAULT"
        lay.operator("max.toggle", text="Toggle Auto Key   (N)").what = "AUTOKEY"
        lay.operator("max.set_key", text="Set Key   (K)")
        lay.operator("anim.keyframe_delete_v3d", text="Delete Keys")
        lay.separator()
        lay.operator_menu_enum("object.constraint_add", "type", text="Constraints")
        lay.separator()
        lay.operator("screen.animation_play", text="Play / Stop   (/)")


class MAX_MT_graph_editors(Menu):
    bl_label = "Graph Editors"
    bl_idname = "MAX_MT_graph_editors"

    def draw(self, context):
        lay = self.layout
        lay.operator_context = "INVOKE_DEFAULT"
        lay.operator("max.open_editor", text="Track View - Curve Editor...").editor = "CURVE_EDITOR"
        lay.operator("max.open_editor", text="Track View - Dope Sheet...").editor = "DOPE_SHEET"
        lay.operator("max.open_editor", text="Schematic View...").editor = "SCHEMATIC"


class MAX_MT_customize(Menu):
    bl_label = "Customize"
    bl_idname = "MAX_MT_customize"

    def draw(self, context):
        lay = self.layout
        lay.operator_context = "INVOKE_DEFAULT"
        lay.operator("screen.userpref_show", text="Preferences...")
        lay.operator("preferences.addon_show", text="Hotkeys (3ds Maxxed)...").module = __package__
        lay.separator()
        lay.operator("max.apply", text="Apply 3ds Max Look (reset layout)")
        lay.operator("max.restore", text="Restore Blender Look")
        lay.separator()
        from . import updater
        if updater.status["state"] == "available":
            lay.operator("max.install_update", text=f"Update to {updater.status['latest']}", icon="IMPORT")
        lay.operator("max.check_update", text="Check for Updates", icon="FILE_REFRESH")
        lay.separator()
        lay.menu("TOPBAR_MT_window", text="Window")


class MAX_MT_scripting(Menu):
    bl_label = "Scripting"
    bl_idname = "MAX_MT_scripting"

    def draw(self, context):
        lay = self.layout
        lay.operator_context = "INVOKE_DEFAULT"
        lay.operator("max.open_editor", text="Script Editor...").editor = "SCRIPT_EDITOR"
        lay.operator("max.open_editor", text="Python Listener...").editor = "LISTENER"


class MAX_MT_workspaces(Menu):
    bl_label = "Workspaces"
    bl_idname = "MAX_MT_workspaces"

    def draw(self, context):
        for ws in bpy.data.workspaces:
            self.layout.operator("max.set_workspace", text=ws.name,
                                 icon="CHECKMARK" if ws == context.window.workspace else "BLANK1").name = ws.name


MAX_MENUBAR = (
    ("TOPBAR_MT_file", "File"), ("MAX_MT_edit", "Edit"), ("MAX_MT_tools", "Tools"),
    ("MAX_MT_group", "Group"), ("MAX_MT_views", "Views"), ("MAX_MT_create", "Create"),
    ("MAX_MT_modifier_list", "Modifiers"), ("MAX_MT_animation", "Animation"),
    ("MAX_MT_graph_editors", "Graph Editors"), ("MAX_MT_rendering", "Rendering"),
    ("MAX_MT_customize", "Customize"), ("MAX_MT_scripting", "Scripting"), ("TOPBAR_MT_help", "Help"),
)

_orig_topbar = {}


def _menubar_on():
    from . import get_prefs
    p = get_prefs()
    return p is None or p.max_menubar


def topbar_draw_left(self, context):
    if not _menubar_on():
        return _orig_topbar["left"](self, context)
    lay = self.layout
    lay.menu("TOPBAR_MT_blender", text="", icon="BLENDER")
    for idname, text in MAX_MENUBAR:
        lay.menu(idname, text=text)


def topbar_draw_right(self, context):
    if not _menubar_on():
        return _orig_topbar["right"](self, context)
    lay = self.layout
    screen = context.screen
    if not screen.show_statusbar:
        lay.template_reports_banner()
        lay.template_running_jobs()
    row = lay.row(align=True)
    row.label(text="Workspaces:")
    sub = row.row(align=True)
    sub.ui_units_x = 7
    sub.menu("MAX_MT_workspaces", text=context.window.workspace.name)


# ---------------------------------------------------------------------------
# Main Toolbar (drawn at the start of the viewport tool header)
# ---------------------------------------------------------------------------

def _active_tool(context):
    try:
        return context.workspace.tools.from_space_view3d_mode(context.mode, create=False).idname
    except Exception:
        return ""


def view3d_header_draw(self, context):
    """In the '3ds Max' workspace the viewport header becomes the 3ds Max Main Toolbar."""
    from . import get_prefs
    from .operators import WS_NAME
    p = get_prefs()
    if (p is None or p.show_toolbar) and context.workspace and context.workspace.name == WS_NAME:
        draw_main_toolbar(self, context)
        lay = self.layout
        lay.separator_spacer()
        row = lay.row(align=True)
        row.prop(context.scene.tool_settings, "use_keyframe_insert_auto", text="", icon="REC")
        space = context.space_data
        row = lay.row(align=True)
        row.prop(space.overlay, "show_overlays", text="", icon="OVERLAY")
        row.popover(panel="VIEW3D_PT_overlay", text="")
        row = lay.row(align=True)
        row.prop(space.shading, "type", text="", expand=True)
        row.popover(panel="VIEW3D_PT_shading", text="")
        return
    _orig_topbar["v3d"](self, context)


def draw_main_toolbar(self, context):
    lay = self.layout
    ts = context.tool_settings
    tool = _active_tool(context)

    row = lay.row(align=True)
    row.operator("ed.undo", text="", icon="LOOP_BACK")
    row.operator("ed.redo", text="", icon="LOOP_FORWARDS")
    row = lay.row(align=True)
    row.operator("max.object_cmd", text="", icon="LINKED").cmd = "LINK"
    row.operator("max.object_cmd", text="", icon="UNLINKED").cmd = "UNLINK"

    row = lay.row(align=True)
    row.operator("max.select_by_name", text="", icon="VIEWZOOM")
    row.operator("wm.tool_set_by_id", text="", icon="SELECT_SET",
                 depress=tool == "builtin.select_box").name = "builtin.select_box"
    row.operator("wm.tool_set_by_id", text="", icon="MESH_CIRCLE",
                 depress=tool == "builtin.select_circle").name = "builtin.select_circle"
    row.operator("wm.tool_set_by_id", text="", icon="SELECT_INTERSECT",
                 depress=tool == "builtin.select_lasso").name = "builtin.select_lasso"

    row = lay.row(align=True)
    row.scale_x = 1.1
    for idname, icon in (("builtin.move", "OBJECT_ORIGIN"), ("builtin.rotate", "ORIENTATION_GIMBAL"),
                         ("builtin.scale", "FULLSCREEN_ENTER")):
        row.operator("wm.tool_set_by_id", text="", icon=icon, depress=(tool == idname)).name = idname

    slot = context.scene.transform_orientation_slots[0]
    sub = lay.row(align=True)
    sub.ui_units_x = 4.5
    sub.prop(slot, "type", text="")
    sub = lay.row(align=True)
    sub.prop(ts, "transform_pivot_point", text="", icon_only=True)

    row = lay.row(align=True)
    row.prop(ts, "use_snap", text="", icon="SNAP_ON" if ts.use_snap else "SNAP_OFF")
    row.prop(ts, "use_snap_rotate", text="", icon="DRIVER_ROTATIONAL_DIFFERENCE")
    row.prop(ts, "use_snap_scale", text="", icon="MOD_PHYSICS")

    row = lay.row(align=True)
    row.operator("max.object_cmd", text="", icon="MOD_MIRROR").cmd = "MIRROR"
    row.operator("max.object_cmd", text="", icon="ALIGN_CENTER").cmd = "ALIGN"
    row = lay.row(align=True)
    row.operator("max.open_editor", text="", icon="OUTLINER").editor = "SCENE_EXPLORER"
    row.operator("max.open_editor", text="", icon="GRAPH").editor = "CURVE_EDITOR"
    row.operator("max.open_editor", text="", icon="NODETREE").editor = "SCHEMATIC"
    row.operator("max.open_editor", text="", icon="MATERIAL").editor = "MATERIAL"
    row = lay.row(align=True)
    row.operator("max.open_editor", text="", icon="SCENE").editor = "RENDER_SETUP"
    row.operator("render.render", text="", icon="RENDER_STILL").use_viewport = True


# ---------------------------------------------------------------------------
# Status bar: X / Y / Z type-in, Auto Key, Set Key
# ---------------------------------------------------------------------------

def draw_statusbar(self, context):
    from . import get_prefs
    p = get_prefs()
    if p is not None and not p.show_statusbar:
        return
    lay = self.layout
    n = len(context.selected_objects) if context.mode == "OBJECT" else 0
    row = lay.row(align=True)
    row.label(text=f"{n} Object{'s' if n != 1 else ''} Selected" if context.mode == "OBJECT"
              else context.mode.replace("_", " ").title())
    ob = context.active_object
    if ob is not None and context.mode == "OBJECT":
        row = lay.row(align=True)
        row.ui_units_x = 18
        row.prop(ob, "location", index=0, text="X")
        row.prop(ob, "location", index=1, text="Y")
        row.prop(ob, "location", index=2, text="Z")
    space = context.space_data if context.space_data and context.space_data.type == "VIEW_3D" else None
    unit = context.scene.unit_settings.scale_length or 1.0
    lay.label(text=f"Grid = {unit:g}m")
    ts = context.tool_settings
    row = lay.row(align=True)
    row.alert = ts.use_keyframe_insert_auto
    row.prop(ts, "use_keyframe_insert_auto", text="Auto Key", toggle=True)
    row.operator("max.set_key", text="Set Key")


classes = (
    MAX_MT_modifier_list, MAX_MT_quad, MAX_MT_quad_modeling, MAX_MT_sublevels, MAX_MT_convert,
    MAX_MT_create, MAX_MT_views, MAX_MT_rendering, MAX_MT_edit, MAX_MT_tools, MAX_MT_group,
    MAX_MT_animation, MAX_MT_graph_editors, MAX_MT_customize, MAX_MT_scripting, MAX_MT_workspaces,
)


def register_draw():
    tb = bpy.types.TOPBAR_HT_upper_bar
    _orig_topbar["left"] = tb.draw_left
    _orig_topbar["right"] = tb.draw_right
    tb.draw_left = topbar_draw_left
    tb.draw_right = topbar_draw_right
    hd = bpy.types.VIEW3D_HT_header
    _orig_topbar["v3d"] = hd.draw
    hd.draw = view3d_header_draw
    bpy.types.STATUSBAR_HT_header.append(draw_statusbar)


def unregister_draw():
    tb = bpy.types.TOPBAR_HT_upper_bar
    if _orig_topbar:
        tb.draw_left = _orig_topbar["left"]
        tb.draw_right = _orig_topbar["right"]
    if "v3d" in _orig_topbar:
        bpy.types.VIEW3D_HT_header.draw = _orig_topbar["v3d"]
    bpy.types.STATUSBAR_HT_header.remove(draw_statusbar)
