"""General 3ds Max style operators."""

import math

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, StringProperty
from bpy.types import Operator
from mathutils import Euler, Quaternion

from . import theme


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def max_name(base):
    """3ds Max style unique names: Box001, Box002 ..."""
    i = 1
    while f"{base}{i:03d}" in bpy.data.objects:
        i += 1
    return f"{base}{i:03d}"


def find_view3d(context):
    """Return (area, window-region) of the viewport, preferring the current one."""
    area = context.area if context.area and context.area.type == "VIEW_3D" else None
    if area is None:
        screen = context.window.screen if context.window else None
        areas = [a for a in screen.areas if a.type == "VIEW_3D"] if screen else []
        area = max(areas, key=lambda a: a.width * a.height) if areas else None
    if area is None:
        return None, None
    region = None
    if context.region and context.region.type == "WINDOW" and context.area == area:
        region = context.region
    else:
        wins = [r for r in area.regions if r.type == "WINDOW"]
        region = wins[-1] if wins else None   # last = the free (perspective) quad
    return area, region


def viewport_override(context):
    """Context override pointing at a 3D viewport, for commands run from menus,
    the status bar or other editors (Dope Sheet, Graph Editor, ...)."""
    area, region = find_view3d(context)
    if area is None:
        return None
    return dict(window=context.window, area=area, region=region)


def has_view3d(context):
    return find_view3d(context)[0] is not None


def mesh_select_mode(context):
    m = context.tool_settings.mesh_select_mode
    return "VERT" if m[0] else "EDGE" if m[1] else "FACE"


# ---------------------------------------------------------------------------
# sub-object levels (1-5)
# ---------------------------------------------------------------------------

LEVEL_NAMES = {0: "Object", 1: "Vertex", 2: "Edge", 3: "Border", 4: "Polygon", 5: "Element"}
_MESH_MODE = {1: "VERT", 2: "EDGE", 3: "EDGE", 4: "FACE", 5: "FACE"}


def current_level(context):
    wm = context.window_manager
    if context.mode != "EDIT_MESH":
        return 0 if context.mode == "OBJECT" else wm.max_sublevel
    mode = mesh_select_mode(context)
    if wm.max_sublevel in _MESH_MODE and _MESH_MODE[wm.max_sublevel] == mode:
        return wm.max_sublevel
    return {"VERT": 1, "EDGE": 2, "FACE": 4}[mode]


class MAX_OT_subobject(Operator):
    """Sub-object level (1 Vertex, 2 Edge, 3 Border, 4 Polygon, 5 Element). Press again to exit"""
    bl_idname = "max.subobject"
    bl_label = "Sub-Object Level"
    bl_options = {"REGISTER", "UNDO"}

    level: IntProperty(min=0, max=5)

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        obj = context.active_object
        wm = context.window_manager
        lvl = self.level

        if obj.type == "MESH":
            if lvl == 0 or (context.mode == "EDIT_MESH" and current_level(context) == lvl):
                bpy.ops.object.mode_set(mode="OBJECT")
                wm.max_sublevel = 0
                return {"FINISHED"}
            if context.mode != "EDIT_MESH":
                if obj.max_prim.kind:     # editing a primitive turns it into an Editable Poly
                    obj.max_prim.kind = ""
                for m in obj.modifiers:   # sub-object editing happens at the base of the stack
                    try:
                        m.is_active = False
                    except Exception:
                        pass
                bpy.ops.object.mode_set(mode="EDIT")
            bpy.ops.mesh.select_mode(type=_MESH_MODE[lvl], use_extend=False, use_expand=False)
            wm.max_sublevel = lvl
            if lvl == 3:
                self.report({"INFO"}, "Border: click an open edge, then Alt+L / 'Loop' selects the whole border")
            elif lvl == 5:
                bpy.ops.mesh.select_linked()
            return {"FINISHED"}

        if obj.type in {"CURVE", "SURFACE", "LATTICE", "ARMATURE", "FONT", "META"}:
            in_edit = context.mode.startswith("EDIT")
            if lvl == 0 or (in_edit and wm.max_sublevel == lvl):
                bpy.ops.object.mode_set(mode="OBJECT")
                wm.max_sublevel = 0
            else:
                if not in_edit:
                    bpy.ops.object.mode_set(mode="EDIT")
                wm.max_sublevel = lvl
            return {"FINISHED"}
        return {"CANCELLED"}


# ---------------------------------------------------------------------------
# viewport navigation
# ---------------------------------------------------------------------------

VIEW_ROTATIONS = {
    "TOP": Quaternion((1, 0, 0, 0)),
    "FRONT": Euler((math.pi / 2, 0, 0)).to_quaternion(),
    "LEFT": Euler((math.pi / 2, 0, -math.pi / 2)).to_quaternion(),
}


class MAX_OT_set_view(Operator):
    """Switch view (T Top, B Bottom, F Front, K Back, L Left, P Perspective, U Orthographic, C Camera)"""
    bl_idname = "max.set_view"
    bl_label = "Set View"

    view: EnumProperty(items=[(v, v.title(), "") for v in (
        "TOP", "BOTTOM", "FRONT", "BACK", "LEFT", "RIGHT", "PERSP", "ORTHO", "CAMERA")])

    @classmethod
    def poll(cls, context):
        return has_view3d(context)

    def execute(self, context):
        area, region = find_view3d(context)
        rv3d = region.data if region else None
        if rv3d is None:
            return {"CANCELLED"}
        if rv3d.lock_rotation:
            rv3d.lock_rotation = False   # unlock a quad view so it can change like in Max
        with context.temp_override(area=area, region=region):
            v = self.view
            if v in {"TOP", "BOTTOM", "FRONT", "BACK", "LEFT", "RIGHT"}:
                bpy.ops.view3d.view_axis(type=v)
            elif v == "PERSP":
                if rv3d.view_perspective != "PERSP":
                    rv3d.view_perspective = "PERSP"
            elif v == "ORTHO":
                if rv3d.view_perspective != "ORTHO":
                    rv3d.view_perspective = "ORTHO"
            elif v == "CAMERA":
                if context.scene.camera is None:
                    self.report({"WARNING"}, "No camera in scene (Ctrl+C creates one from this view)")
                    return {"CANCELLED"}
                rv3d.view_perspective = "CAMERA"
        return {"FINISHED"}


class MAX_OT_zoom_extents(Operator):
    """Zoom Extents Selected (Z). Zooms to everything when nothing is selected"""
    bl_idname = "max.zoom_extents"
    bl_label = "Zoom Extents Selected"

    @classmethod
    def poll(cls, context):
        return has_view3d(context)

    def execute(self, context):
        has_sel = bool(context.selected_objects) if context.mode == "OBJECT" else True
        with context.temp_override(**viewport_override(context)):
            try:
                if has_sel:
                    bpy.ops.view3d.view_selected(use_all_regions=False)
                else:
                    bpy.ops.view3d.view_all(center=False)
            except RuntimeError:
                try:
                    bpy.ops.view3d.view_all(center=False)
                except RuntimeError:
                    return {"CANCELLED"}
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# toggles
# ---------------------------------------------------------------------------

_prev_shading = {}


class MAX_OT_toggle(Operator):
    """3ds Max display / snap toggles"""
    bl_idname = "max.toggle"
    bl_label = "Toggle"

    what: EnumProperty(items=[(k, k.replace("_", " ").title(), "") for k in (
        "WIREFRAME", "EDGED_FACES", "SEE_THROUGH", "GRID", "GIZMO", "STATS",
        "SNAP", "ANGLE_SNAP", "PERCENT_SNAP", "AUTOKEY", "BACKFACE")])

    def execute(self, context):
        ts = context.tool_settings
        space = context.space_data if context.space_data and context.space_data.type == "VIEW_3D" else None
        if space is None:
            area, _ = find_view3d(context)
            space = area.spaces.active if area else None
        w = self.what
        if w == "SNAP":
            ts.use_snap = not ts.use_snap
            self.report({"INFO"}, f"Snaps {'ON' if ts.use_snap else 'OFF'}")
        elif w == "ANGLE_SNAP":
            ts.use_snap_rotate = not ts.use_snap_rotate
            if ts.use_snap_rotate:
                ts.use_snap = True
                if "INCREMENT" not in ts.snap_elements:
                    ts.snap_elements = set(ts.snap_elements) | {"INCREMENT"}
            self.report({"INFO"}, f"Angle Snap {'ON' if ts.use_snap_rotate else 'OFF'}")
        elif w == "PERCENT_SNAP":
            ts.use_snap_scale = not ts.use_snap_scale
        elif w == "AUTOKEY":
            ts.use_keyframe_insert_auto = not ts.use_keyframe_insert_auto
            self.report({"INFO"}, f"Auto Key {'ON' if ts.use_keyframe_insert_auto else 'OFF'}")
        elif space is None:
            return {"CANCELLED"}
        elif w == "WIREFRAME":
            sh = space.shading
            key = space.as_pointer()
            if sh.type == "WIREFRAME":
                sh.type = _prev_shading.get(key, "SOLID")
            else:
                _prev_shading[key] = sh.type
                sh.type = "WIREFRAME"
        elif w == "EDGED_FACES":
            ov = space.overlay
            ov.show_wireframes = not ov.show_wireframes
            ov.wireframe_threshold = 1.0
        elif w == "SEE_THROUGH":
            sh = space.shading
            sh.show_xray = not sh.show_xray
            sh.xray_alpha = 0.5
        elif w == "GRID":
            ov = space.overlay
            on = not (ov.show_floor or ov.show_ortho_grid)
            ov.show_floor = ov.show_ortho_grid = on
        elif w == "GIZMO":
            space.show_gizmo = not space.show_gizmo
        elif w == "STATS":
            space.overlay.show_stats = not space.overlay.show_stats
        elif w == "BACKFACE":
            space.shading.show_backface_culling = not space.shading.show_backface_culling
        return {"FINISHED"}


_expert_state = {}


class MAX_OT_expert_mode(Operator):
    """Expert Mode (Ctrl+X): hide all interface around the viewport"""
    bl_idname = "max.expert_mode"
    bl_label = "Expert Mode"

    def execute(self, context):
        space = context.space_data
        if space is None or space.type != "VIEW_3D":
            area, _ = find_view3d(context)
            space = area.spaces.active if area else None
        if space is None:
            return {"CANCELLED"}
        attrs = ("show_region_header", "show_region_tool_header", "show_region_toolbar", "show_region_ui")
        key = space.as_pointer()
        if key in _expert_state:
            for a, v in zip(attrs, _expert_state.pop(key)):
                setattr(space, a, v)
        else:
            _expert_state[key] = [getattr(space, a) for a in attrs]
            for a in attrs:
                setattr(space, a, False)
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# selection / editing
# ---------------------------------------------------------------------------

class MAX_OT_select_all(Operator):
    """Select All (Ctrl+A) / None (Ctrl+D) / Invert (Ctrl+I)"""
    bl_idname = "max.select_all"
    bl_label = "Select"
    bl_options = {"REGISTER", "UNDO"}

    action: EnumProperty(items=[("SELECT", "All", ""), ("DESELECT", "None", ""), ("INVERT", "Invert", "")])

    def execute(self, context):
        m = context.mode
        if m == "OBJECT":
            bpy.ops.object.select_all(action=self.action)
        elif m == "EDIT_MESH":
            bpy.ops.mesh.select_all(action=self.action)
        elif m == "EDIT_CURVE":
            bpy.ops.curve.select_all(action=self.action)
        elif m == "EDIT_ARMATURE":
            bpy.ops.armature.select_all(action=self.action)
        elif m == "POSE":
            bpy.ops.pose.select_all(action=self.action)
        else:
            return {"PASS_THROUGH"}
        return {"FINISHED"}


class MAX_OT_delete(Operator):
    """Delete selection (no confirmation, like 3ds Max)"""
    bl_idname = "max.delete"
    bl_label = "Delete"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        m = context.mode
        if m == "OBJECT":
            bpy.ops.object.delete(use_global=False, confirm=False)
        elif m == "EDIT_MESH":
            bpy.ops.mesh.delete(type=mesh_select_mode(context))
        elif m == "EDIT_CURVE":
            bpy.ops.curve.delete(type="VERT")
        else:
            return {"PASS_THROUGH"}
        return {"FINISHED"}


def _object_items(self, context):
    icons = {"MESH": "OUTLINER_OB_MESH", "CURVE": "OUTLINER_OB_CURVE", "LIGHT": "OUTLINER_OB_LIGHT",
             "CAMERA": "OUTLINER_OB_CAMERA", "EMPTY": "OUTLINER_OB_EMPTY", "FONT": "OUTLINER_OB_FONT"}
    items = [(o.name, o.name, o.type.title(), icons.get(o.type, "OBJECT_DATA"), i)
             for i, o in enumerate(sorted(context.scene.objects, key=lambda o: o.name.lower()))]
    _object_items.cache = items  # keep strings alive for Blender
    return items


class MAX_OT_select_by_name(Operator):
    """Select From Scene (H)"""
    bl_idname = "max.select_by_name"
    bl_label = "Select From Scene"
    bl_property = "obj"
    bl_options = {"REGISTER", "UNDO"}

    obj: EnumProperty(items=_object_items)

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT"

    def invoke(self, context, event):
        context.window_manager.invoke_search_popup(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        ob = context.scene.objects.get(self.obj)
        if ob is None:
            return {"CANCELLED"}
        bpy.ops.object.select_all(action="DESELECT")
        if ob.hide_get():
            ob.hide_set(False)
        ob.select_set(True)
        context.view_layer.objects.active = ob
        return {"FINISHED"}


class MAX_OT_clone(Operator):
    """Clone Options (Ctrl+V): Copy or Instance the selection in place"""
    bl_idname = "max.clone"
    bl_label = "Clone Options"
    bl_options = {"REGISTER", "UNDO"}

    mode: EnumProperty(name="Object", items=[("COPY", "Copy", ""), ("INSTANCE", "Instance", "")])

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT" and context.selected_objects

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=220)

    def draw(self, context):
        self.layout.prop(self, "mode", expand=True)

    def execute(self, context):
        bpy.ops.object.duplicate(linked=(self.mode == "INSTANCE"))
        for ob in context.selected_objects:
            base = ob.name.split(".")[0].rstrip("0123456789") or "Object"
            ob.name = max_name(base)
        return {"FINISHED"}


EDIT_POLY_OPS = [
    ("EXTRUDE", "Extrude", ""), ("CHAMFER", "Chamfer", ""), ("CONNECT", "Connect", ""),
    ("REMOVE", "Remove", ""), ("REMOVE_WITH_VERTS", "Remove (with vertices)", ""),
    ("LOOP", "Loop", ""), ("RING", "Ring", ""), ("WELD", "Weld", ""), ("TARGET_WELD", "Target Weld", ""),
    ("BRIDGE", "Bridge", ""), ("INSET", "Inset", ""), ("OUTLINE", "Outline", ""), ("CAP", "Cap", ""),
    ("FLIP", "Flip", ""), ("DETACH", "Detach", ""), ("BREAK", "Break", ""), ("COLLAPSE", "Collapse", ""),
    ("RELAX", "Relax", ""), ("MSMOOTH", "MSmooth", ""), ("TESSELLATE", "Tessellate", ""),
    ("MAKE_PLANAR", "Make Planar", ""), ("SLICE_PLANE", "Slice Plane", ""), ("CUT", "Cut", ""),
    ("HIDE_SEL", "Hide Selected", ""), ("HIDE_UNSEL", "Hide Unselected", ""), ("UNHIDE", "Unhide All", ""),
    ("OPEN_EDGES", "Select Open Edges", ""), ("GROW", "Grow", ""), ("SHRINK", "Shrink", ""),
    ("SWIFT_LOOP", "SwiftLoop", ""), ("BEVEL", "Bevel", ""),
]


class MAX_OT_edit_poly(Operator):
    """Editable Poly command"""
    bl_idname = "max.edit_poly"
    bl_label = "Edit Poly"
    bl_options = {"REGISTER", "UNDO"}

    op: EnumProperty(items=EDIT_POLY_OPS)

    @classmethod
    def poll(cls, context):
        return context.mode == "EDIT_MESH"

    @classmethod
    def description(cls, context, props):
        return dict((k, n) for k, n, _ in EDIT_POLY_OPS).get(props.op, "Edit Poly")

    def invoke(self, context, event):
        return self.run(context, "INVOKE_DEFAULT")

    def execute(self, context):
        return self.run(context, "EXEC_DEFAULT")

    def run(self, context, how):
        o = self.op
        mode = mesh_select_mode(context)
        ops = bpy.ops.mesh
        try:
            if o == "EXTRUDE":
                if mode == "VERT":
                    bpy.ops.mesh.extrude_vertices_move(how)
                elif mode == "EDGE":
                    bpy.ops.mesh.extrude_edges_move(how)
                else:
                    bpy.ops.view3d.edit_mesh_extrude_move_normal(how)
            elif o in {"CHAMFER", "BEVEL"}:
                ops.bevel(how, affect="VERTICES" if mode == "VERT" else "EDGES")
            elif o == "CONNECT":
                if mode == "VERT":
                    ops.vert_connect_path()
                else:
                    ops.subdivide(number_cuts=1)
            elif o == "REMOVE":
                ops.dissolve_mode(use_verts=False)
            elif o == "REMOVE_WITH_VERTS":
                ops.dissolve_mode(use_verts=True)
            elif o == "LOOP":
                if hasattr(ops, "select_edge_loop_multi"):
                    ops.select_edge_loop_multi()
                else:
                    ops.loop_multi_select(ring=False)
            elif o == "RING":
                if hasattr(ops, "select_edge_ring_multi"):
                    ops.select_edge_ring_multi()
                else:
                    ops.loop_multi_select(ring=True)
            elif o == "WELD":
                ops.remove_doubles(how)
            elif o == "TARGET_WELD":
                try:
                    ops.merge(type="LAST")
                except TypeError:
                    self.report({"WARNING"}, "Target Weld: click the source vertex, then Shift+click the target")
                    return {"CANCELLED"}
            elif o == "BRIDGE":
                ops.bridge_edge_loops()
            elif o in {"INSET", "OUTLINE"}:
                ops.inset(how)
            elif o == "CAP":
                ops.fill()
            elif o == "FLIP":
                ops.flip_normals()
            elif o == "DETACH":
                ops.separate(type="SELECTED")
            elif o == "BREAK":
                ops.split()
            elif o == "COLLAPSE":
                ops.merge(type="COLLAPSE")
            elif o == "RELAX":
                ops.vertices_smooth(factor=0.5, repeat=3)
            elif o == "MSMOOTH":
                ops.subdivide(number_cuts=1, smoothness=1.0)
            elif o == "TESSELLATE":
                ops.subdivide(number_cuts=1)
            elif o == "MAKE_PLANAR":
                bpy.ops.transform.resize(value=(1, 1, 0), orient_type="NORMAL", constraint_axis=(False, False, True))
            elif o == "SLICE_PLANE":
                ops.bisect(how)
            elif o == "CUT":
                ops.knife_tool(how)
            elif o == "SWIFT_LOOP":
                ops.loopcut_slide(how)
            elif o == "HIDE_SEL":
                ops.hide(unselected=False)
            elif o == "HIDE_UNSEL":
                ops.hide(unselected=True)
            elif o == "UNHIDE":
                ops.reveal()
            elif o == "OPEN_EDGES":
                ops.select_mode(type="EDGE")
                ops.select_non_manifold(extend=False, use_wire=False, use_boundary=True,
                                        use_multi_face=False, use_non_contiguous=False, use_verts=False)
            elif o == "GROW":
                ops.select_more()
            elif o == "SHRINK":
                ops.select_less()
        except RuntimeError as exc:
            self.report({"WARNING"}, str(exc).split("Error: ")[-1].strip())
            return {"CANCELLED"}
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# object level commands
# ---------------------------------------------------------------------------

OBJECT_CMDS = [
    ("CONVERT_POLY", "Convert to Editable Poly", "Collapse the modifier stack into an editable mesh"),
    ("CONVERT_SPLINE", "Convert to Editable Spline", "Convert to a curve object"),
    ("RESET_XFORM", "Reset XForm", "Bake rotation and scale into the object (Apply Rotation & Scale)"),
    ("CENTER_PIVOT", "Center to Object", "Move the pivot to the center of the object"),
    ("PIVOT_TO_WORLD", "Pivot to World Origin", "Move the pivot to the world origin"),
    ("OBJECT_TO_PIVOT", "Center Object to Pivot", "Move the object so its center is at the pivot"),
    ("HIDE_SEL", "Hide Selection", ""), ("HIDE_UNSEL", "Hide Unselected", ""), ("UNHIDE", "Unhide All", ""),
    ("FREEZE", "Freeze Selection", "Make the selection unselectable and grey"),
    ("UNFREEZE", "Unfreeze All", ""),
    ("DISPLAY_BOX", "Display as Box", "Toggle bounding box display"),
    ("SEE_THROUGH", "See-Through", "Toggle drawing the selection in front"),
    ("EDGES_ONLY", "Show Wireframe on Object", "Toggle wireframe over shaded"),
    ("LINK", "Select and Link", "Parent selection to the active object"),
    ("UNLINK", "Unlink Selection", "Clear parent, keep transform"),
    ("ATTACH", "Attach", "Join selected objects into the active one"),
    ("MIRROR", "Mirror", "Mirror the selection"),
    ("ALIGN", "Align", "Align objects"),
    ("ISOLATE", "Isolate Selection", "Local view (Alt+Q)"),
]


class MAX_OT_object_cmd(Operator):
    """3ds Max object command"""
    bl_idname = "max.object_cmd"
    bl_label = "Object Command"
    bl_options = {"REGISTER", "UNDO"}

    cmd: EnumProperty(items=OBJECT_CMDS)

    @classmethod
    def description(cls, context, props):
        for k, n, d in OBJECT_CMDS:
            if k == props.cmd:
                return d or n
        return ""

    def invoke(self, context, event):
        return self.run(context, "INVOKE_DEFAULT")

    def execute(self, context):
        return self.run(context, "EXEC_DEFAULT")

    def run(self, context, how):
        c = self.cmd
        if context.mode != "OBJECT" and c not in {"ISOLATE", "MIRROR"}:
            bpy.ops.object.mode_set(mode="OBJECT")
            context.window_manager.max_sublevel = 0
        sel = context.selected_objects
        try:
            if c == "CONVERT_POLY":
                bpy.ops.object.convert(target="MESH")
                for ob in context.selected_objects:
                    if ob.type == "MESH":
                        ob.max_prim.kind = ""
            elif c == "CONVERT_SPLINE":
                bpy.ops.object.convert(target="CURVE")
            elif c == "RESET_XFORM":
                bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
            elif c == "CENTER_PIVOT":
                bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")
            elif c == "PIVOT_TO_WORLD":
                cursor = context.scene.cursor
                saved = cursor.location.copy()
                cursor.location = (0, 0, 0)
                bpy.ops.object.origin_set(type="ORIGIN_CURSOR")
                cursor.location = saved
            elif c == "OBJECT_TO_PIVOT":
                bpy.ops.object.origin_set(type="GEOMETRY_ORIGIN", center="BOUNDS")
            elif c == "HIDE_SEL":
                bpy.ops.object.hide_view_set(unselected=False)
            elif c == "HIDE_UNSEL":
                bpy.ops.object.hide_view_set(unselected=True)
            elif c == "UNHIDE":
                bpy.ops.object.hide_view_clear(select=False)
            elif c == "FREEZE":
                for ob in sel:
                    ob["max_frozen_color"] = list(ob.color)
                    ob.color = (0.55, 0.55, 0.55, 1.0)
                    ob.select_set(False)
                    ob.hide_select = True
            elif c == "UNFREEZE":
                for ob in context.scene.objects:
                    if ob.hide_select:
                        ob.hide_select = False
                        if "max_frozen_color" in ob:
                            ob.color = ob["max_frozen_color"]
                            del ob["max_frozen_color"]
            elif c == "DISPLAY_BOX":
                for ob in sel:
                    ob.display_type = "TEXTURED" if ob.display_type == "BOUNDS" else "BOUNDS"
            elif c == "SEE_THROUGH":
                for ob in sel:
                    ob.show_in_front = not ob.show_in_front
            elif c == "EDGES_ONLY":
                for ob in sel:
                    ob.show_wire = not ob.show_wire
            elif c == "LINK":
                bpy.ops.object.parent_set(type="OBJECT", keep_transform=True)
            elif c == "UNLINK":
                bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
            elif c == "ATTACH":
                bpy.ops.object.join()
            elif c == "MIRROR":
                bpy.ops.transform.mirror(how)
            elif c == "ALIGN":
                bpy.ops.object.align(how)
            elif c == "ISOLATE":
                area, region = find_view3d(context)
                with context.temp_override(area=area, region=region):
                    bpy.ops.view3d.localview()
        except RuntimeError as exc:
            self.report({"WARNING"}, str(exc).split("Error: ")[-1].strip())
            return {"CANCELLED"}
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# cameras / editors / dialogs
# ---------------------------------------------------------------------------

class MAX_OT_camera_from_view(Operator):
    """Create Camera From View (Ctrl+C)"""
    bl_idname = "max.camera_from_view"
    bl_label = "Create Camera From View"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        area, region = find_view3d(context)
        if region is None:
            return {"CANCELLED"}
        rv3d = region.data
        name = max_name("PhysCamera")
        cam = bpy.data.cameras.new(name)
        cam.lens = area.spaces.active.lens
        ob = bpy.data.objects.new(name, cam)
        context.collection.objects.link(ob)
        ob.matrix_world = rv3d.view_matrix.inverted()
        context.scene.camera = ob
        if context.mode == "OBJECT":
            bpy.ops.object.select_all(action="DESELECT")
            ob.select_set(True)
            context.view_layer.objects.active = ob
        rv3d.view_perspective = "CAMERA"
        return {"FINISHED"}


EDITORS = {
    "MATERIAL": ("ShaderNodeTree", None, "Slate Material Editor"),
    "RENDER_SETUP": ("PROPERTIES", "RENDER", "Render Setup"),
    "ENVIRONMENT": ("PROPERTIES", "WORLD", "Environment and Effects"),
    "CURVE_EDITOR": ("FCURVES", None, "Curve Editor"),
    "DOPE_SHEET": ("DOPESHEET", None, "Dope Sheet"),
    "SCENE_EXPLORER": ("OUTLINER", None, "Scene Explorer"),
    "SCHEMATIC": ("GeometryNodeTree", None, "Schematic View"),
    "SCRIPT_EDITOR": ("TEXT_EDITOR", None, "Script Editor"),
    "LISTENER": ("CONSOLE", None, "Python Listener"),
}


class MAX_OT_open_editor(Operator):
    """Open a floating editor window, like 3ds Max dialogs"""
    bl_idname = "max.open_editor"
    bl_label = "Open Editor"

    editor: EnumProperty(items=[(k, v[2], "") for k, v in EDITORS.items()])

    @classmethod
    def description(cls, context, props):
        return EDITORS[props.editor][2]

    def invoke(self, context, event):
        ui_type, tab, _ = EDITORS[self.editor]
        area = context.area
        if area is None or area.type in {"TOPBAR", "STATUSBAR", "EMPTY"} \
                or area not in context.window.screen.areas[:]:
            # called from the menu bar / status bar: borrow the main viewport
            area, _ = find_view3d(context)
            if area is None:
                area = max(context.window.screen.areas, key=lambda a: a.width * a.height)
        old = area.ui_type
        try:
            area.ui_type = ui_type
            if tab:
                try:
                    area.spaces.active.context = tab
                except Exception:
                    pass
            region = next((r for r in area.regions if r.type == "WINDOW"), None)
            with context.temp_override(window=context.window, area=area, region=region):
                bpy.ops.screen.area_dupli("INVOKE_DEFAULT")
        except Exception as exc:
            self.report({"WARNING"}, f"Could not open window: {exc}")
        finally:
            area.ui_type = old
        return {"FINISHED"}

    def execute(self, context):
        return {"CANCELLED"}


class MAX_OT_transform_typein(Operator):
    """Transform Type-In (F12)"""
    bl_idname = "max.transform_typein"
    bl_label = "Transform Type-In"

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def invoke(self, context, event):
        return context.window_manager.invoke_popup(self, width=320)

    def draw(self, context):
        ob = context.active_object
        lay = self.layout
        lay.label(text=f"Move / Rotate / Scale Transform Type-In:  {ob.name}")
        row = lay.row()
        row.column().prop(ob, "location", text="Absolute:World")
        row.column().prop(ob, "rotation_euler", text="Rotation")
        row.column().prop(ob, "scale", text="Scale")

    def execute(self, context):
        return {"FINISHED"}


class MAX_OT_add_modifier(Operator):
    """Add a modifier (3ds Max name)"""
    bl_idname = "max.add_modifier"
    bl_label = "Add Modifier"
    bl_options = {"REGISTER", "UNDO"}

    kind: StringProperty()     # "BLENDER_TYPE[:option]|Max Name"

    @classmethod
    def description(cls, context, props):
        try:
            spec, label = props.kind.split("|")
            return f"{label}  (Blender: {spec.split(':')[0].replace('_', ' ').title()})"
        except ValueError:
            return "Add modifier"

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        spec, label = self.kind.split("|")
        mtype, _, option = spec.partition(":")
        ob = context.active_object
        if mtype == "EDIT_POLY":
            bpy.ops.max.subobject(level=1)
            return {"FINISHED"}
        if mtype == "UNWRAP":
            ws = bpy.data.workspaces.get("UV Editing")
            if ws:
                context.window.workspace = ws
            return {"FINISHED"}
        if mtype == "EXTRUDE_SHAPE" and ob.type == "CURVE":
            ob.data.extrude = 0.25
            return {"FINISHED"}
        if mtype == "SWEEP" and ob.type == "CURVE":
            ob.data.bevel_depth = 0.05
            return {"FINISHED"}
        if mtype == "GN":
            from . import gn_mods
            if ob.type != "MESH":
                self.report({"WARNING"}, f"{label} works on mesh objects")
                return {"CANCELLED"}
            mod = gn_mods.add(ob, option, label)
            ob.modifiers.active = mod
            return {"FINISHED"}
        try:
            mod = ob.modifiers.new(label, mtype)
        except (RuntimeError, TypeError) as exc:
            self.report({"WARNING"}, f"{label} can't be applied to this object: {exc}")
            return {"CANCELLED"}
        if mod is None:
            self.report({"WARNING"}, f"{label} can't be applied to a {ob.type.lower()}")
            return {"CANCELLED"}
        if mtype == "SIMPLE_DEFORM" and option:
            mod.deform_method = option
            mod.deform_axis = "Z"
            if option in {"BEND", "TWIST"}:
                mod.angle = 0.7854
        elif mtype == "LATTICE" and option:
            mod.object = _make_ffd(context, ob, int(option))
        elif mtype == "DECIMATE" and option == "PLANAR":
            mod.decimate_type = "DISSOLVE"
        elif mtype == "REMESH" and option == "QUAD":
            mod.mode = "SHARP"
        elif mtype == "SHRINKWRAP" and option == "PROJECT":
            mod.wrap_method = "PROJECT"
        elif mtype == "PARTICLE_SYSTEM" and option == "HAIR":
            mod.particle_system.settings.type = "HAIR"
            mod.particle_system.settings.hair_length = 0.2
        elif mtype == "SUBSURF":
            mod.levels = mod.render_levels = 1 if option else 2
        elif mtype == "SOLIDIFY":
            mod.thickness = 0.1
        elif mtype == "SCREW":
            mod.axis = "Z"
        elif mtype == "CAST" and option == "SPHERE":
            mod.factor = 1.0
        elif mtype == "WAVE" and option == "RIPPLE":
            mod.use_normal = False
        try:
            ob.modifiers.active = mod
        except Exception:
            pass
        return {"FINISHED"}


def _make_ffd(context, ob, n):
    """Create an FFD lattice fitted to the object's bounding box."""
    from mathutils import Vector
    lat = bpy.data.lattices.new(f"FFD({n}x{n}x{n})")
    lat.points_u = lat.points_v = lat.points_w = n
    lat_ob = bpy.data.objects.new(f"{ob.name} FFD", lat)
    for coll in ob.users_collection:
        coll.objects.link(lat_ob)
    corners = [Vector(c) for c in ob.bound_box]
    lo = Vector([min(c[i] for c in corners) for i in range(3)])
    hi = Vector([max(c[i] for c in corners) for i in range(3)])
    lat_ob.parent = ob
    lat_ob.location = (lo + hi) / 2
    lat_ob.scale = [max(hi[i] - lo[i], 1e-3) for i in range(3)]
    lat_ob.color = (1.0, 0.55, 0.1, 1.0)   # Max draws FFD lattices orange
    return lat_ob


class MAX_OT_melt_preset(Operator):
    """Set Melt solidity to a 3ds Max preset"""
    bl_idname = "max.melt_preset"
    bl_label = "Solidity Preset"
    bl_options = {"REGISTER", "UNDO"}

    value: bpy.props.FloatProperty()

    def execute(self, context):
        from . import gn_mods
        ob = context.active_object
        mod = ob.modifiers.active if ob else None
        if mod is None or mod.type != "NODES":
            return {"CANCELLED"}
        gn_mods.set_input(mod, "Solidity", self.value)
        ob.update_tag()
        return {"FINISHED"}


def _melt_mod(ob):
    from . import gn_mods
    if ob is None:
        return None
    act = ob.modifiers.active
    if gn_mods.is_melt(act):
        return act
    return next((m for m in ob.modifiers if gn_mods.is_melt(m)), None)


class MAX_OT_animate_melt(Operator):
    """Animate the melt: keyframe Amount from solid to melted over a frame range"""
    bl_idname = "max.animate_melt"
    bl_label = "Animate Melt"
    bl_options = {"REGISTER", "UNDO"}

    start: bpy.props.IntProperty(name="Start Frame", default=1)
    end: bpy.props.IntProperty(name="End Frame", default=100)
    amount_from: FloatProperty(name="From Amount", default=0.0, min=0.0, max=1.0, subtype="FACTOR")
    amount_to: FloatProperty(name="To Amount", default=1.0, min=0.0, max=1.0, subtype="FACTOR")
    play: BoolProperty(name="Play Animation", default=True)

    @classmethod
    def poll(cls, context):
        ob = context.active_object
        return ob is not None and ob.type == "MESH"

    def invoke(self, context, event):
        self.start = context.scene.frame_current
        self.end = self.start + 99
        return context.window_manager.invoke_props_dialog(self, width=260)

    def execute(self, context):
        from . import gn_mods
        ob = context.active_object
        mod = _melt_mod(ob)
        if mod is None:
            mod = gn_mods.add(ob, "MELT", "Melt")
        ob.modifiers.active = mod
        if self.end <= self.start:
            self.end = self.start + 1
        for frame, value in ((self.start, self.amount_from), (self.end, self.amount_to)):
            gn_mods.set_input(mod, "Amount", value)
            gn_mods.keyframe_input(mod, "Amount", frame)
        scene = context.scene
        scene.frame_end = max(scene.frame_end, self.end)
        scene.frame_set(self.start)
        if self.play and not context.screen.is_animation_playing:
            try:
                bpy.ops.screen.animation_play()
            except RuntimeError:
                pass
        self.report({"INFO"}, f"Melt animated: frame {self.start} to {self.end}")
        return {"FINISHED"}


class MAX_OT_key_melt(Operator):
    """Set a key on the Melt Amount at the current frame"""
    bl_idname = "max.key_melt"
    bl_label = "Key Melt Amount"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        from . import gn_mods
        mod = _melt_mod(context.active_object)
        if mod is None:
            return {"CANCELLED"}
        gn_mods.keyframe_input(mod, "Amount", context.scene.frame_current)
        return {"FINISHED"}


class MAX_OT_modifier_set_active(Operator):
    """Select this modifier in the stack"""
    bl_idname = "max.modifier_set_active"
    bl_label = "Select Modifier"

    name: StringProperty()

    def execute(self, context):
        ob = context.active_object
        mod = ob.modifiers.get(self.name) if ob else None
        if mod is None:
            if ob:  # clicked the base object: deselect modifiers
                for m in ob.modifiers:
                    try:
                        m.is_active = False
                    except Exception:
                        pass
            return {"FINISHED"}
        ob.modifiers.active = mod
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# global apply / restore
# ---------------------------------------------------------------------------

def quadview_op():
    """screen.region_quadviews was renamed to screen.region_quadview in Blender 5."""
    if "region_quadview" in dir(bpy.ops.screen):
        return bpy.ops.screen.region_quadview
    return bpy.ops.screen.region_quadviews


class MAX_OT_toggle_quad(Operator):
    """Maximize Viewport Toggle (Alt+W): switch between quad views and one big viewport"""
    bl_idname = "max.toggle_quad"
    bl_label = "Maximize Viewport Toggle"

    @classmethod
    def poll(cls, context):
        return find_view3d(context)[0] is not None

    def execute(self, context):
        area, region = find_view3d(context)
        with context.temp_override(area=area, region=region):
            quadview_op()()
        return {"FINISHED"}


def unlock_region(region):
    """3ds Max lets you orbit any viewport; Blender locks 3 of its 4 quad views."""
    rv3d = region.data
    if rv3d is not None and getattr(rv3d, "lock_rotation", False):
        rv3d.lock_rotation = False


def unlock_max_workspace_quads():
    """Fix layouts saved by older versions (orbit didn't work in 3 of 4 viewports)."""
    ws = bpy.data.workspaces.get(WS_NAME)
    if ws is None:
        return
    for screen in ws.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                for region in area.regions:
                    if region.type == "WINDOW":
                        unlock_region(region)


def _assign_quad_views(area):
    wins = [r for r in area.regions if r.type == "WINDOW"]
    if len(wins) < 4:
        return
    # order: top-left, top-right, bottom-left, bottom-right
    wins.sort(key=lambda r: (-r.y, r.x))
    for region in wins:
        unlock_region(region)
    for region, name in zip(wins[:3], ("TOP", "FRONT", "LEFT")):
        rv3d = region.data
        try:
            rv3d.view_rotation = VIEW_ROTATIONS[name]
            rv3d.view_perspective = "ORTHO"
        except Exception as exc:
            print(f"[3ds Maxxed] quad {name}: {exc}")
    persp = wins[3].data
    persp.view_perspective = "PERSP"
    persp.view_rotation = Euler((math.radians(65), 0, math.radians(-45))).to_quaternion()
    area.tag_redraw()


def setup_quad_views(context, window, area):
    """Enable quad view with the 3ds Max layout: Top | Front / Left | Perspective."""
    space = area.spaces.active
    wins = [r for r in area.regions if r.type == "WINDOW"]
    if len(space.region_quadviews) == 0 and wins:
        with context.temp_override(window=window, area=area, region=wins[-1]):
            quadview_op()()
    # Region positions are only valid after Blender lays the quads out, so assign
    # the views a moment later.
    def later():
        try:
            _assign_quad_views(area)
        except ReferenceError:
            pass
        return None
    bpy.app.timers.register(later, first_interval=0.15)


WS_NAME = "3ds Max"


def _configure_viewport(context, window, area, quad=True):
    space = area.spaces.active
    space.show_region_ui = True
    space.show_region_tool_header = False
    space.show_region_toolbar = False
    space.show_region_header = True           # drawn as the 3ds Max Main Toolbar
    sh = space.shading
    if sh.type == "SOLID":
        sh.color_type = "OBJECT"
        sh.light = "STUDIO"
    sh.wireframe_color_type = "OBJECT"
    space.overlay.show_text = False           # only our [+] [Perspective] labels
    space.overlay.show_wireframes = False
    for r in area.regions:
        if r.type == "UI":
            try:
                r.active_panel_category = "Command Panel"
            except Exception:
                pass
    if quad:
        setup_quad_views(context, window, area)
    try:
        with context.temp_override(window=window, area=area):
            bpy.ops.wm.tool_set_by_id(name="builtin.select_box")
    except Exception:
        pass


def _build_screen(window):
    """Turn the duplicated Layout into: Scene Explorer | quad viewports | Command Panel."""
    context = bpy.context
    screen = window.screen
    views = [a for a in screen.areas if a.type == "VIEW_3D"]
    if not views:
        return
    view = max(views, key=lambda a: a.width * a.height)
    # 1. close the Outliner / Properties column right of the viewport
    for area in list(screen.areas):
        if area.type in {"OUTLINER", "PROPERTIES"} and area.x >= view.x + view.width - 4:
            try:
                with context.temp_override(window=window, screen=screen, area=area):
                    bpy.ops.screen.area_close()
            except Exception as exc:
                print(f"[3ds Maxxed] close area: {exc}")

    def split_later():
        try:
            views = [a for a in screen.areas if a.type == "VIEW_3D"]
            view = max(views, key=lambda a: a.width * a.height)
            if not any(a.type == "OUTLINER" and a.x < view.x for a in screen.areas):
                region = [r for r in view.regions if r.type == "WINDOW"][-1]
                with context.temp_override(window=window, screen=screen, area=view, region=region):
                    bpy.ops.screen.area_split(direction="VERTICAL", factor=0.14)
                views = sorted([a for a in screen.areas if a.type == "VIEW_3D"], key=lambda a: a.width)
                if len(views) >= 2:
                    explorer = views[0]
                    explorer.ui_type = "OUTLINER"
                    view = views[-1]
            _configure_viewport(context, window, view)
        except Exception as exc:
            print(f"[3ds Maxxed] layout: {exc}")
        return None
    bpy.app.timers.register(split_later, first_interval=0.1)


def apply_layout(context, quad=True):
    wm = context.window_manager
    window = context.window or (wm.windows[0] if wm.windows else None)
    if window is None:
        return
    ws = bpy.data.workspaces.get(WS_NAME)
    if ws is not None:
        window.workspace = ws
        def activate():
            views = [a for a in window.screen.areas if a.type == "VIEW_3D"]
            if views:
                _configure_viewport(bpy.context, window, max(views, key=lambda a: a.width * a.height), quad)
            return None
        bpy.app.timers.register(activate, first_interval=0.1)
        return
    base = bpy.data.workspaces.get("Layout") or window.workspace
    before = set(bpy.data.workspaces.keys())
    with context.temp_override(window=window, workspace=base):
        bpy.ops.workspace.duplicate()
    new = [w for w in bpy.data.workspaces if w.name not in before]
    if not new:
        return
    new[0].name = WS_NAME
    window.workspace = new[0]

    def wait():
        if window.workspace.name != WS_NAME:
            return 0.05
        _build_screen(window)
        return None
    bpy.app.timers.register(wait, first_interval=0.05)


def restore_layout(context):
    for window in context.window_manager.windows:
        if window.workspace.name == WS_NAME:
            layout = bpy.data.workspaces.get("Layout")
            if layout:
                window.workspace = layout


class MAX_OT_adaptive_degradation(Operator):
    """Adaptive Degradation (O): lighter viewport for heavy scenes (Blender Simplify)"""
    bl_idname = "max.adaptive_degradation"
    bl_label = "Adaptive Degradation"

    def execute(self, context):
        r = context.scene.render
        r.use_simplify = not r.use_simplify
        if r.use_simplify:
            r.simplify_subdivision = min(r.simplify_subdivision, 1)
            r.simplify_child_particles = min(r.simplify_child_particles, 0.2)
            r.simplify_volumes = min(r.simplify_volumes, 0.5)
        self.report({"INFO"}, f"Adaptive Degradation {'ON' if r.use_simplify else 'OFF'}")
        return {"FINISHED"}


class MAX_OT_set_key(Operator):
    """Set Key (K): key the selection's transforms (works from any menu or editor)"""
    bl_idname = "max.set_key"
    bl_label = "Set Key"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return bool(context.selected_objects) or context.active_object is not None

    def execute(self, context):
        ov = viewport_override(context)
        try:
            if ov:
                with context.temp_override(**ov):
                    bpy.ops.anim.keyframe_insert()
            else:
                raise RuntimeError
        except RuntimeError:
            frame = context.scene.frame_current
            for ob in context.selected_objects or [context.active_object]:
                for path in ("location", "rotation_euler", "scale"):
                    ob.keyframe_insert(path, frame=frame)
        self.report({"INFO"}, f"Key set at frame {context.scene.frame_current}")
        return {"FINISHED"}


class MAX_OT_group(Operator):
    """Group: parent the selection under a new Dummy (Ungroup removes it)"""
    bl_idname = "max.group"
    bl_label = "Group"
    bl_options = {"REGISTER", "UNDO"}

    action: EnumProperty(items=[("GROUP", "Group", ""), ("UNGROUP", "Ungroup", "")])

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT" and context.selected_objects

    def execute(self, context):
        sel = list(context.selected_objects)
        if self.action == "GROUP":
            from mathutils import Vector
            center = sum((o.matrix_world.translation for o in sel), Vector()) / len(sel)
            grp = bpy.data.objects.new(max_name("Group"), None)
            grp.empty_display_type = "CUBE"
            grp.location = center
            context.collection.objects.link(grp)
            context.view_layer.update()
            for o in sel:
                mw = o.matrix_world.copy()
                o.parent = grp
                o.matrix_world = mw
            for o in sel:
                o.select_set(False)
            grp.select_set(True)
            context.view_layer.objects.active = grp
        else:
            for grp in [o for o in sel if o.type == "EMPTY" and o.name.startswith("Group")]:
                for child in list(grp.children):
                    mw = child.matrix_world.copy()
                    child.parent = None
                    child.matrix_world = mw
                    child.select_set(True)
                bpy.data.objects.remove(grp)
        return {"FINISHED"}


class MAX_OT_set_workspace(Operator):
    """Switch workspace"""
    bl_idname = "max.set_workspace"
    bl_label = "Workspace"

    name: StringProperty()

    def execute(self, context):
        ws = bpy.data.workspaces.get(self.name)
        if ws:
            context.window.workspace = ws
        return {"FINISHED"}


class MAX_OT_apply(Operator):
    """Turn Blender into 3ds Max: theme, navigation and a '3ds Max' workspace with quad viewports"""
    bl_idname = "max.apply"
    bl_label = "Apply 3ds Max Look"

    theme: BoolProperty(default=True)
    layout_: BoolProperty(name="Layout", default=True)
    quad: BoolProperty(default=True)

    def execute(self, context):
        if self.theme:
            theme.apply_theme()
        theme.apply_prefs()
        if self.layout_:
            apply_layout(context, quad=self.quad)
        self.report({"INFO"}, "3ds Max mode applied")
        return {"FINISHED"}


class MAX_OT_restore(Operator):
    """Restore Blender's default theme, preferences and layout"""
    bl_idname = "max.restore"
    bl_label = "Restore Blender Look"

    def execute(self, context):
        theme.reset_theme()
        theme.restore_prefs()
        restore_layout(context)
        self.report({"INFO"}, "Blender look restored")
        return {"FINISHED"}


classes = (
    MAX_OT_subobject, MAX_OT_set_view, MAX_OT_zoom_extents, MAX_OT_toggle, MAX_OT_expert_mode,
    MAX_OT_select_all, MAX_OT_delete, MAX_OT_select_by_name, MAX_OT_clone, MAX_OT_edit_poly,
    MAX_OT_object_cmd, MAX_OT_camera_from_view, MAX_OT_open_editor, MAX_OT_transform_typein,
    MAX_OT_add_modifier, MAX_OT_modifier_set_active, MAX_OT_apply, MAX_OT_restore, MAX_OT_toggle_quad, MAX_OT_set_workspace, MAX_OT_group, MAX_OT_melt_preset, MAX_OT_set_key, MAX_OT_animate_melt, MAX_OT_key_melt, MAX_OT_adaptive_degradation,
)
