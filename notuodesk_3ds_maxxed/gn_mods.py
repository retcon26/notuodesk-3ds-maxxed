"""3ds Max modifiers that Blender lacks, built as Geometry Nodes groups:
Melt, Skew, Squeeze, Slice, Noise, Push, Spherify.

Each group is created once per file (named "3dsMaxxed <Name>") and reused."""

import math

import bpy

PREFIX = "3dsMaxxed "


# ---------------------------------------------------------------------------
# tiny node-building helpers
# ---------------------------------------------------------------------------

class G:
    def __init__(self, name):
        self.ng = bpy.data.node_groups.new(PREFIX + name, "GeometryNodeTree")
        if hasattr(self.ng, "is_modifier"):
            self.ng.is_modifier = True
        self.nodes, self.links = self.ng.nodes, self.ng.links
        self.ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
        self.ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
        self.gi = self.nodes.new("NodeGroupInput")
        self.go = self.nodes.new("NodeGroupOutput")
        self.gi.location = (-900, 0)
        self.go.location = (900, 0)

    def inp(self, name, kind="FLOAT", default=0.0, lo=None, hi=None, subtype=None, desc=""):
        stype = {"FLOAT": "NodeSocketFloat", "INT": "NodeSocketInt", "BOOL": "NodeSocketBool",
                 "VECTOR": "NodeSocketVector"}[kind]
        s = self.ng.interface.new_socket(name, in_out="INPUT", socket_type=stype)
        s.description = desc
        try:
            s.default_value = default
            if lo is not None:
                s.min_value = lo
            if hi is not None:
                s.max_value = hi
            if subtype:
                s.subtype = subtype
        except (AttributeError, TypeError):
            pass
        return name

    def g(self, name):
        return self.gi.outputs[name]

    def _set(self, node, i, v):
        if v is None:
            return
        if isinstance(v, (int, float, tuple)):
            node.inputs[i].default_value = v
        else:
            self.links.new(v, node.inputs[i])

    def m(self, op, a, b=None, c=None):
        n = self.nodes.new("ShaderNodeMath")
        n.operation = op
        for i, v in enumerate((a, b, c)):
            self._set(n, i, v)
        return n.outputs[0]

    def vm(self, op, a, b=None, out=0):
        n = self.nodes.new("ShaderNodeVectorMath")
        n.operation = op
        for i, v in enumerate((a, b)):
            self._set(n, i, v)
        return n.outputs[out]

    def xyz(self, vec):
        n = self.nodes.new("ShaderNodeSeparateXYZ")
        self._set(n, 0, vec)
        return n.outputs[0], n.outputs[1], n.outputs[2]

    def combine(self, x, y, z):
        n = self.nodes.new("ShaderNodeCombineXYZ")
        for i, v in enumerate((x, y, z)):
            self._set(n, i, v)
        return n.outputs[0]

    def position(self):
        return self.nodes.new("GeometryNodeInputPosition").outputs[0]

    def normal(self):
        return self.nodes.new("GeometryNodeInputNormal").outputs[0]

    def bbox(self):
        n = self.nodes.new("GeometryNodeBoundBox")
        self.links.new(self.g("Geometry"), n.inputs[0])
        return n.outputs["Min"], n.outputs["Max"]

    def set_position(self, geo, position=None, offset=None):
        n = self.nodes.new("GeometryNodeSetPosition")
        self.links.new(geo, n.inputs["Geometry"])
        if position is not None:
            self.links.new(position, n.inputs["Position"])
        if offset is not None:
            self.links.new(offset, n.inputs["Offset"])
        return n.outputs[0]

    def out(self, geo):
        self.links.new(geo, self.go.inputs[0])
        return self.ng

    def height_factor(self):
        """t = (z - minZ) / height, plus helpers used by most deformers."""
        mn, mx = self.bbox()
        mnx, mny, mnz = self.xyz(mn)
        mxx, mxy, mxz = self.xyz(mx)
        h = self.m("MAXIMUM", self.m("SUBTRACT", mxz, mnz), 1e-5)
        px, py, pz = self.xyz(self.position())
        t = self.m("DIVIDE", self.m("SUBTRACT", pz, mnz), h)
        cx = self.m("MULTIPLY", self.m("ADD", mnx, mxx), 0.5)
        cy = self.m("MULTIPLY", self.m("ADD", mny, mxy), 0.5)
        return dict(t=t, h=h, mnz=mnz, px=px, py=py, pz=pz, cx=cx, cy=cy)


# ---------------------------------------------------------------------------
# modifiers
# ---------------------------------------------------------------------------

def build_melt():
    """3ds Max Melt: the object sags toward its base and spreads out like a puddle.
    Irregularity makes some parts melt faster than others, so it drips unevenly."""
    g = G("Melt 2")
    g.inp("Amount", default=0.5, lo=0.0, hi=1.0, subtype="FACTOR",
          desc="How far the object has melted. Keyframe this to animate the melt")
    g.inp("% of Melt Spread", default=0.19, lo=0.0, hi=1.0, subtype="FACTOR",
          desc="How much the melted part spreads outward")
    g.inp("Solidity", default=2.0, lo=0.05, hi=10.0,
          desc="Ice 2.0, Glass 0.5, Jelly 0.4, Plastic 0.1. Lower = gooier")
    g.inp("Irregularity", default=0.35, lo=0.0, hi=1.0, subtype="FACTOR",
          desc="Uneven melting: some areas drip faster than others")
    g.inp("Drip Size", default=1.0, lo=0.01, hi=100.0, desc="Size of the uneven melting pattern")
    g.inp("Seed", default=0.0, desc="Random variation of the drips")
    g.inp("Flip Axis", "BOOL", default=False, desc="Melt toward the top instead of the base")
    v = g.height_factor()
    t = v["t"]
    flip = g.g("Flip Axis")
    t = g.m("ADD", g.m("MULTIPLY", t, g.m("SUBTRACT", 1.0, flip)),
            g.m("MULTIPLY", g.m("SUBTRACT", 1.0, t), flip))

    # uneven melting: noise over the footprint (x, y) varies the local amount
    tex = g.nodes.new("ShaderNodeTexNoise")
    try:
        tex.noise_dimensions = "4D"
    except Exception:
        pass
    g.links.new(g.combine(v["px"], v["py"], 0.0), tex.inputs["Vector"])
    if "W" in tex.inputs:
        g.links.new(g.g("Seed"), tex.inputs["W"])
    g.links.new(g.m("DIVIDE", 1.5, g.g("Drip Size")), tex.inputs["Scale"])
    tex.inputs["Detail"].default_value = 1.5   # cheap: only the footprint is sampled
    wobble = g.m("MULTIPLY", g.m("SUBTRACT", tex.outputs["Fac"], 0.5), g.m("MULTIPLY", g.g("Irregularity"), 2.0))
    amount = g.m("MINIMUM", g.m("MAXIMUM",
                 g.m("MULTIPLY", g.g("Amount"), g.m("ADD", 1.0, wobble)), 0.0), 1.0)

    # sag: upper parts drop more. t' = t * (1 - amount * t^(1/solidity))
    expo = g.m("DIVIDE", 1.0, g.g("Solidity"))
    sag = g.m("MULTIPLY", amount, g.m("POWER", g.m("MAXIMUM", t, 0.0), expo))
    t2 = g.m("MAXIMUM", g.m("MULTIPLY", t, g.m("SUBTRACT", 1.0, sag)), 0.0)
    # spread: the closer to the ground after melting, the wider it gets (the puddle)
    near = g.m("POWER", g.m("SUBTRACT", 1.0, t2), 2.0)
    scale = g.m("ADD", 1.0, g.m("MULTIPLY", g.m("MULTIPLY", g.g("% of Melt Spread"), amount),
                                  g.m("MULTIPLY", near, 3.0)))
    nx = g.m("ADD", v["cx"], g.m("MULTIPLY", g.m("SUBTRACT", v["px"], v["cx"]), scale))
    ny = g.m("ADD", v["cy"], g.m("MULTIPLY", g.m("SUBTRACT", v["py"], v["cy"]), scale))
    t2f = g.m("ADD", g.m("MULTIPLY", t2, g.m("SUBTRACT", 1.0, flip)),
              g.m("MULTIPLY", g.m("SUBTRACT", 1.0, t2), flip))
    nz = g.m("ADD", v["mnz"], g.m("MULTIPLY", t2f, v["h"]))
    return g.out(g.set_position(g.g("Geometry"), position=g.combine(nx, ny, nz)))


def build_skew():
    g = G("Skew")
    g.inp("Amount", default=0.5, desc="Skew distance at the top of the object")
    g.inp("Direction", default=0.0, subtype="ANGLE", desc="Direction of the skew around the Z axis")
    v = g.height_factor()
    d = g.g("Direction")
    off = g.m("MULTIPLY", g.g("Amount"), v["t"])
    ox = g.m("MULTIPLY", off, g.m("COSINE", d))
    oy = g.m("MULTIPLY", off, g.m("SINE", d))
    return g.out(g.set_position(g.g("Geometry"), offset=g.combine(ox, oy, 0.0)))


def build_squeeze():
    g = G("Squeeze")
    g.inp("Axial Bulge", default=0.5, lo=-1.0, hi=4.0, desc="Bulge outward around the middle")
    g.inp("Curve", default=2.0, lo=0.1, hi=10.0, desc="Shape of the bulge")
    g.inp("Radial Squeeze", default=0.0, lo=-1.0, hi=1.0, desc="Squash height (positive) or stretch (negative)")
    v = g.height_factor()
    bump = g.m("POWER", g.m("SINE", g.m("MULTIPLY", v["t"], math.pi)), g.g("Curve"))
    scale = g.m("ADD", 1.0, g.m("MULTIPLY", g.g("Axial Bulge"), bump))
    nx = g.m("ADD", v["cx"], g.m("MULTIPLY", g.m("SUBTRACT", v["px"], v["cx"]), scale))
    ny = g.m("ADD", v["cy"], g.m("MULTIPLY", g.m("SUBTRACT", v["py"], v["cy"]), scale))
    zs = g.m("SUBTRACT", 1.0, g.m("MULTIPLY", g.g("Radial Squeeze"), 0.5))
    nz = g.m("ADD", v["mnz"], g.m("MULTIPLY", g.m("SUBTRACT", v["pz"], v["mnz"]), zs))
    return g.out(g.set_position(g.g("Geometry"), position=g.combine(nx, ny, nz)))


def build_slice():
    g = G("Slice")
    g.inp("Slice Height", default=0.5, lo=0.0, hi=1.0, subtype="FACTOR", desc="Where the slice plane sits")
    g.inp("Remove Bottom", "BOOL", default=False, desc="Remove below the plane instead of above")
    v = g.height_factor()
    above = g.m("GREATER_THAN", v["t"], g.g("Slice Height"))
    flip = g.g("Remove Bottom")
    sel = g.m("ABSOLUTE", g.m("SUBTRACT", above, flip))
    dn = g.nodes.new("GeometryNodeDeleteGeometry")
    g.links.new(g.g("Geometry"), dn.inputs["Geometry"])
    g.links.new(sel, dn.inputs["Selection"])
    return g.out(dn.outputs[0])


def build_noise():
    g = G("Noise")
    g.inp("Seed", default=0.0, desc="Random seed")
    g.inp("Scale", default=1.0, lo=0.001, desc="Noise size")
    g.inp("Strength", "VECTOR", default=(0.0, 0.0, 0.3), desc="Displacement per axis")
    g.inp("Fractal Detail", default=2.0, lo=0.0, hi=15.0)
    tex = g.nodes.new("ShaderNodeTexNoise")
    try:
        tex.noise_dimensions = "4D"
    except Exception:
        pass
    g.links.new(g.position(), tex.inputs["Vector"])
    if "W" in tex.inputs:
        g.links.new(g.g("Seed"), tex.inputs["W"])
    g.links.new(g.g("Scale"), tex.inputs["Scale"])
    g.links.new(g.g("Fractal Detail"), tex.inputs["Detail"])
    centered = g.vm("SUBTRACT", tex.outputs["Color"], (0.5, 0.5, 0.5))
    off = g.vm("MULTIPLY", g.vm("MULTIPLY", centered, g.g("Strength")), (2.0, 2.0, 2.0))
    return g.out(g.set_position(g.g("Geometry"), offset=off))


def build_push():
    g = G("Push")
    g.inp("Push Value", default=0.1, desc="Move every vertex along its normal")
    off = g.vm("SCALE", g.normal(), None)
    n = off.node
    g.links.new(g.g("Push Value"), n.inputs["Scale"])
    return g.out(g.set_position(g.g("Geometry"), offset=off))


def build_spherify():
    g = G("Spherify")
    g.inp("Percent", default=1.0, lo=0.0, hi=1.0, subtype="FACTOR")
    mn, mx = g.bbox()
    c = g.vm("SCALE", g.vm("ADD", mn, mx), None)
    c.node.inputs["Scale"].default_value = 0.5
    size = g.vm("LENGTH", g.vm("SUBTRACT", mx, mn), None, out=1)
    radius = g.m("MULTIPLY", size, 0.35)
    p = g.position()
    d = g.vm("NORMALIZE", g.vm("SUBTRACT", p, c))
    sphere_pt = g.vm("ADD", c, g.vm("MULTIPLY", d, g.combine(radius, radius, radius)))
    mix = g.nodes.new("ShaderNodeMix")
    mix.data_type = "VECTOR"
    g.links.new(g.g("Percent"), mix.inputs[0])
    g.links.new(p, mix.inputs[4])
    g.links.new(sphere_pt, mix.inputs[5])
    return g.out(g.set_position(g.g("Geometry"), position=mix.outputs[1]))


BUILDERS = {
    "MELT": ("Melt 2", build_melt),
    "SKEW": ("Skew", build_skew),
    "SQUEEZE": ("Squeeze", build_squeeze),
    "SLICE": ("Slice", build_slice),
    "NOISE": ("Noise", build_noise),
    "PUSH": ("Push", build_push),
    "SPHERIFY": ("Spherify", build_spherify),
}


def get_group(key):
    label, fn = BUILDERS[key]
    ng = bpy.data.node_groups.get(PREFIX + label)
    if ng is None:
        ng = fn()
    return ng


def add(ob, key, name):
    mod = ob.modifiers.new(name, "NODES")
    mod.node_group = get_group(key)
    return mod


def inputs(mod):
    """(identifier, name) of the user-facing inputs of a node-group modifier."""
    ng = mod.node_group
    if ng is None:
        return []
    out = []
    for item in ng.interface.items_tree:
        if getattr(item, "item_type", "") == "SOCKET" and item.in_out == "INPUT" \
                and item.socket_type != "NodeSocketGeometry":
            out.append((item.identifier, item.name))
    return out


def input_ref(mod, identifier):
    """(data, property name) for drawing / setting a node-modifier input.
    Blender 5: mod.properties.inputs.<id>.value; Blender 4.x: mod["<id>"]."""
    props = getattr(mod, "properties", None)
    holder = getattr(getattr(props, "inputs", None), identifier, None) if props is not None else None
    if holder is not None:
        return holder, "value"
    return mod, f'["{identifier}"]'


def set_input(mod, name, value):
    for ident, n in inputs(mod):
        if n == name:
            data, prop = input_ref(mod, ident)
            if prop == "value":
                data.value = value
            else:
                mod[ident] = value
            return True
    return False


def keyframe_input(mod, name, frame):
    """Insert a keyframe on a node-modifier input (Blender 4.x and 5.x)."""
    for ident, n in inputs(mod):
        if n == name:
            data, prop = input_ref(mod, ident)
            return data.keyframe_insert(prop, frame=frame)
    return False


def is_melt(mod):
    return mod is not None and mod.type == "NODES" and mod.node_group is not None \
        and mod.node_group.name.startswith(PREFIX + "Melt")
