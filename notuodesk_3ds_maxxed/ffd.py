"""3ds Max FFD (Free-Form Deformation): a Lattice modifier + lattice cage, presented with
FFD's parameters.

Sub-object       Control Points (edit the cage points) / Lattice (move the cage) / back
Dimensions       Set Number of Points (U x V x W)
Display          Lattice, In Front
Deform           Only In Volume / All Vertices + Falloff (driven by a vertex group,
                 because Blender's lattice otherwise deforms everything)
Interpolation    Linear / Cardinal / Catmull-Rom / B-Spline (Max: Tension/Continuity)
Control Points   Reset, Animate All, Conform to Shape (Inside / Outside Points, Offset)
"""

import bpy
import numpy as np
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty
from bpy.types import Operator, PropertyGroup
from mathutils import Vector
from mathutils.bvhtree import BVHTree

OWNER_KEY = "max_ffd_owner"


def is_ffd(mod):
    return (mod is not None and mod.type == "LATTICE" and mod.object is not None
            and mod.object.type == "LATTICE")


def ffd_modifier(ob):
    if ob is None:
        return None
    act = ob.modifiers.active
    if is_ffd(act):
        return act
    return next((m for m in ob.modifiers if is_ffd(m)), None)


def ffd_context(context):
    """(deformed object, FFD modifier, lattice object) from either the object or its cage."""
    ob = context.active_object
    if ob is None:
        return None, None, None
    if ob.type == "LATTICE" and ob.get(OWNER_KEY) in bpy.data.objects:
        owner = bpy.data.objects[ob[OWNER_KEY]]
        mod = next((m for m in owner.modifiers if m.type == "LATTICE" and m.object == ob), None)
        return owner, mod, ob
    mod = ffd_modifier(ob)
    return (ob, mod, mod.object) if mod else (ob, None, None)


# ---------------------------------------------------------------------------
# Deform volume (Only In Volume / All Vertices + Falloff)
# ---------------------------------------------------------------------------

def volume_group_name(mod):
    return f"FFD Volume ({mod.name})"


def apply_volume(ob, mod):
    if ob.type != "MESH" or ob.mode == "EDIT" or not is_ffd(mod):
        return
    s = ob.max_ffd
    name = volume_group_name(mod)
    if s.deform_mode == "ALL" and s.falloff <= 0.0:
        mod.vertex_group = ""                       # every vertex fully deformed
        return
    lat = mod.object
    me = ob.data
    n = len(me.vertices)
    co = np.empty(n * 3, np.float32)
    me.vertices.foreach_get("co", co)
    co = np.c_[co.reshape(n, 3), np.ones(n, np.float32)]
    to_lat = np.array(lat.matrix_world.inverted() @ ob.matrix_world, np.float32)
    local = (co @ to_lat.T)[:, :3]
    out = np.maximum(np.abs(local) - 0.5, 0.0)               # outside amount per axis (cage units)
    out *= np.array(lat.matrix_world.to_scale(), np.float32)  # -> world units
    dist = np.sqrt((out * out).sum(axis=1))
    if s.deform_mode == "VOLUME":
        w = (dist <= 1e-6).astype(np.float32)
    else:
        w = np.clip(1.0 - dist / max(s.falloff, 1e-6), 0.0, 1.0)
    vg = ob.vertex_groups.get(name) or ob.vertex_groups.new(name=name)
    zero = np.nonzero(w <= 0.0)[0]
    if len(zero):
        vg.remove(zero.tolist())
    q = np.round(w * 100).astype(np.int32)                    # batch by weight (fast)
    for level in np.unique(q[q > 0]):
        idx = np.nonzero(q == level)[0]
        vg.add(idx.tolist(), level / 100.0, "REPLACE")
    mod.vertex_group = name


# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------

def _lat(self):
    mod = ffd_modifier(self.id_data)
    return mod.object.data if mod else None


def _pts_get(axis):
    def get(self):
        lat = _lat(self)
        return getattr(lat, f"points_{axis}") if lat else 4
    return get


def _pts_set(axis):
    def set_(self, v):
        lat = _lat(self)
        if lat is not None:
            setattr(lat, f"points_{axis}", v)
    return set_


INTERP = [("KEY_BSPLINE", "B-Spline (smooth)", "Smoothest; points pull gently, like Max's default"),
          ("KEY_CATMULL_ROM", "Catmull-Rom", "Passes through the points"),
          ("KEY_CARDINAL", "Cardinal", "Tighter than Catmull-Rom"),
          ("KEY_LINEAR", "Linear", "Straight, sharp influence")]
INTERP_IDS = [i[0] for i in INTERP]


def _interp_get(self):
    lat = _lat(self)
    return INTERP_IDS.index(lat.interpolation_type_u) if lat else 0


def _interp_set(self, v):
    lat = _lat(self)
    if lat is not None:
        lat.interpolation_type_u = lat.interpolation_type_v = lat.interpolation_type_w = INTERP_IDS[v]


def _cage(self):
    mod = ffd_modifier(self.id_data)
    return mod.object if mod else None


def _show_get(self):
    c = _cage(self)
    return bool(c and not c.hide_get())


def _show_set(self, v):
    c = _cage(self)
    if c is not None:
        c.hide_set(not v)


def _front_get(self):
    c = _cage(self)
    return bool(c and c.show_in_front)


def _front_set(self, v):
    c = _cage(self)
    if c is not None:
        c.show_in_front = v


def _volume_update(self, context):
    ob = self.id_data
    apply_volume(ob, ffd_modifier(ob))


class MaxFFD(PropertyGroup):
    points_u: IntProperty(name="Length", min=2, max=64, get=_pts_get("u"), set=_pts_set("u"),
                          description="Control points along X (changing it resets the cage)")
    points_v: IntProperty(name="Width", min=2, max=64, get=_pts_get("v"), set=_pts_set("v"),
                          description="Control points along Y (changing it resets the cage)")
    points_w: IntProperty(name="Height", min=2, max=64, get=_pts_get("w"), set=_pts_set("w"),
                          description="Control points along Z (changing it resets the cage)")
    interpolation: EnumProperty(name="Interpolation", items=INTERP, get=_interp_get, set=_interp_set)
    show_lattice: BoolProperty(name="Lattice", get=_show_get, set=_show_set, description="Show the cage")
    in_front: BoolProperty(name="In Front", get=_front_get, set=_front_set,
                           description="Draw the cage on top of the model")
    deform_mode: EnumProperty(name="Deform", items=[
        ("VOLUME", "Only In Volume", "Only vertices inside the cage are deformed"),
        ("ALL", "All Vertices", "Every vertex is deformed; use Falloff to fade it outside the cage")],
        default="ALL", update=_volume_update)
    falloff: FloatProperty(name="Falloff", default=0.0, min=0.0, unit="LENGTH", update=_volume_update,
                           description="All Vertices: distance outside the cage over which the effect fades "
                                       "(0 = no fade)")
    conform_inside: BoolProperty(name="Inside Points", default=True)
    conform_outside: BoolProperty(name="Outside Points", default=True)
    offset: FloatProperty(name="Offset", default=0.05, unit="LENGTH",
                          description="Conform to Shape: distance kept from the surface")


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------

def _object_mode(context):
    if context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")


def _select_only(context, ob):
    for o in context.view_layer.objects:
        o.select_set(False)
    ob.hide_set(False)
    ob.select_set(True)
    context.view_layer.objects.active = ob


class MAX_OT_ffd_level(Operator):
    """FFD sub-object level"""
    bl_idname = "max.ffd_level"
    bl_label = "FFD Sub-Object"
    bl_options = {"REGISTER", "UNDO"}

    level: EnumProperty(items=[
        ("POINTS", "Control Points", "Edit the cage's control points (deforms the model)"),
        ("LATTICE", "Lattice", "Move, rotate or scale the cage"),
        ("OBJECT", "Back to Object", "Return to the deformed object")])

    @classmethod
    def description(cls, context, props):
        return {"POINTS": "Control Points: edit the cage's points to deform the model",
                "LATTICE": "Lattice: move, rotate or scale the whole cage",
                "OBJECT": "Back to the deformed object"}[props.level]

    def execute(self, context):
        owner, mod, lat = ffd_context(context)
        if lat is None:
            self.report({"WARNING"}, "No FFD on the selected object")
            return {"CANCELLED"}
        _object_mode(context)
        if self.level == "OBJECT":
            _select_only(context, owner)
            owner.modifiers.active = mod
            return {"FINISHED"}
        lat[OWNER_KEY] = owner.name
        _select_only(context, lat)
        if self.level == "POINTS":
            bpy.ops.object.mode_set(mode="EDIT")
            bpy.ops.lattice.select_all(action="DESELECT")
            try:
                bpy.ops.wm.tool_set_by_id(name="builtin.move")
            except Exception:
                pass
        return {"FINISHED"}


class MAX_OT_ffd_reset(Operator):
    """Reset: put every control point back to its original position"""
    bl_idname = "max.ffd_reset"
    bl_label = "Reset"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        owner, mod, lat = ffd_context(context)
        if lat is None:
            return {"CANCELLED"}
        was_edit = context.mode == "EDIT_LATTICE"
        _object_mode(context)
        for p in lat.data.points:
            p.co_deform = p.co
        if was_edit:
            bpy.ops.object.mode_set(mode="EDIT")
        return {"FINISHED"}


class MAX_OT_ffd_animate_all(Operator):
    """Animate All: set a key on every control point at the current frame"""
    bl_idname = "max.ffd_animate_all"
    bl_label = "Animate All"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        owner, mod, lat = ffd_context(context)
        if lat is None:
            return {"CANCELLED"}
        was_edit = context.mode == "EDIT_LATTICE"
        _object_mode(context)
        frame = context.scene.frame_current
        for i, _p in enumerate(lat.data.points):
            lat.data.keyframe_insert(f"points[{i}].co_deform", frame=frame)
        if was_edit:
            bpy.ops.object.mode_set(mode="EDIT")
        self.report({"INFO"}, f"Keyed {len(lat.data.points)} control points at frame {frame}")
        return {"FINISHED"}


class MAX_OT_ffd_conform(Operator):
    """Conform to Shape: pull the control points onto the object's surface"""
    bl_idname = "max.ffd_conform"
    bl_label = "Conform to Shape"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        owner, mod, lat = ffd_context(context)
        if lat is None or owner.type != "MESH":
            return {"CANCELLED"}
        was_edit = context.mode == "EDIT_LATTICE"
        _object_mode(context)
        s = owner.max_ffd
        me = owner.data
        bvh = BVHTree.FromPolygons([v.co for v in me.vertices], [p.vertices for p in me.polygons])
        ow, ow_inv = owner.matrix_world, owner.matrix_world.inverted()
        lw, lw_inv = lat.matrix_world, lat.matrix_world.inverted()
        center_w = lw.translation
        pu, pv, pw = lat.data.points_u, lat.data.points_v, lat.data.points_w
        moved = 0
        for i, p in enumerate(lat.data.points):
            iu, iv, iw = i % pu, (i // pu) % pv, i // (pu * pv)
            outer = iu in (0, pu - 1) or iv in (0, pv - 1) or iw in (0, pw - 1)
            if (outer and not s.conform_outside) or (not outer and not s.conform_inside):
                continue
            pos_w = lw @ Vector(p.co)
            d_w = pos_w - center_w
            if d_w.length < 1e-6:
                continue
            d_w.normalize()
            o_l = ow_inv @ center_w
            d_l = (ow_inv.to_3x3() @ d_w).normalized()
            hit, _n, _idx, _dist = bvh.ray_cast(o_l, d_l)
            if hit is None:
                continue
            target_w = (ow @ hit) + d_w * s.offset
            p.co_deform = lw_inv @ target_w
            moved += 1
        if was_edit:
            bpy.ops.object.mode_set(mode="EDIT")
        self.report({"INFO"}, f"Conformed {moved} control points")
        return {"FINISHED"}


class MAX_OT_ffd_fit(Operator):
    """Fit the cage to the object's current size (keeps point edits)"""
    bl_idname = "max.ffd_fit"
    bl_label = "Fit to Object"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        owner, mod, lat = ffd_context(context)
        if lat is None or owner.type != "MESH" or not owner.data.vertices:
            return {"CANCELLED"}
        _object_mode(context)
        n = len(owner.data.vertices)
        co = np.empty(n * 3, np.float32)
        owner.data.vertices.foreach_get("co", co)
        co = co.reshape(n, 3)
        lo, hi = co.min(axis=0), co.max(axis=0)
        world = lat.matrix_world.copy()
        lat.parent = owner
        lat.matrix_parent_inverse.identity()
        lat.location = Vector(((lo + hi) / 2).tolist())
        lat.rotation_euler = (0, 0, 0)
        lat.scale = [max(float(x), 1e-3) for x in (hi - lo)]
        apply_volume(owner, mod)
        return {"FINISHED"}


class MAX_OT_ffd_update_volume(Operator):
    """Recompute which vertices the FFD affects (after moving or scaling the cage)"""
    bl_idname = "max.ffd_update_volume"
    bl_label = "Update Volume"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        owner, mod, lat = ffd_context(context)
        if mod is None:
            return {"CANCELLED"}
        _object_mode(context)
        apply_volume(owner, mod)
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

def draw(layout, ob, mod, editing_cage=False):
    s = ob.max_ffd
    lat = mod.object
    level = "POINTS" if editing_cage and bpy.context.mode == "EDIT_LATTICE" else (
        "LATTICE" if editing_cage else "OBJECT")

    def box(title):
        b = layout.box()
        b.label(text=title)
        return b.column(align=True)

    col = box("Sub-Object")
    row = col.row(align=True)
    row.operator("max.ffd_level", text="Control Points", depress=(level == "POINTS")).level = "POINTS"
    row.operator("max.ffd_level", text="Lattice", depress=(level == "LATTICE")).level = "LATTICE"
    if editing_cage:
        col.operator("max.ffd_level", text=f"Back to {ob.name}", icon="BACK").level = "OBJECT"

    col = box(f"Dimensions: {lat.data.points_u}x{lat.data.points_v}x{lat.data.points_w}")
    row = col.row(align=True)
    row.prop(s, "points_u", text="L")
    row.prop(s, "points_v", text="W")
    row.prop(s, "points_w", text="H")

    col = box("Display")
    row = col.row(align=True)
    row.prop(s, "show_lattice", toggle=True)
    row.prop(s, "in_front", toggle=True)

    col = box("Deform")
    col.row(align=True).prop(s, "deform_mode", expand=True)
    sub = col.row(align=True)
    sub.enabled = s.deform_mode == "ALL"
    sub.prop(s, "falloff")
    col.prop(s, "interpolation", text="")
    col.prop(mod, "strength", slider=True)

    col = box("Control Points")
    row = col.row(align=True)
    row.operator("max.ffd_reset")
    row.operator("max.ffd_animate_all")
    col.separator()
    col.operator("max.ffd_conform", icon="MOD_SHRINKWRAP")
    row = col.row(align=True)
    row.prop(s, "conform_inside", toggle=True)
    row.prop(s, "conform_outside", toggle=True)
    col.prop(s, "offset")

    row = layout.row(align=True)
    row.operator("max.ffd_fit", icon="FULLSCREEN_ENTER")
    row.operator("max.ffd_update_volume", icon="FILE_REFRESH")


classes = (MaxFFD, MAX_OT_ffd_level, MAX_OT_ffd_reset, MAX_OT_ffd_animate_all, MAX_OT_ffd_conform,
           MAX_OT_ffd_fit, MAX_OT_ffd_update_volume)


def register_props():
    bpy.types.Object.max_ffd = PointerProperty(type=MaxFFD)


def unregister_props():
    del bpy.types.Object.max_ffd
