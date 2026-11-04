"""Create panel: 3ds Max style click-drag primitive creation, shapes, lights, cameras, helpers."""

import math
import random

import bmesh
import bpy
from bpy.props import EnumProperty, IntProperty
from bpy.types import Operator
from bpy_extras import view3d_utils
from mathutils import Matrix, Vector
from mathutils.geometry import intersect_line_plane

from .operators import max_name

from .prims import PRIMITIVES, set_params

MAX_COLORS = [
    (0.88, 0.34, 0.78), (0.53, 0.89, 0.34), (0.34, 0.53, 0.89), (0.89, 0.73, 0.34),
    (0.34, 0.89, 0.85), (0.89, 0.34, 0.34), (0.60, 0.34, 0.89), (0.89, 0.55, 0.20),
    (0.23, 0.70, 0.45), (0.70, 0.70, 0.20), (0.18, 0.45, 0.80), (0.80, 0.25, 0.55),
]


def random_color():
    return (*random.choice(MAX_COLORS), 1.0)


# ---------------------------------------------------------------------------
# unit meshes. RECT kinds fill x,y in [-0.5, 0.5]; RADIUS kinds have radius 1.
# Kinds with height span z in [0, 1].
# ---------------------------------------------------------------------------

def _ring(bm, r, z, segs):
    return [bm.verts.new((r * math.cos(2 * math.pi * i / segs), r * math.sin(2 * math.pi * i / segs), z))
            for i in range(segs)]


def build_unit_mesh(kind, segs=24):
    bm = bmesh.new()
    smooth = False
    if kind == "BOX":
        bmesh.ops.create_cube(bm, size=1.0)
        bmesh.ops.translate(bm, verts=bm.verts, vec=(0, 0, 0.5))
    elif kind == "PLANE":
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=0.5)
    elif kind == "SPHERE":
        bmesh.ops.create_uvsphere(bm, u_segments=32, v_segments=16, radius=1.0)
        smooth = True
    elif kind == "GEOSPHERE":
        bmesh.ops.create_icosphere(bm, subdivisions=3, radius=1.0)
        smooth = True
    elif kind in {"CYLINDER", "CONE"}:
        bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segs,
                              radius1=1.0, radius2=0.0 if kind == "CONE" else 1.0, depth=1.0)
        bmesh.ops.translate(bm, verts=bm.verts, vec=(0, 0, 0.5))
    elif kind == "PYRAMID":
        bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=4,
                              radius1=math.sqrt(0.5), radius2=0.0, depth=1.0)
        bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=Matrix.Rotation(math.pi / 4, 3, "Z"))
        bmesh.ops.translate(bm, verts=bm.verts, vec=(0, 0, 0.5))
    elif kind == "TUBE":
        rings = [_ring(bm, r, z, segs) for r, z in ((1, 0), (1, 1), (0.75, 1), (0.75, 0))]
        for k in range(4):
            a, b = rings[k], rings[(k + 1) % 4]
            for i in range(segs):
                j = (i + 1) % segs
                bm.faces.new((a[i], a[j], b[j], b[i]))
    elif kind == "TORUS":
        sides = 12
        grid = []
        for i in range(segs):
            a = 2 * math.pi * i / segs
            row = []
            for j in range(sides):
                b = 2 * math.pi * j / sides
                r = 1.0 + 0.25 * math.cos(b)
                row.append(bm.verts.new((r * math.cos(a), r * math.sin(a), 0.25 * math.sin(b))))
            grid.append(row)
        for i in range(segs):
            for j in range(sides):
                i2, j2 = (i + 1) % segs, (j + 1) % sides
                bm.faces.new((grid[i][j], grid[i2][j], grid[i2][j2], grid[i][j2]))
        smooth = True
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(PRIMITIVES[kind][0])
    bm.to_mesh(me)
    bm.free()
    if smooth:
        for p in me.polygons:
            p.use_smooth = True
    return me


def new_object(context, name, data):
    ob = bpy.data.objects.new(name, data)
    context.view_layer.active_layer_collection.collection.objects.link(ob)
    ob.color = random_color()
    for o in context.selected_objects:
        o.select_set(False)
    ob.select_set(True)
    context.view_layer.objects.active = ob
    return ob


# ---------------------------------------------------------------------------
# construction plane helpers
# ---------------------------------------------------------------------------

def construction_frame(rv3d):
    """Home grid (XY) in perspective; the view plane in orthographic views."""
    if rv3d.is_perspective:
        n = Vector((0, 0, 1))
    else:
        d = rv3d.view_rotation @ Vector((0, 0, 1))
        i = max(range(3), key=lambda k: abs(d[k]))
        n = Vector((0, 0, 0))
        n[i] = 1.0 if d[i] > 0 else -1.0
    if abs(n.z) > 0.5:
        u = Vector((1, 0, 0))
        v = n.cross(u)
    else:
        v = Vector((0, 0, 1))
        u = v.cross(n)
    return u, v, n


def mouse_ray(region, rv3d, co):
    origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, co)
    direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, co)
    return origin, direction


def ray_plane(region, rv3d, co, point, normal):
    o, d = mouse_ray(region, rv3d, co)
    return intersect_line_plane(o, o + d * 1000.0, point, normal)


def ray_line_height(region, rv3d, co, base, axis):
    """Signed distance along `axis` from `base` closest to the mouse ray."""
    o, d = mouse_ray(region, rv3d, co)
    w0 = base - o
    a, b, c = axis.dot(axis), axis.dot(d), d.dot(d)
    dd, e = axis.dot(w0), d.dot(w0)
    denom = a * c - b * b
    if abs(denom) < 1e-9:
        return 0.0
    return (b * e - c * dd) / denom


def region_under_mouse(context, mx, my):
    for area in context.window.screen.areas:
        if area.type != "VIEW_3D":
            continue
        if not (area.x <= mx < area.x + area.width and area.y <= my < area.y + area.height):
            continue
        for r in area.regions:
            if r.type in {"UI", "TOOLS", "HEADER", "TOOL_HEADER", "ASSET_SHELF"} and r.width > 1 and r.height > 1:
                if r.x <= mx < r.x + r.width and r.y <= my < r.y + r.height:
                    return None, None
        for r in area.regions:
            if r.type == "WINDOW" and r.x <= mx < r.x + r.width and r.y <= my < r.y + r.height:
                return area, r
    return None, None


# ---------------------------------------------------------------------------
# interactive creation
# ---------------------------------------------------------------------------

class MAX_OT_create(Operator):
    """Click-drag in any viewport to create (like 3ds Max). Right-click or Esc to stop"""
    bl_idname = "max.create"
    bl_label = "Create Primitive"

    kind: EnumProperty(items=[(k, v[0], "", v[1], i) for i, (k, v) in enumerate(PRIMITIVES.items())])
    segments: IntProperty(default=24, min=3, max=256)

    _session = 0          # id of the creation session currently in charge
    active_kind = ""      # for highlighting the button

    @classmethod
    def description(cls, context, props):
        label, _, style, height = PRIMITIVES[props.kind]
        steps = "drag the base, release, then move the mouse for height and click" if height else "drag to size"
        return f"{label}: in a viewport, {steps}. Right-click to stop creating"

    def invoke(self, context, event):
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
            context.window_manager.max_sublevel = 0
        MAX_OT_create._session += 1
        self.session = MAX_OT_create._session
        MAX_OT_create.active_kind = self.kind
        self.state = "WAIT"
        self.obj = None
        context.window_manager.modal_handler_add(self)
        self._status(context)
        self._redraw(context)
        return {"RUNNING_MODAL"}

    # -- helpers ------------------------------------------------------------
    def _status(self, context):
        label = PRIMITIVES[self.kind][0]
        msg = {
            "WAIT": f"Create {label}: click-drag in a viewport.  Right-click / Esc: stop",
            "BASE": f"{label}: drag to size the base, release mouse",
            "HEIGHT": f"{label}: move the mouse to set height, click to finish",
        }[self.state]
        try:
            context.workspace.status_text_set(msg)
        except Exception:
            pass

    def _redraw(self, context):
        for area in context.window.screen.areas:
            area.tag_redraw()

    def _co(self, event):
        r = self.region
        return Vector((event.mouse_x - r.x, event.mouse_y - r.y))

    def _finish(self, context):
        MAX_OT_create.active_kind = ""
        try:
            context.workspace.status_text_set(None)
        except Exception:
            pass
        self._redraw(context)
        return {"FINISHED"}

    def _cancel_object(self):
        if self.obj is not None:
            me = self.obj.data
            bpy.data.objects.remove(self.obj)
            if me and me.users == 0:
                bpy.data.meshes.remove(me)
        self.obj = None

    def _start(self, context, event, area, region):
        self.area, self.region = area, region
        self.rv3d = region.data
        self.u, self.v, self.n = construction_frame(self.rv3d)
        p = ray_plane(region, self.rv3d, self._co(event), Vector((0, 0, 0)), self.n)
        if p is None:
            return False
        if context.scene.tool_settings.use_snap:
            p = Vector([round(c) for c in p])   # snap to home grid units
        self.p0 = p
        label = PRIMITIVES[self.kind][0]
        self.obj = new_object(context, max_name(label), build_unit_mesh(self.kind, self.segments))
        rot = Matrix((self.u, self.v, self.n)).transposed().to_4x4()
        self.obj.matrix_world = Matrix.Translation(p) @ rot
        self.obj.scale = (1e-4, 1e-4, 1e-4)
        self.height = 0.0
        self.size = (0.0, 0.0)
        return True

    def _update_base(self, context, event):
        p = ray_plane(self.region, self.rv3d, self._co(event), self.p0, self.n)
        if p is None:
            return
        if context.scene.tool_settings.use_snap:
            p = Vector([round(c) for c in p])
        _, _, style, has_h = PRIMITIVES[self.kind]
        h = max(abs(self.height), 1e-4) if has_h else 1.0
        if style == "RECT":
            d = p - self.p0
            du, dv = d.dot(self.u), d.dot(self.v)
            center = self.p0 + (self.u * du + self.v * dv) * 0.5
            self.obj.location = center
            self.size = (abs(du), abs(dv))
            self.obj.scale = (max(abs(du), 1e-4), max(abs(dv), 1e-4), h)
        else:
            r = (p - self.p0).length
            self.size = (r, r)
            self.obj.location = self.p0
            z = h if has_h else r
            self.obj.scale = (max(r, 1e-4), max(r, 1e-4), max(z, 1e-4))

    def _update_height(self, context, event):
        base = self.obj.location.copy()
        view_dir = self.rv3d.view_rotation @ Vector((0, 0, 1))
        if not self.rv3d.is_perspective or abs(view_dir.dot(self.n)) > 0.97:
            # Height axis points at the viewer: use vertical mouse motion like 3ds Max
            co0 = self.release_co
            a = view3d_utils.region_2d_to_location_3d(self.region, self.rv3d, co0, base)
            b = view3d_utils.region_2d_to_location_3d(self.region, self.rv3d, co0 + Vector((0, 1)), base)
            h = (self._co(event).y - co0.y) * (b - a).length
        else:
            h = ray_line_height(self.region, self.rv3d, self._co(event), base, self.n)
        if context.scene.tool_settings.use_snap:
            h = round(h)
        self.height = h if abs(h) > 1e-4 else 1e-4
        sx, sy, _ = self.obj.scale
        self.obj.scale = (sx, sy, self.height)

    def _bake(self, context):
        """Apply scale into the mesh so the object ends with scale 1 (Max-style parameters)."""
        ob = self.obj
        s = ob.scale.copy()
        ob.scale = (1, 1, 1)
        k = self.kind
        if k in {"BOX", "PYRAMID", "PLANE"}:
            set_params(ob, k, width=abs(s.x), length=abs(s.y), height=s.z)
        elif k in {"CYLINDER", "CONE", "TUBE"}:
            set_params(ob, k, radius1=s.x, radius2=(0.0 if k == "CONE" else s.x * 0.75), height=s.z)
        elif k == "TORUS":
            set_params(ob, k, radius1=s.x, radius2=s.x * 0.25)
        else:
            set_params(ob, k, radius1=s.x)
        bpy.ops.ed.undo_push(message=f"Create {PRIMITIVES[self.kind][0]}")
        self.obj = None

    # -- modal ----------------------------------------------------------------
    def modal(self, context, event):
        if self.session != MAX_OT_create._session:   # another Create button was pressed
            self._cancel_object()
            return {"FINISHED"}

        if event.type in {"RIGHTMOUSE", "ESC"} and event.value == "PRESS":
            if self.state != "WAIT":
                self._cancel_object()
                self.state = "WAIT"
                self._status(context)
                return {"RUNNING_MODAL"}
            if event.type == "ESC" or region_under_mouse(context, event.mouse_x, event.mouse_y)[1]:
                return self._finish(context)
            return {"PASS_THROUGH"}

        if self.state == "WAIT":
            if event.type == "LEFTMOUSE" and event.value == "PRESS":
                area, region = region_under_mouse(context, event.mouse_x, event.mouse_y)
                if region is None:
                    return {"PASS_THROUGH"}
                if self._start(context, event, area, region):
                    self.state = "BASE"
                    self._status(context)
                    return {"RUNNING_MODAL"}
            return {"PASS_THROUGH"}

        if self.state == "BASE":
            if event.type == "MOUSEMOVE":
                self._update_base(context, event)
            elif event.type == "LEFTMOUSE" and event.value == "RELEASE":
                if max(self.size) < 1e-3:          # a click without a drag creates nothing
                    self._cancel_object()
                    self.state = "WAIT"
                elif PRIMITIVES[self.kind][3]:
                    self.release_co = self._co(event)
                    self.state = "HEIGHT"
                else:
                    self._bake(context)
                    self.state = "WAIT"
                self._status(context)
            return {"RUNNING_MODAL"} if event.type != "TIMER" else {"PASS_THROUGH"}

        if self.state == "HEIGHT":
            if event.type == "MOUSEMOVE":
                self._update_height(context, event)
            elif event.type == "LEFTMOUSE" and event.value == "PRESS":
                self._bake(context)
                self.state = "WAIT"
                self._status(context)
            elif event.type in {"WHEELUPMOUSE", "WHEELDOWNMOUSE", "MIDDLEMOUSE"}:
                return {"PASS_THROUGH"}
            return {"RUNNING_MODAL"}

        return {"PASS_THROUGH"}


# ---------------------------------------------------------------------------
# shapes, lights, cameras, helpers (created at the 3D cursor)
# ---------------------------------------------------------------------------

SHAPES = [
    ("LINE", "Line", "CURVE_PATH"), ("RECTANGLE", "Rectangle", "MESH_PLANE"),
    ("CIRCLE", "Circle", "CURVE_BEZCIRCLE"), ("ELLIPSE", "Ellipse", "MESH_CIRCLE"),
    ("ARC", "Arc", "SPHERECURVE"), ("NGON", "NGon", "SEQ_CHROMA_SCOPE"),
    ("STAR", "Star", "SOLO_OFF"), ("TEXT", "Text", "OUTLINER_OB_FONT"),
    ("HELIX", "Helix", "FORCE_VORTEX"),
]


def _poly_curve(context, name, points, cyclic):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    sp = cu.splines.new("POLY")
    sp.points.add(len(points) - 1)
    for pt, co in zip(sp.points, points):
        pt.co = (*co, 1.0)
    sp.use_cyclic_u = cyclic
    ob = new_object(context, name, cu)
    ob.location = context.scene.cursor.location
    return ob


class MAX_OT_create_shape(Operator):
    """Create a 3ds Max spline shape at the 3D cursor"""
    bl_idname = "max.create_shape"
    bl_label = "Create Shape"
    bl_options = {"REGISTER", "UNDO"}

    kind: EnumProperty(items=[(k, n, "", i, idx) for idx, (k, n, i) in enumerate(SHAPES)])
    radius: bpy.props.FloatProperty(name="Radius", default=1.0, min=0.001)
    sides: IntProperty(name="Sides", default=6, min=3, max=64)

    def execute(self, context):
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        k, r = self.kind, self.radius
        label = dict((a, b) for a, b, _ in SHAPES)[k]
        name = max_name(label)
        tau = 2 * math.pi
        if k == "LINE":
            _poly_curve(context, name, [(-r, 0, 0), (r, 0, 0)], False)
        elif k == "RECTANGLE":
            _poly_curve(context, name, [(-r, -r * .6, 0), (r, -r * .6, 0), (r, r * .6, 0), (-r, r * .6, 0)], True)
        elif k in {"CIRCLE", "ELLIPSE"}:
            bpy.ops.curve.primitive_bezier_circle_add(radius=r, location=context.scene.cursor.location)
            ob = context.active_object
            ob.name = name
            ob.color = random_color()
            if k == "ELLIPSE":
                ob.scale.y = 0.6
                bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        elif k == "ARC":
            pts = [(r * math.cos(a), r * math.sin(a), 0) for a in (i * math.pi / 16 for i in range(17))]
            _poly_curve(context, name, pts, False)
        elif k == "NGON":
            _poly_curve(context, name, [(r * math.cos(tau * i / self.sides), r * math.sin(tau * i / self.sides), 0)
                                        for i in range(self.sides)], True)
        elif k == "STAR":
            n = self.sides
            pts = [((r if i % 2 == 0 else r * .5) * math.cos(math.pi * i / n),
                    (r if i % 2 == 0 else r * .5) * math.sin(math.pi * i / n), 0) for i in range(2 * n)]
            _poly_curve(context, name, pts, True)
        elif k == "HELIX":
            pts = [(r * math.cos(t), r * math.sin(t), t * r * 0.1)
                   for t in (i * tau / 24 for i in range(24 * 3 + 1))]
            _poly_curve(context, name, pts, False)
        elif k == "TEXT":
            bpy.ops.object.text_add(location=context.scene.cursor.location)
            ob = context.active_object
            ob.name = name
            ob.data.body = "MAX Text"
            ob.color = random_color()
        return {"FINISHED"}


LIGHTS = [
    ("TARGET_SPOT", "Target Spot", "LIGHT_SPOT"), ("FREE_SPOT", "Free Spot", "LIGHT_SPOT"),
    ("TARGET_DIRECT", "Target Direct", "LIGHT_SUN"), ("FREE_DIRECT", "Free Direct", "LIGHT_SUN"),
    ("OMNI", "Omni", "LIGHT_POINT"), ("AREA", "Free Area (Photometric)", "LIGHT_AREA"),
    ("SKYLIGHT", "Skylight", "WORLD"),
]


def _add_target(context, ob, offset):
    cursor = context.scene.cursor.location.copy()
    tgt = bpy.data.objects.new(ob.name + ".Target", None)
    tgt.empty_display_type = "CUBE"
    tgt.empty_display_size = 0.1
    context.view_layer.active_layer_collection.collection.objects.link(tgt)
    tgt.location = cursor
    ob.location = cursor + Vector(offset)
    con = ob.constraints.new("TRACK_TO")
    con.target = tgt
    con.track_axis = "TRACK_NEGATIVE_Z"
    con.up_axis = "UP_Y"
    return tgt


class MAX_OT_create_light(Operator):
    """Create a 3ds Max style light"""
    bl_idname = "max.create_light"
    bl_label = "Create Light"
    bl_options = {"REGISTER", "UNDO"}

    kind: EnumProperty(items=[(k, n, "", i, idx) for idx, (k, n, i) in enumerate(LIGHTS)])

    def execute(self, context):
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        k = self.kind
        if k == "SKYLIGHT":
            world = context.scene.world or bpy.data.worlds.new("World")
            context.scene.world = world
            world.color = (0.55, 0.65, 0.8)
            if world.use_nodes and world.node_tree and "Background" in world.node_tree.nodes:
                bg = world.node_tree.nodes["Background"]
                bg.inputs[0].default_value = (0.55, 0.65, 0.8, 1)
                bg.inputs[1].default_value = 1.0
            self.report({"INFO"}, "Skylight: world lighting set (see Environment, key 8)")
            return {"FINISHED"}
        ltype = {"OMNI": "POINT", "AREA": "AREA"}.get(k, "SPOT" if "SPOT" in k else "SUN")
        base = {"OMNI": "Omni", "AREA": "PhotometricLight", "TARGET_SPOT": "Spot", "FREE_SPOT": "FSpot",
                "TARGET_DIRECT": "Direct", "FREE_DIRECT": "FDirect"}[k]
        name = max_name(base)
        data = bpy.data.lights.new(name, ltype)
        data.energy = {"POINT": 1000, "SPOT": 1000, "SUN": 3, "AREA": 300}[ltype]
        ob = new_object(context, name, data)
        ob.location = context.scene.cursor.location
        if k.startswith("TARGET"):
            _add_target(context, ob, (3, -3, 4))
        elif k.startswith("FREE"):
            ob.location.z += 4
        else:
            ob.location.z += 2
        return {"FINISHED"}


class MAX_OT_create_camera(Operator):
    """Create a 3ds Max style camera"""
    bl_idname = "max.create_camera"
    bl_label = "Create Camera"
    bl_options = {"REGISTER", "UNDO"}

    target: bpy.props.BoolProperty(default=True)

    def execute(self, context):
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        name = max_name("PhysCamera" if not self.target else "Camera")
        data = bpy.data.cameras.new(name)
        ob = new_object(context, name, data)
        if self.target:
            _add_target(context, ob, (6, -6, 4))
        else:
            ob.location = context.scene.cursor.location + Vector((0, -8, 2))
            ob.rotation_euler = (math.radians(85), 0, 0)
        if context.scene.camera is None:
            context.scene.camera = ob
        return {"FINISHED"}


HELPERS = [
    ("DUMMY", "Dummy", "CUBE"), ("POINT", "Point", "PLAIN_AXES"),
    ("ARROWS", "ExposeTM", "ARROWS"), ("SPHERE", "Sphere Gizmo", "SPHERE"),
    ("CIRCLE", "Circle Gizmo", "CIRCLE"), ("CONE", "Cone Gizmo", "CONE"),
]


class MAX_OT_create_helper(Operator):
    """Create a helper object (empty)"""
    bl_idname = "max.create_helper"
    bl_label = "Create Helper"
    bl_options = {"REGISTER", "UNDO"}

    kind: EnumProperty(items=[(k, n, "") for k, n, _ in HELPERS])

    def execute(self, context):
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        label, dtype = {k: (n, t) for k, n, t in HELPERS}[self.kind]
        ob = new_object(context, max_name(label.split()[0]), None)
        ob.empty_display_type = dtype
        ob.location = context.scene.cursor.location
        return {"FINISHED"}


classes = (MAX_OT_create, MAX_OT_create_shape, MAX_OT_create_light, MAX_OT_create_camera, MAX_OT_create_helper)
