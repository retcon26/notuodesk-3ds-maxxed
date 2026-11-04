"""The 3ds Max Command Panel: tab row on top, collapsible rollouts below."""

import bpy
from bpy.props import IntProperty
from bpy.types import Menu, Panel, UIList

from . import create, prims
from .operators import EDIT_POLY_OPS, current_level

EP_LABELS = {k: n for k, n, _ in EDIT_POLY_OPS}

TABS = [
    ("CREATE", "Create", "Create", "ADD", 0),
    ("MODIFY", "Modify", "Modify", "MODIFIER", 1),
    ("HIERARCHY", "Hierarchy", "Hierarchy", "OUTLINER", 2),
    ("MOTION", "Motion", "Motion", "ANIM", 3),
    ("DISPLAY", "Display", "Display", "RESTRICT_VIEW_OFF", 4),
    ("UTILITIES", "Utilities", "Utilities", "TOOL_SETTINGS", 5),
]

CREATE_CATS = [
    ("GEOMETRY", "Geometry", "Standard Primitives", "MESH_UVSPHERE", 0),
    ("SHAPES", "Shapes", "Splines", "CURVE_BEZCURVE", 1),
    ("LIGHTS", "Lights", "Standard", "LIGHT", 2),
    ("CAMERAS", "Cameras", "Standard", "CAMERA_DATA", 3),
    ("HELPERS", "Helpers", "Standard", "EMPTY_AXIS", 4),
]

BASE_NAMES = {
    "MESH": "Editable Poly", "CURVE": "Editable Spline", "FONT": "Text", "SURFACE": "NURBS Surface",
    "LIGHT": "Light", "CAMERA": "Camera", "EMPTY": "Dummy", "ARMATURE": "Bones", "META": "Blob Mesh",
    "LATTICE": "FFD", "GREASEPENCIL": "Grease Pencil", "CURVES": "Hair", "POINTCLOUD": "Point Cloud",
    "VOLUME": "Volume",
}

SUBLEVEL_ICONS = {1: "VERTEXSEL", 2: "EDGESEL", 3: "MOD_EDGESPLIT", 4: "FACESEL", 5: "MESH_CUBE"}

SKIP_PROPS = {
    "rna_type", "name", "type", "is_active", "is_override_data", "use_apply_on_spline",
    "persistent_uid", "execution_time", "use_pin_to_last",
}


def base_name(ob):
    if ob.type == "MESH" and ob.max_prim.kind:
        return prims.PRIMITIVES[ob.max_prim.kind][0]
    return BASE_NAMES.get(ob.type, ob.type.title())


def tab(context):
    return context.window_manager.max_cmd_tab


# ---------------------------------------------------------------------------
# Modifier stack list
# ---------------------------------------------------------------------------

def _stack_get(ob):
    if bpy.context.mode.startswith("EDIT"):
        return -1          # sub-object editing happens at the base of the stack
    act = ob.modifiers.active
    if act is not None and act.is_active:
        return ob.modifiers.find(act.name)
    return -1


def _stack_set(ob, value):
    if 0 <= value < len(ob.modifiers):
        ob.modifiers.active = ob.modifiers[value]


class MAX_UL_stack(UIList):
    """Modifier stack, newest on top like 3ds Max"""

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.prop(item, "show_viewport", text="", emboss=False, icon_only=True)
        row.prop(item, "name", text="", emboss=False)

    def filter_items(self, context, data, propname):
        n = len(getattr(data, propname))
        return [self.bitflag_filter_item] * n, list(reversed(range(n)))

    def draw_filter(self, context, layout):
        pass


SUBTYPES = {
    "GEOMETRY": (("STANDARD", "Standard Primitives"), ("VRAY", "V-Ray")),
    "LIGHTS": (("STANDARD", "Standard"), ("VRAY", "V-Ray")),
    "CAMERAS": (("STANDARD", "Standard"), ("VRAY", "V-Ray")),
    "SHAPES": (("STANDARD", "Splines"),),
    "HELPERS": (("STANDARD", "Standard"),),
}


def subtype_label(context):
    wm = context.window_manager
    opts = dict(SUBTYPES[wm.max_create_cat])
    return opts.get(wm.max_create_sub, next(iter(opts.values())))


class MAX_MT_create_subcat(Menu):
    bl_label = "Category"
    bl_idname = "MAX_MT_create_subcat"

    def draw(self, context):
        wm = context.window_manager
        for key, label in SUBTYPES[wm.max_create_cat]:
            self.layout.prop_enum(wm, "max_create_sub", key, text=label)


# ---------------------------------------------------------------------------
# Command Panel (header area: tabs, name, modifier list, stack)
# ---------------------------------------------------------------------------

class MAX_PT_command_panel(Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Command Panel"
    bl_label = "Command Panel"
    bl_options = {"HIDE_HEADER"}
    bl_order = 0

    def draw(self, context):
        wm = context.window_manager
        layout = self.layout
        row = layout.row(align=True)
        row.alignment = "LEFT"
        row.prop(wm, "max_cmd_tab", expand=True, icon_only=True)
        layout.separator(factor=0.3)
        t = wm.max_cmd_tab
        ob = context.active_object

        if t == "CREATE":
            row = layout.row(align=True)
            row.alignment = "LEFT"
            row.prop(wm, "max_create_cat", expand=True, icon_only=True)
            layout.menu("MAX_MT_create_subcat", text=subtype_label(context))

        elif t == "MODIFY":
            if ob is None:
                return
            row = layout.row(align=True)
            split = row.split(factor=0.88, align=True)
            split.prop(ob, "name", text="")
            split.prop(ob, "color", text="")
            layout.menu("MAX_MT_modifier_list", text="Modifier List")

            col = layout.column(align=True)
            col.template_list("MAX_UL_stack", "", ob, "modifiers", ob, "max_stack_index",
                              rows=3, maxrows=8, sort_lock=True)
            base = col.row(align=True)
            no_active = _stack_get(ob) < 0
            base.operator("max.modifier_set_active", text=base_name(ob), depress=no_active,
                          icon="MESH_DATA" if ob.type == "MESH" else "OBJECT_DATA").name = ""

            # stack tool icons
            active = ob.modifiers.active if _stack_get(ob) >= 0 else None
            row = layout.row(align=True)
            row.alignment = "LEFT"
            if active:
                row.prop(active, "show_in_editmode", text="", icon="EDITMODE_HLT")
                row.prop(active, "show_on_cage", text="", icon="MESH_DATA")
                row.operator("object.make_single_user", text="", icon="DUPLICATE").object = True
                row.operator("object.modifier_remove", text="", icon="TRASH").modifier = active.name
                row.separator()
                row.operator("object.modifier_move_down", text="", icon="TRIA_UP").modifier = active.name
                row.operator("object.modifier_move_up", text="", icon="TRIA_DOWN").modifier = active.name
                row.operator("object.modifier_apply", text="", icon="CHECKMARK").modifier = active.name
            else:
                row.operator("max.object_cmd", text="", icon="CHECKMARK").cmd = "CONVERT_POLY"
                row.label(text="")


# ---------------------------------------------------------------------------
# Rollouts
# ---------------------------------------------------------------------------

def _split_col(layout):
    col = layout.column(align=True)
    col.use_property_split = True
    col.use_property_decorate = False
    return col


def draw_prim_params(layout, ob):
    p = ob.max_prim
    col = _split_col(layout)
    for field in prims.UI_FIELDS[p.kind]:
        if field is None:
            col.separator()
            continue
        prop, label = field
        col.prop(p, prop, text=label)


MELT_PRESETS = (("Ice", 2.0), ("Glass", 0.5), ("Jelly", 0.4), ("Plastic", 0.1))


def draw_modifier_params(layout, mod):
    col = _split_col(layout)
    if mod.type == "NODES":
        from . import gn_mods
        for ident, name in gn_mods.inputs(mod):
            data, prop = gn_mods.input_ref(mod, ident)
            try:
                col.prop(data, prop, text=name)
            except Exception:
                pass
        if gn_mods.is_melt(mod):
            layout.label(text="Solidity:")
            g = _grid(layout, 2)
            for label, val in MELT_PRESETS:
                g.operator("max.melt_preset", text=label).value = val
            layout.separator()
            row = layout.row(align=True)
            row.scale_y = 1.3
            row.operator("max.animate_melt", text="Animate Melt", icon="PLAY")
            row.operator("max.key_melt", text="", icon="KEY_HLT")
            layout.label(text="Tip: Auto Key (N) keys Amount as you drag it", icon="INFO")
        return
    for p in mod.bl_rna.properties:
        ident = p.identifier
        if (ident in SKIP_PROPS or p.is_readonly or p.type == "COLLECTION"
                or ident.startswith(("open_", "ui_", "show_"))):
            continue
        try:
            col.prop(mod, ident)
        except Exception:
            pass


def draw_base_params(layout, ob):
    col = _split_col(layout)
    if ob.type == "MESH":
        col.prop(ob, "dimensions", text="Size")
        me = ob.data
        layout.label(text=f"Verts: {len(me.vertices):,}    Polys: {len(me.polygons):,}")
    elif ob.type in {"CURVE", "FONT"}:
        cu = ob.data
        col.prop(cu, "bevel_depth", text="Thickness")
        col.prop(cu, "bevel_resolution", text="Sides")
        col.prop(cu, "extrude", text="Extrude")
        col.prop(cu, "resolution_u", text="Steps")
        if ob.type == "FONT":
            col.prop(cu, "body", text="Text")
            col.prop(cu, "size")
            col.prop(cu, "space_character", text="Kerning")
    elif ob.type == "LIGHT":
        li = ob.data
        col.prop(li, "type", text="Type")
        col.prop(li, "color")
        col.prop(li, "energy", text="Multiplier")
        if li.type == "SPOT":
            col.prop(li, "spot_size", text="Falloff")
            col.prop(li, "spot_blend", text="Hotspot Blend")
        col.prop(li, "use_shadow", text="Shadows")
    elif ob.type == "CAMERA" and ob.data.max_vray.enabled:
        from . import vray
        vray.draw_vray_camera(layout, ob.data)
    elif ob.type == "CAMERA":
        cam = ob.data
        col.prop(cam, "lens", text="Lens")
        col.prop(cam, "sensor_width", text="Film Width")
        col.prop(cam, "type", text="Type")
        col.prop(cam, "clip_start", text="Clip Near")
        col.prop(cam, "clip_end", text="Clip Far")
        col.prop(cam.dof, "use_dof", text="Depth of Field")
    elif ob.type == "EMPTY":
        col.prop(ob, "empty_display_type", text="Display")
        col.prop(ob, "empty_display_size", text="Size")
    else:
        layout.label(text=base_name(ob))


def _btn(container, op, text=None):
    container.operator("max.edit_poly", text=text or EP_LABELS[op]).op = op


def _grid(layout, cols=2):
    return layout.grid_flow(row_major=True, columns=cols, even_columns=True, align=True)


ROLLOUTS = []


def rollout(label, tabs, order, closed=False):
    """Decorator registering a draw function as a collapsible 3ds Max rollout."""
    def deco(fn):
        poll_fn = getattr(fn, "poll", None)
        ns = {
            "bl_space_type": "VIEW_3D",
            "bl_region_type": "UI",
            "bl_category": "Command Panel",
            "bl_parent_id": "MAX_PT_command_panel",
            "bl_label": label,
            "bl_order": order,
            "bl_options": {"DEFAULT_CLOSED"} if closed else set(),
            "draw": lambda self, context: fn(self.layout, context),
            "poll": classmethod(lambda cls, context: tab(context) in tabs and (poll_fn is None or poll_fn(context))),
        }
        cls = type("MAX_PT_" + fn.__name__, (Panel,), ns)
        ROLLOUTS.append(cls)
        return fn
    return deco


def when(pred):
    def deco(fn):
        fn.poll = pred
        return fn
    return deco


# ----- Create ---------------------------------------------------------------

@rollout("Object Type", {"CREATE"}, 1)
def create_object_type(layout, context):
    wm = context.window_manager
    cat = wm.max_create_cat
    g = _grid(layout)
    vray_sub = wm.max_create_sub == "VRAY" and len(SUBTYPES[cat]) > 1
    if vray_sub and cat == "GEOMETRY":
        g.operator("max.vray_plane", text="VRayPlane")
    elif vray_sub and cat == "LIGHTS":
        for k, label in (("PLANE", "VRayLight"), ("DISC", "VRayLight Disc"), ("SPHERE", "VRayLight Sphere"),
                         ("DOME", "VRayLight Dome"), ("SUN", "VRaySun"), ("IES", "VRayIES")):
            g.operator("max.vray_light", text=label).kind = k
    elif vray_sub and cat == "CAMERAS":
        g.operator("max.vray_camera", text="VRayPhysicalCamera")
    elif cat == "GEOMETRY":
        for k, (label, icon, _, _) in prims.PRIMITIVES.items():
            g.operator("max.create", text=label, depress=(create.MAX_OT_create.active_kind == k)).kind = k
    elif cat == "SHAPES":
        for k, label, icon in create.SHAPES:
            g.operator("max.create_shape", text=label).kind = k
    elif cat == "LIGHTS":
        for k, label, icon in create.LIGHTS:
            g.operator("max.create_light", text=label).kind = k
    elif cat == "CAMERAS":
        g.operator("max.create_camera", text="Target").target = True
        g.operator("max.create_camera", text="Physical").target = False
        layout.operator("max.camera_from_view", text="Create Camera From View")
    elif cat == "HELPERS":
        for k, label, icon in create.HELPERS:
            g.operator("max.create_helper", text=label).kind = k


@rollout("Name and Color", {"CREATE"}, 2)
def create_name_color(layout, context):
    ob = context.active_object
    if ob is None:
        return
    row = layout.row(align=True)
    split = row.split(factor=0.88, align=True)
    split.prop(ob, "name", text="")
    split.prop(ob, "color", text="")


# ----- Parameters (Create right after creation, and Modify) -------------------

def _has_params(context):
    ob = context.active_object
    if ob is None:
        return False
    if tab(context) == "CREATE":
        return ob.type == "MESH" and bool(ob.max_prim.kind)
    if context.mode == "EDIT_MESH" or (ob.type == "MESH" and not ob.max_prim.kind and _stack_get(ob) < 0):
        return False   # Editable Poly shows Selection / Edit Geometry instead
    return True


@rollout("Parameters", {"CREATE", "MODIFY"}, 3)
@when(_has_params)
def parameters(layout, context):
    ob = context.active_object
    idx = _stack_get(ob)
    if idx >= 0:
        draw_modifier_params(layout, ob.modifiers[idx])
    elif ob.type == "MESH" and ob.max_prim.kind:
        draw_prim_params(layout, ob)
    else:
        draw_base_params(layout, ob)


# ----- Material (VRayMtl) ---------------------------------------------------------

@rollout("Material", {"MODIFY"}, 9, closed=True)
@when(lambda c: c.active_object is not None and c.active_object.type in {"MESH", "CURVE", "FONT", "SURFACE", "META"})
def material_rollout(layout, context):
    from . import vray
    ob = context.active_object
    mat = ob.active_material
    row = layout.row(align=True)
    row.operator_menu_enum("max.vray_material", "preset", text="New VRayMtl")
    if mat is None:
        layout.label(text="No material")
        return
    layout.prop(mat, "name", text="")
    row = layout.row(align=True)
    bitmap = mat.get("max_bitmap")
    has_img = mat.use_nodes and any(n.type == "TEX_IMAGE" and n.image for n in mat.node_tree.nodes)
    if bitmap and not has_img:
        row.alert = True
        row.label(text=f"Missing bitmap: {bitmap}", icon="ERROR")
        row = layout.row(align=True)
    row.operator("max.load_bitmap", text="Load Bitmap...", icon="IMAGE_DATA")
    if mat.get("max_vray"):
        vray.draw_vraymtl(layout, mat)
    else:
        col = _split_col(layout)
        col.prop(mat, "diffuse_color", text="Viewport Color")
        layout.label(text="Not a VRayMtl: edit in Material Editor (M)")


# ----- Editable Poly ------------------------------------------------------------

def _is_poly(context):
    ob = context.active_object
    if ob is None or ob.type != "MESH":
        return False
    if context.mode == "EDIT_MESH":
        return True
    return not ob.max_prim.kind and _stack_get(ob) < 0


@rollout("Selection", {"MODIFY"}, 4)
@when(_is_poly)
def poly_selection(layout, context):
    lvl = current_level(context)
    row = layout.row(align=True)
    row.scale_y = 1.3
    for i in range(1, 6):
        row.operator("max.subobject", text="", icon=SUBLEVEL_ICONS[i], depress=(lvl == i)).level = i
    if context.mode == "EDIT_MESH":
        g = _grid(layout)
        for op in ("SHRINK", "GROW", "RING", "LOOP"):
            _btn(g, op)
        _btn(layout, "OPEN_EDGES")
    me = context.active_object.data
    if context.mode != "EDIT_MESH":
        layout.label(text=f"Verts: {len(me.vertices):,}   Polys: {len(me.polygons):,}")
    else:
        layout.label(text="Whole Object Selected" if lvl == 0 else f"{me.total_vert_sel} Vertices Selected"
                     if lvl == 1 else f"{me.total_edge_sel} Edges Selected" if lvl in (2, 3)
                     else f"{me.total_face_sel} Polygons Selected")


@rollout("Edit Sub-Object", {"MODIFY"}, 5)
@when(lambda c: _is_poly(c) and c.mode == "EDIT_MESH")
def poly_edit_level(layout, context):
    lvl = current_level(context) or 1
    per_level = {
        1: ("REMOVE", "BREAK", "EXTRUDE", "WELD", "CHAMFER", "TARGET_WELD", "CONNECT"),
        2: ("REMOVE", "EXTRUDE", "WELD", "CHAMFER", "TARGET_WELD", "BRIDGE", "CONNECT"),
        3: ("EXTRUDE", "CAP", "CHAMFER", "BRIDGE", "CONNECT"),
        4: ("EXTRUDE", "OUTLINE", "BEVEL", "INSET", "BRIDGE", "FLIP"),
        5: ("FLIP", "DETACH"),
    }[lvl]
    g = _grid(layout)
    for op in per_level:
        _btn(g, op)
    if lvl in (2, 3):
        layout.operator("mesh.edge_face_add", text="Create Shape / Fill")


@rollout("Edit Geometry", {"MODIFY"}, 6)
@when(_is_poly)
def poly_edit_geometry(layout, context):
    if context.mode != "EDIT_MESH":
        g = _grid(layout)
        g.operator("max.object_cmd", text="Attach").cmd = "ATTACH"
        g.operator("max.object_cmd", text="Reset XForm").cmd = "RESET_XFORM"
        return
    layout.operator("screen.repeat_last", text="Repeat Last")
    g = _grid(layout)
    for op in ("COLLAPSE", "DETACH", "SLICE_PLANE", "CUT", "SWIFT_LOOP", "MSMOOTH",
               "TESSELLATE", "MAKE_PLANAR", "RELAX"):
        _btn(g, op)
    g = _grid(layout)
    for op in ("HIDE_SEL", "UNHIDE", "HIDE_UNSEL"):
        _btn(g, op)


# ----- Hierarchy ---------------------------------------------------------------

@rollout("Adjust Pivot", {"HIERARCHY"}, 10)
def hier_pivot(layout, context):
    ts = context.tool_settings
    col = layout.column(align=True)
    col.prop(ts, "use_transform_data_origin", text="Affect Pivot Only", toggle=True)
    col.prop(ts, "use_transform_skip_children", text="Don't Affect Children", toggle=True)
    layout.label(text="Alignment:")
    col = layout.column(align=True)
    col.operator("max.object_cmd", text="Center to Object").cmd = "CENTER_PIVOT"
    col.operator("max.object_cmd", text="Align to World").cmd = "PIVOT_TO_WORLD"
    col.operator("max.object_cmd", text="Center Object to Pivot").cmd = "OBJECT_TO_PIVOT"
    col.operator("object.origin_set", text="Pivot to 3D Cursor").type = "ORIGIN_CURSOR"


@rollout("Adjust Transform", {"HIERARCHY"}, 11)
def hier_transform(layout, context):
    col = layout.column(align=True)
    col.operator("max.object_cmd", text="Reset XForm").cmd = "RESET_XFORM"
    col.operator("object.transform_apply", text="Reset Transform").location = True


@rollout("Link Info", {"HIERARCHY"}, 12)
def hier_link(layout, context):
    ob = context.active_object
    if ob:
        _split_col(layout).prop(ob, "parent", text="Parent")
    g = _grid(layout)
    g.operator("max.object_cmd", text="Select and Link").cmd = "LINK"
    g.operator("max.object_cmd", text="Unlink Selection").cmd = "UNLINK"
    layout.operator("object.select_hierarchy", text="Select Children").direction = "CHILD"


# ----- Motion ----------------------------------------------------------------

@rollout("Animation", {"MOTION"}, 20)
def motion_anim(layout, context):
    scene = context.scene
    ts = context.tool_settings
    row = layout.row(align=True)
    row.prop(ts, "use_keyframe_insert_auto", text="Auto Key", toggle=True, icon="REC")
    row.operator("max.set_key", text="Set Key", icon="KEY_HLT")
    layout.operator("anim.keyframe_delete_v3d", text="Delete Keys")
    col = _split_col(layout)
    col.prop(scene, "frame_current", text="Frame")
    col.prop(scene, "frame_start", text="Start Time")
    col.prop(scene, "frame_end", text="End Time")
    col.prop(scene.render, "fps", text="Frame Rate")


@rollout("Editors", {"MOTION"}, 21, closed=True)
def motion_editors(layout, context):
    layout.operator("max.open_editor", text="Curve Editor").editor = "CURVE_EDITOR"
    layout.operator("max.open_editor", text="Dope Sheet").editor = "DOPE_SHEET"


@rollout("Trajectories", {"MOTION"}, 22, closed=True)
def motion_traj(layout, context):
    g = _grid(layout)
    g.operator("object.paths_calculate", text="Show")
    g.operator("object.paths_clear", text="Hide")


# ----- Display ---------------------------------------------------------------

@rollout("Hide", {"DISPLAY"}, 30)
def disp_hide(layout, context):
    g = _grid(layout)
    g.operator("max.object_cmd", text="Hide Selected").cmd = "HIDE_SEL"
    g.operator("max.object_cmd", text="Hide Unselected").cmd = "HIDE_UNSEL"
    g.operator("max.select_by_name", text="Hide by Name...")
    g.operator("max.object_cmd", text="Unhide All").cmd = "UNHIDE"


@rollout("Freeze", {"DISPLAY"}, 31)
def disp_freeze(layout, context):
    g = _grid(layout)
    g.operator("max.object_cmd", text="Freeze Selected").cmd = "FREEZE"
    g.operator("max.object_cmd", text="Unfreeze All").cmd = "UNFREEZE"


@rollout("Display Properties", {"DISPLAY"}, 32)
@when(lambda c: c.active_object is not None)
def disp_props(layout, context):
    ob = context.active_object
    col = layout.column(align=True)
    col.prop(ob, "display_type", text="")
    col.prop(ob, "show_in_front", text="See-Through")
    col.prop(ob, "show_wire", text="Edges Only")
    col.prop(ob, "show_name", text="Display Name")
    col.prop(ob, "show_axis", text="Show Pivot")
    col.prop(ob, "show_bounds", text="Display as Box Outline")
    if context.space_data and context.space_data.type == "VIEW_3D":
        col.prop(context.space_data.shading, "show_backface_culling", text="Backface Cull")


# ----- Utilities ---------------------------------------------------------------

@rollout("Utilities", {"UTILITIES"}, 40)
def util_main(layout, context):
    g = _grid(layout)
    g.operator("max.object_cmd", text="Reset XForm").cmd = "RESET_XFORM"
    g.operator("max.object_cmd", text="Collapse").cmd = "CONVERT_POLY"
    ob = context.active_object
    if ob:
        layout.label(text="Measure:")
        _split_col(layout).prop(ob, "dimensions", text="Dimensions")


@rollout("NotuoDesk 3ds Maxxed", {"UTILITIES"}, 41)
def util_maxxed(layout, context):
    col = layout.column(align=True)
    col.operator("max.apply", text="Apply 3ds Max Look", icon="CHECKMARK")
    col.operator("max.apply", text="Theme Only", icon="COLOR").layout_ = False
    col.operator("max.restore", text="Restore Blender Look", icon="LOOP_BACK")
    layout.operator("max.toggle_quad", text="Maximize Viewport Toggle (Alt+W)")
    layout.operator("preferences.addon_show", text="Hotkeys & Settings").module = __package__
    from . import updater
    updater.draw_update_box(layout)


classes = (MAX_UL_stack, MAX_MT_create_subcat, MAX_PT_command_panel)


def register_props():
    bpy.types.Object.max_stack_index = IntProperty(
        get=_stack_get, set=_stack_set, options={"SKIP_SAVE"})


def unregister_props():
    del bpy.types.Object.max_stack_index
