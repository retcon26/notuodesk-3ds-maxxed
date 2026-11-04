"""Parametric primitives: objects keep their creation parameters (Length, Width,
Height, Segs ...) and can be edited in the Modify panel until they are collapsed
to an Editable Poly, exactly like 3ds Max."""

import math

import bmesh
import bpy
from bpy.props import BoolProperty, FloatProperty, IntProperty, StringProperty
from mathutils import Matrix

# kind: (label, icon, base style for click-drag, has height stage)
PRIMITIVES = {
    "BOX": ("Box", "MESH_CUBE", "RECT", True),
    "CONE": ("Cone", "MESH_CONE", "RADIUS", True),
    "SPHERE": ("Sphere", "MESH_UVSPHERE", "RADIUS", False),
    "GEOSPHERE": ("GeoSphere", "MESH_ICOSPHERE", "RADIUS", False),
    "CYLINDER": ("Cylinder", "MESH_CYLINDER", "RADIUS", True),
    "TUBE": ("Tube", "MESH_CIRCLE", "RADIUS", True),
    "TORUS": ("Torus", "MESH_TORUS", "RADIUS", False),
    "PYRAMID": ("Pyramid", "MARKER", "RECT", True),
    "PLANE": ("Plane", "MESH_PLANE", "RECT", False),
}

# 3ds Max default segment counts
DEFAULTS = {
    "BOX": dict(length_segs=1, width_segs=1, height_segs=1),
    "CONE": dict(sides=24, height_segs=5),
    "SPHERE": dict(sides=32),
    "GEOSPHERE": dict(sides=4),
    "CYLINDER": dict(sides=18, height_segs=5),
    "TUBE": dict(sides=18, height_segs=5),
    "TORUS": dict(sides=24, height_segs=12),
    "PYRAMID": dict(length_segs=1, width_segs=1, height_segs=1),
    "PLANE": dict(length_segs=4, width_segs=4),
}

# which parameters each kind shows: (property, label)
UI_FIELDS = {
    "BOX": [("length", "Length"), ("width", "Width"), ("height", "Height"), None,
            ("length_segs", "Length Segs"), ("width_segs", "Width Segs"), ("height_segs", "Height Segs")],
    "PLANE": [("length", "Length"), ("width", "Width"), None,
              ("length_segs", "Length Segs"), ("width_segs", "Width Segs")],
    "PYRAMID": [("width", "Width"), ("length", "Depth"), ("height", "Height"), None,
                ("width_segs", "Width Segs"), ("length_segs", "Depth Segs"), ("height_segs", "Height Segs")],
    "SPHERE": [("radius1", "Radius"), ("sides", "Segments"), ("smooth", "Smooth")],
    "GEOSPHERE": [("radius1", "Radius"), ("sides", "Segments"), ("smooth", "Smooth")],
    "CYLINDER": [("radius1", "Radius"), ("height", "Height"), None,
                 ("height_segs", "Height Segments"), ("sides", "Sides"), ("smooth", "Smooth")],
    "CONE": [("radius1", "Radius 1"), ("radius2", "Radius 2"), ("height", "Height"), None,
             ("height_segs", "Height Segments"), ("sides", "Sides"), ("smooth", "Smooth")],
    "TUBE": [("radius1", "Radius 1"), ("radius2", "Radius 2"), ("height", "Height"), None,
             ("height_segs", "Height Segments"), ("sides", "Sides"), ("smooth", "Smooth")],
    "TORUS": [("radius1", "Radius 1"), ("radius2", "Radius 2"), None,
              ("sides", "Segments"), ("height_segs", "Sides"), ("smooth", "Smooth")],
}


def _slice(bm, axis, start, size, count):
    """Cut the mesh into `count` equal slices along an axis (Max 'Segs')."""
    no = [0.0, 0.0, 0.0]
    no[axis] = 1.0
    for i in range(1, count):
        co = [0.0, 0.0, 0.0]
        co[axis] = start + size * i / count
        geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
        bmesh.ops.bisect_plane(bm, geom=geom, dist=1e-6, plane_co=co, plane_no=no)


def _ring(bm, r, z, segs):
    return [bm.verts.new((r * math.cos(2 * math.pi * i / segs), r * math.sin(2 * math.pi * i / segs), z))
            for i in range(segs)]


def build_bmesh(kind, p):
    bm = bmesh.new()
    h = p.height
    ah = abs(h) if abs(h) > 1e-6 else 1e-6
    smooth_all = False
    if kind in {"BOX", "PYRAMID"}:
        if kind == "BOX":
            bmesh.ops.create_cube(bm, size=1.0)
        else:
            bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=4,
                                  radius1=math.sqrt(0.5), radius2=0.0, depth=1.0)
            bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=Matrix.Rotation(math.pi / 4, 3, "Z"))
        bmesh.ops.scale(bm, verts=bm.verts, vec=(p.width, p.length, ah))
        bmesh.ops.translate(bm, verts=bm.verts, vec=(0, 0, ah / 2))
        _slice(bm, 0, -p.width / 2, p.width, p.width_segs)
        _slice(bm, 1, -p.length / 2, p.length, p.length_segs)
        _slice(bm, 2, 0.0, ah, p.height_segs)
    elif kind == "PLANE":
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=0.5)
        bmesh.ops.scale(bm, verts=bm.verts, vec=(p.width, p.length, 1.0))
        _slice(bm, 0, -p.width / 2, p.width, p.width_segs)
        _slice(bm, 1, -p.length / 2, p.length, p.length_segs)
    elif kind == "SPHERE":
        bmesh.ops.create_uvsphere(bm, u_segments=max(p.sides, 4), v_segments=max(p.sides // 2, 2), radius=p.radius1)
    elif kind == "GEOSPHERE":
        bmesh.ops.create_icosphere(bm, subdivisions=max(1, min(p.sides, 7)), radius=p.radius1)
    elif kind in {"CYLINDER", "CONE"}:
        r2 = p.radius1 if kind == "CYLINDER" else p.radius2
        bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=max(p.sides, 3),
                              radius1=p.radius1, radius2=r2, depth=ah)
        bmesh.ops.translate(bm, verts=bm.verts, vec=(0, 0, ah / 2))
        _slice(bm, 2, 0.0, ah, p.height_segs)
    elif kind == "TUBE":
        segs = max(p.sides, 3)
        rings = [_ring(bm, r, z, segs) for r, z in
                 ((p.radius1, 0), (p.radius1, ah), (p.radius2, ah), (p.radius2, 0))]
        for k in range(4):
            a, b = rings[k], rings[(k + 1) % 4]
            for i in range(segs):
                j = (i + 1) % segs
                bm.faces.new((a[i], a[j], b[j], b[i]))
        _slice(bm, 2, 0.0, ah, p.height_segs)
    elif kind == "TORUS":
        segs, sides = max(p.sides, 3), max(p.height_segs, 3)
        grid = []
        for i in range(segs):
            a = 2 * math.pi * i / segs
            row = []
            for j in range(sides):
                b = 2 * math.pi * j / sides
                r = p.radius1 + p.radius2 * math.cos(b)
                row.append(bm.verts.new((r * math.cos(a), r * math.sin(a), p.radius2 * math.sin(b))))
            grid.append(row)
        for i in range(segs):
            for j in range(sides):
                i2, j2 = (i + 1) % segs, (j + 1) % sides
                bm.faces.new((grid[i][j], grid[i2][j], grid[i2][j2], grid[i][j2]))
        smooth_all = True
    if kind in {"SPHERE", "GEOSPHERE"}:
        smooth_all = True
    if h < 0 and kind in {"BOX", "PYRAMID", "CYLINDER", "CONE", "TUBE"}:
        bmesh.ops.scale(bm, verts=bm.verts, vec=(1, 1, -1))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    if p.smooth:
        for f in bm.faces:
            # smooth round surfaces only, keep caps / boxes flat
            f.smooth = smooth_all or abs(f.normal.z) < 0.7
    return bm


def rebuild(ob):
    p = ob.max_prim
    if not p.kind or ob.type != "MESH":
        return False
    me = ob.data
    if p.vcount and len(me.vertices) != p.vcount:
        p.kind = ""          # mesh was edited: it is an Editable Poly now
        return False
    bm = build_bmesh(p.kind, p)
    bm.to_mesh(me)
    bm.free()
    me.update()
    p.vcount = len(me.vertices)
    return True


_guard = [False]


def _update(self, context):
    if _guard[0]:
        return
    ob = self.id_data
    _guard[0] = True
    try:
        rebuild(ob)
    finally:
        _guard[0] = False


class MaxPrimParams(bpy.types.PropertyGroup):
    kind: StringProperty(default="")
    vcount: IntProperty(default=0)
    length: FloatProperty(name="Length", default=1.0, min=0.0001, unit="LENGTH", update=_update)
    width: FloatProperty(name="Width", default=1.0, min=0.0001, unit="LENGTH", update=_update)
    height: FloatProperty(name="Height", default=1.0, unit="LENGTH", update=_update)
    radius1: FloatProperty(name="Radius 1", default=1.0, min=0.0001, unit="LENGTH", update=_update)
    radius2: FloatProperty(name="Radius 2", default=0.0, min=0.0, unit="LENGTH", update=_update)
    length_segs: IntProperty(name="Length Segs", default=1, min=1, max=200, update=_update)
    width_segs: IntProperty(name="Width Segs", default=1, min=1, max=200, update=_update)
    height_segs: IntProperty(name="Height Segs", default=1, min=1, max=200, update=_update)
    sides: IntProperty(name="Sides", default=18, min=1, max=200, update=_update)
    smooth: BoolProperty(name="Smooth", default=True, update=_update)


def set_params(ob, kind, **values):
    """Assign parameters without triggering a rebuild for each one, then rebuild once."""
    p = ob.max_prim
    _guard[0] = True
    try:
        p.kind = kind
        p.vcount = 0
        for k, v in {**DEFAULTS.get(kind, {}), **values}.items():
            setattr(p, k, v)
    finally:
        _guard[0] = False
    rebuild(ob)


def collapse(ob):
    if hasattr(ob, "max_prim"):
        ob.max_prim.kind = ""


classes = (MaxPrimParams,)


def register_props():
    bpy.types.Object.max_prim = bpy.props.PointerProperty(type=MaxPrimParams)


def unregister_props():
    del bpy.types.Object.max_prim
