"""3ds Max TurboSmooth.

A native Subdivision Surface modifier (fast, GPU subdivision in the viewport)
presented with TurboSmooth's parameters:

Main               Iterations, Render Iters, Isoline Display, Explicit Normals
Surface Parameters Smooth Result, Separate by Materials / Smoothing Groups
Update Options     Always / When Rendering

"Separate by" keeps borders crisp the way Max does, by fully creasing the edges
between different materials / along smoothing-group (sharp) edges.
"""

import bpy
import numpy as np
from bpy.props import BoolProperty, EnumProperty, IntProperty, PointerProperty
from bpy.types import Operator, PropertyGroup

NAME = "TurboSmooth"
SMOOTH_BACKUP = "max_ts_orig_smooth"     # face attribute holding the pre-TurboSmooth smoothing


def is_turbosmooth(mod):
    return mod is not None and mod.type == "SUBSURF" and mod.name.startswith(NAME)


def ts_modifier(ob):
    if ob is None:
        return None
    act = ob.modifiers.active
    if is_turbosmooth(act):
        return act
    return next((m for m in ob.modifiers if is_turbosmooth(m)), None)


# ---------------------------------------------------------------------------
# mesh helpers
# ---------------------------------------------------------------------------

def _edge_face_material_boundaries(me):
    """Boolean array: edges whose adjacent faces use different materials."""
    n_e = len(me.edges)
    if n_e == 0 or len(me.polygons) == 0:
        return np.zeros(n_e, bool)
    loop_edges = np.empty(len(me.loops), np.int32)
    me.loops.foreach_get("edge_index", loop_edges)
    totals = np.empty(len(me.polygons), np.int32)
    me.polygons.foreach_get("loop_total", totals)
    mats = np.empty(len(me.polygons), np.int32)
    me.polygons.foreach_get("material_index", mats)
    loop_mat = np.repeat(mats, totals)
    lo = np.full(n_e, np.iinfo(np.int32).max, np.int32)
    hi = np.full(n_e, -1, np.int32)
    np.minimum.at(lo, loop_edges, loop_mat)
    np.maximum.at(hi, loop_edges, loop_mat)
    return (hi >= 0) & (lo != hi)


def _sharp_edges(me):
    attr = me.attributes.get("sharp_edge")
    if attr is None or attr.domain != "EDGE":
        return np.zeros(len(me.edges), bool)
    vals = np.zeros(len(me.edges), bool)
    attr.data.foreach_get("value", vals)
    return vals


def apply_separation(ob, by_materials, by_smoothing):
    """Crease (1.0) the edges TurboSmooth should keep separate; clear ones it no longer should."""
    me = ob.data
    if ob.mode == "EDIT":
        return
    mask_mat = _edge_face_material_boundaries(me)
    mask_sg = _sharp_edges(me)
    want = np.zeros(len(me.edges), bool)
    if by_materials:
        want |= mask_mat
    if by_smoothing:
        want |= mask_sg
    managed = mask_mat | mask_sg
    attr = me.attributes.get("crease_edge")
    if attr is None:
        if not want.any():
            return
        attr = me.attributes.new("crease_edge", "FLOAT", "EDGE")
    vals = np.zeros(len(me.edges), np.float32)
    attr.data.foreach_get("value", vals)
    vals[managed & ~want] = 0.0          # only touch edges TurboSmooth manages
    vals[want] = 1.0
    attr.data.foreach_set("value", vals)
    me.update()


def apply_smooth_result(ob, on):
    """Smooth Result on: smooth every face (backing up the original smoothing).
    Off: restore the original smoothing."""
    me = ob.data
    if ob.mode == "EDIT":
        return
    n = len(me.polygons)
    if on:
        if SMOOTH_BACKUP not in me.attributes:
            orig = np.zeros(n, bool)
            me.polygons.foreach_get("use_smooth", orig)
            me.attributes.new(SMOOTH_BACKUP, "BOOLEAN", "FACE").data.foreach_set("value", orig)
        me.polygons.foreach_set("use_smooth", np.ones(n, bool))
    else:
        backup = me.attributes.get(SMOOTH_BACKUP)
        if backup is not None:
            orig = np.zeros(n, bool)
            backup.data.foreach_get("value", orig)
            me.polygons.foreach_set("use_smooth", orig)
            me.attributes.remove(backup)
    me.update()


# ---------------------------------------------------------------------------
# Max parameters (computed over the modifier where possible)
# ---------------------------------------------------------------------------

def _mod(self):
    return ts_modifier(self.id_data)


def _iters_get(self):
    m = _mod(self)
    return m.levels if m else 1


def _iters_set(self, v):
    m = _mod(self)
    if m:
        m.levels = v
        if not self.render_iters_on:
            m.render_levels = v


def _riters_get(self):
    m = _mod(self)
    return m.render_levels if m else 1


def _riters_set(self, v):
    m = _mod(self)
    if m:
        m.render_levels = v


def _render_on_update(self, context):
    m = _mod(self)
    if m and not self.render_iters_on:
        m.render_levels = m.levels


def _iso_get(self):
    m = _mod(self)
    return bool(m and m.show_only_control_edges)


def _iso_set(self, v):
    m = _mod(self)
    if m:
        m.show_only_control_edges = v


def _normals_get(self):
    m = _mod(self)
    return bool(m and m.use_custom_normals)


def _normals_set(self, v):
    m = _mod(self)
    if m:
        m.use_custom_normals = v


def _update_mode_get(self):
    m = _mod(self)
    return 0 if (m is None or m.show_viewport) else 1


def _update_mode_set(self, v):
    m = _mod(self)
    if m:
        m.show_viewport = (v == 0)
        m.show_render = True


def _smooth_update(self, context):
    apply_smooth_result(self.id_data, self.smooth_result)


def _separate_update(self, context):
    apply_separation(self.id_data, self.separate_materials, self.separate_smoothing)


class MaxTurboSmooth(PropertyGroup):
    iterations: IntProperty(name="Iterations", min=0, max=10, get=_iters_get, set=_iters_set,
                            description="Subdivision steps in the viewport")
    render_iters_on: BoolProperty(name="Render Iters", default=False, update=_render_on_update,
                                  description="Use a different number of iterations when rendering")
    render_iters: IntProperty(name="Render Iterations", min=0, max=10, get=_riters_get, set=_riters_set)
    isoline: BoolProperty(name="Isoline Display", get=_iso_get, set=_iso_set,
                          description="Show only the original cage edges on the smoothed surface")
    explicit_normals: BoolProperty(name="Explicit Normals", get=_normals_get, set=_normals_set,
                                   description="Keep custom normals through the smoothing")
    smooth_result: BoolProperty(name="Smooth Result", default=True, update=_smooth_update,
                                description="Smooth-shade the whole result")
    separate_materials: BoolProperty(name="Materials", default=False, update=_separate_update,
                                     description="Keep a crisp border between faces with different materials")
    separate_smoothing: BoolProperty(name="Smoothing Groups", default=False, update=_separate_update,
                                     description="Keep a crisp border along sharp (smoothing-group) edges")
    update_mode: EnumProperty(name="Update Options",
                              items=[("ALWAYS", "Always", "Smooth in the viewport and render"),
                                     ("RENDER", "When Rendering", "Only smooth at render time (fast viewport)")],
                              get=_update_mode_get, set=_update_mode_set)


# ---------------------------------------------------------------------------
# operator + UI
# ---------------------------------------------------------------------------

class MAX_OT_turbosmooth(Operator):
    """Add a TurboSmooth modifier (3ds Max)"""
    bl_idname = "max.turbosmooth"
    bl_label = "TurboSmooth"
    bl_options = {"REGISTER", "UNDO"}

    iterations: IntProperty(name="Iterations", default=1, min=0, max=10)

    @classmethod
    def poll(cls, context):
        return any(o.type == "MESH" for o in context.selected_objects) or (
            context.active_object is not None and context.active_object.type == "MESH")

    def execute(self, context):
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        targets = [o for o in context.selected_objects if o.type == "MESH"]
        if not targets and context.active_object and context.active_object.type == "MESH":
            targets = [context.active_object]
        for ob in targets:
            mod = ob.modifiers.new(NAME, "SUBSURF")
            mod.levels = mod.render_levels = self.iterations
            mod.show_only_control_edges = False    # Max: Isoline Display off by default
            mod.use_creases = True
            mod.quality = 3
            ob.modifiers.active = mod
            ts = ob.max_turbosmooth
            ts.render_iters_on = False
            ts.smooth_result = True                # Max default: Smooth Result on
            apply_smooth_result(ob, True)
        self.report({"INFO"}, f"TurboSmooth added to {len(targets)} object(s)")
        return {"FINISHED"}


def draw(layout, ob, mod):
    ts = ob.max_turbosmooth

    def box(title):
        b = layout.box()
        b.label(text=title)
        return b.column(align=True)

    col = box("Main")
    col.prop(ts, "iterations")
    row = col.row(align=True)
    row.prop(ts, "render_iters_on", text="Render Iters")
    sub = row.row(align=True)
    sub.enabled = ts.render_iters_on
    sub.prop(ts, "render_iters", text="")
    col.prop(ts, "isoline")
    col.prop(ts, "explicit_normals")

    col = box("Surface Parameters")
    col.prop(ts, "smooth_result")
    col.label(text="Separate by:")
    row = col.row(align=True)
    row.prop(ts, "separate_materials", toggle=True)
    row.prop(ts, "separate_smoothing", toggle=True)

    col = box("Update Options")
    col.row(align=True).prop(ts, "update_mode", expand=True)

    adv = layout.column(align=True)
    adv.use_property_split = True
    adv.use_property_decorate = False
    adv.prop(mod, "quality")
    adv.prop(mod, "uv_smooth", text="UV Smooth")
    adv.prop(mod, "boundary_smooth", text="Boundary")


classes = (MaxTurboSmooth, MAX_OT_turbosmooth)


def register_props():
    bpy.types.Object.max_turbosmooth = PointerProperty(type=MaxTurboSmooth)


def unregister_props():
    del bpy.types.Object.max_turbosmooth
