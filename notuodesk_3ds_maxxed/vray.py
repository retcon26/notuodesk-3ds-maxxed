"""V-Ray workflow for 3ds Max users.

* If Chaos "V-Ray for Blender" is installed, it is detected and can be made the
  active renderer from Rendering > V-Ray, and its own operators are listed there.
* VRayMtl / VRayLight / VRaySun / VRayPhysicalCamera / VRayPlane are created as
  native Blender data, using the V-Ray parameter names Max users know. They render
  in Cycles (and EEVEE) out of the box, and V-Ray for Blender can convert them.
"""

import math

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, StringProperty
from bpy.types import Menu, Operator, PropertyGroup

from .operators import max_name

VRAY_URL = "https://www.chaos.com/vray/blender"


def vray_engine():
    """bl_idname of an installed V-Ray render engine, or None."""
    for cls in bpy.types.RenderEngine.__subclasses__():
        label = (getattr(cls, "bl_label", "") or "").lower()
        ident = (getattr(cls, "bl_idname", "") or "").lower()
        if "v-ray" in label or "vray" in label or "vray" in ident:
            return cls.bl_idname
    return None


def vray_operator_modules():
    return [m for m in dir(bpy.ops) if "vray" in m.lower()]


def _link(context, ob):
    context.view_layer.active_layer_collection.collection.objects.link(ob)
    for o in context.selected_objects:
        o.select_set(False)
    ob.select_set(True)
    context.view_layer.objects.active = ob
    return ob


def _object_mode(context):
    if context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")


# ---------------------------------------------------------------------------
# VRayMtl
# ---------------------------------------------------------------------------

def _principled(mat):
    if not mat or not mat.node_tree:
        return None
    for n in mat.node_tree.nodes:
        if n.type == "BSDF_PRINCIPLED":
            return n
    return None


def _inp(node, *names):
    for n in names:
        if n in node.inputs:
            return node.inputs[n]
    return None


def _gloss_get(mat):
    p = _principled(mat)
    s = _inp(p, "Roughness") if p else None
    return 1.0 - s.default_value if s else 1.0


def _gloss_set(mat, value):
    p = _principled(mat)
    s = _inp(p, "Roughness") if p else None
    if s:
        s.default_value = 1.0 - value


class MAX_OT_vray_material(Operator):
    """Create a VRayMtl and assign it to the selected objects"""
    bl_idname = "max.vray_material"
    bl_label = "VRayMtl"
    bl_options = {"REGISTER", "UNDO"}

    preset: EnumProperty(items=[
        ("DEFAULT", "Default", "Grey diffuse"), ("GLOSSY", "Glossy Plastic", ""),
        ("METAL", "Brushed Metal", ""), ("CHROME", "Chrome", ""), ("GLASS", "Glass", ""),
        ("CAR_PAINT", "Car Paint", ""), ("EMISSIVE", "Light Material", "VRayLightMtl")])

    def execute(self, context):
        mat = bpy.data.materials.new(max_name("VRayMtl" if self.preset != "EMISSIVE" else "VRayLightMtl"))
        mat.use_nodes = True
        mat["max_vray"] = 1
        p = _principled(mat)
        base = _inp(p, "Base Color")
        rough = _inp(p, "Roughness")
        metal = _inp(p, "Metallic")
        trans = _inp(p, "Transmission Weight", "Transmission")
        ior = _inp(p, "IOR")
        coat = _inp(p, "Coat Weight", "Clearcoat")
        emit = _inp(p, "Emission Color", "Emission")
        emit_s = _inp(p, "Emission Strength")
        base.default_value = (0.5, 0.5, 0.5, 1)
        rough.default_value = 0.5
        ior.default_value = 1.6
        pr = self.preset
        if pr == "GLOSSY":
            base.default_value = (0.6, 0.05, 0.05, 1)
            rough.default_value = 0.15
        elif pr in {"METAL", "CHROME"}:
            base.default_value = (0.9, 0.9, 0.9, 1)
            metal.default_value = 1.0
            rough.default_value = 0.35 if pr == "METAL" else 0.02
        elif pr == "GLASS":
            base.default_value = (1, 1, 1, 1)
            trans.default_value = 1.0
            rough.default_value = 0.0
            ior.default_value = 1.517
        elif pr == "CAR_PAINT":
            base.default_value = (0.02, 0.1, 0.5, 1)
            rough.default_value = 0.3
            if coat:
                coat.default_value = 1.0
        elif pr == "EMISSIVE" and emit:
            emit.default_value = (1, 1, 1, 1)
            if emit_s:
                emit_s.default_value = 5.0
        mat.diffuse_color = base.default_value
        for ob in context.selected_objects:
            if ob.type in {"MESH", "CURVE", "FONT", "SURFACE", "META"}:
                if ob.material_slots:
                    ob.material_slots[ob.active_material_index].material = mat
                else:
                    ob.data.materials.append(mat)
        self.report({"INFO"}, f"{mat.name} assigned")
        return {"FINISHED"}


def draw_vraymtl(layout, mat):
    """V-Ray named parameters over the Principled BSDF."""
    p = _principled(mat)
    if p is None:
        layout.label(text="Not a VRayMtl (no Principled BSDF)")
        return
    col = layout.column(align=True)
    col.use_property_split = True
    col.use_property_decorate = False
    rows = [
        ("Diffuse", ("Base Color",)), ("Roughness (diffuse)", ("Diffuse Roughness",)),
        ("Reflect", ("Specular Tint",)), ("Reflection Amount", ("Specular IOR Level", "Specular")),
        ("Metalness", ("Metallic",)), ("Fresnel IOR", ("IOR",)),
        ("Refract", ("Transmission Weight", "Transmission")),
        ("Opacity", ("Alpha",)), ("Coat Amount", ("Coat Weight", "Clearcoat")),
        ("Sheen", ("Sheen Weight", "Sheen")), ("Self-Illumination", ("Emission Color", "Emission")),
        ("Self-Illum. Multiplier", ("Emission Strength",)),
    ]
    for label, names in rows:
        s = _inp(p, *names)
        if s is None or s.is_linked:
            continue
        if label == "Fresnel IOR":
            col.prop(mat, "max_vray_glossiness", text="Refl. Glossiness")
        col.prop(s, "default_value", text=label)


# ---------------------------------------------------------------------------
# Lights
# ---------------------------------------------------------------------------

def _world(context):
    world = context.scene.world or bpy.data.worlds.new("World")
    context.scene.world = world
    world.use_nodes = True
    return world, world.node_tree


def _world_output(nt):
    out = next((n for n in nt.nodes if n.type == "OUTPUT_WORLD"), None) or nt.nodes.new("ShaderNodeOutputWorld")
    bg = next((n for n in nt.nodes if n.type == "BACKGROUND"), None) or nt.nodes.new("ShaderNodeBackground")
    if not bg.outputs[0].is_linked:
        nt.links.new(bg.outputs[0], out.inputs[0])
    return bg


class MAX_OT_vray_light(Operator):
    """Create a V-Ray light"""
    bl_idname = "max.vray_light"
    bl_label = "VRayLight"
    bl_options = {"REGISTER", "UNDO"}

    kind: EnumProperty(items=[
        ("PLANE", "VRayLight (Plane)", ""), ("DISC", "VRayLight (Disc)", ""),
        ("SPHERE", "VRayLight (Sphere)", ""), ("DOME", "VRayLight (Dome)", ""),
        ("SUN", "VRaySun + VRaySky", ""), ("IES", "VRayIES", "")])
    filepath: StringProperty(subtype="FILE_PATH", default="")
    filter_glob: StringProperty(default="*.hdr;*.exr;*.hdri;*.png;*.jpg", options={"HIDDEN"})

    def invoke(self, context, event):
        if self.kind == "DOME":
            context.window_manager.fileselect_add(self)
            return {"RUNNING_MODAL"}
        return self.execute(context)

    def execute(self, context):
        _object_mode(context)
        cur = context.scene.cursor.location
        k = self.kind
        if k == "DOME":
            world, nt = _world(context)
            bg = _world_output(nt)
            if self.filepath:
                env = nt.nodes.new("ShaderNodeTexEnvironment")
                try:
                    env.image = bpy.data.images.load(self.filepath, check_existing=True)
                except RuntimeError as exc:
                    self.report({"WARNING"}, f"Could not load HDRI: {exc}")
                    return {"CANCELLED"}
                nt.links.new(env.outputs["Color"], bg.inputs["Color"])
            bg.inputs["Strength"].default_value = 1.0
            ob = bpy.data.objects.new(max_name("VRayLight"), None)   # helper marking the dome
            ob.empty_display_type = "SPHERE"
            ob.empty_display_size = 0.5
            ob["max_vray_dome"] = 1
            ob.location = cur
            _link(context, ob)
            self.report({"INFO"}, "Dome light: world lighting set" + (" from HDRI" if self.filepath else ""))
            return {"FINISHED"}
        if k == "SUN":
            data = bpy.data.lights.new(max_name("VRaySun"), "SUN")
            data.energy = 4.0
            data.angle = math.radians(0.53)
            ob = _link(context, bpy.data.objects.new(data.name, data))
            ob.location = cur + type(cur)((0, 0, 10))
            ob.rotation_euler = (math.radians(45), 0, math.radians(30))
            world, nt = _world(context)
            bg = _world_output(nt)
            sky = nt.nodes.new("ShaderNodeTexSky")
            nt.links.new(sky.outputs["Color"], bg.inputs["Color"])
            bg.inputs["Strength"].default_value = 0.3
            try:
                sky.sun_elevation = math.radians(45)
                sky.sun_rotation = math.radians(30)
            except AttributeError:
                pass
            self.report({"INFO"}, "VRaySun created with VRaySky environment")
            return {"FINISHED"}
        if k in {"PLANE", "DISC"}:
            data = bpy.data.lights.new(max_name("VRayLight"), "AREA")
            data.shape = "RECTANGLE" if k == "PLANE" else "DISK"
            data.size = 1.0
            if k == "PLANE":
                data.size_y = 1.0
            data.energy = 200
        elif k == "SPHERE":
            data = bpy.data.lights.new(max_name("VRayLight"), "POINT")
            data.shadow_soft_size = 0.5
            data.energy = 500
        else:  # IES: spot with soft cone, ready for an IES texture
            data = bpy.data.lights.new(max_name("VRayIES"), "SPOT")
            data.energy = 800
            data.spot_size = math.radians(90)
            data.spot_blend = 0.6
        ob = _link(context, bpy.data.objects.new(data.name, data))
        ob.location = cur + type(cur)((0, 0, 3))
        ob["max_vray_light"] = k
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# VRayPhysicalCamera
# ---------------------------------------------------------------------------

def _update_exposure(self, context):
    cam = self.id_data
    scene = context.scene
    if not self.exposure:
        return
    for ob in scene.objects:
        if ob.data == cam and scene.camera == ob:
            break
    else:
        return
    # 0 EV at f/8, 1/200 s, ISO 100 (V-Ray's sunny-day defaults)
    ratio = (200.0 / max(self.shutter_speed, 1e-6)) * (self.iso / 100.0) * (8.0 / max(self.f_number, 1e-3)) ** 2
    scene.view_settings.exposure = math.log2(ratio)
    cam.dof.aperture_fstop = self.f_number


class MaxVRayCamera(PropertyGroup):
    enabled: BoolProperty(default=False)
    exposure: BoolProperty(name="Exposure", default=True, update=_update_exposure,
                           description="Drive scene exposure from f-number, shutter speed and ISO")
    f_number: FloatProperty(name="F-Number", default=8.0, min=0.5, max=64.0, update=_update_exposure)
    shutter_speed: FloatProperty(name="Shutter Speed (s^-1)", default=200.0, min=0.01, max=100000.0,
                                 update=_update_exposure)
    iso: FloatProperty(name="Film Speed (ISO)", default=100.0, min=1.0, max=100000.0, update=_update_exposure)


class MAX_OT_vray_camera(Operator):
    """Create a VRayPhysicalCamera"""
    bl_idname = "max.vray_camera"
    bl_label = "VRayPhysicalCamera"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        _object_mode(context)
        name = max_name("VRayPhysCamera")
        cam = bpy.data.cameras.new(name)
        cam.lens = 40.0
        cam.sensor_width = 36.0
        cam.max_vray.enabled = True
        ob = _link(context, bpy.data.objects.new(name, cam))
        ob.location = context.scene.cursor.location + type(context.scene.cursor.location)((0, -10, 2))
        ob.rotation_euler = (math.radians(85), 0, 0)
        if context.scene.camera is None:
            context.scene.camera = ob
        _update_exposure(cam.max_vray, context)
        return {"FINISHED"}


def draw_vray_camera(layout, cam):
    v = cam.max_vray
    col = layout.column(align=True)
    col.use_property_split = True
    col.use_property_decorate = False
    col.prop(cam, "sensor_width", text="Film Gate (mm)")
    col.prop(cam, "lens", text="Focal Length (mm)")
    col.prop(v, "f_number")
    col.prop(v, "shutter_speed")
    col.prop(v, "iso")
    col.prop(v, "exposure")
    col.prop(cam.dof, "use_dof", text="Depth of Field")


# ---------------------------------------------------------------------------
# VRayPlane, renderer
# ---------------------------------------------------------------------------

class MAX_OT_vray_plane(Operator):
    """VRayPlane: an (effectively) infinite ground plane"""
    bl_idname = "max.vray_plane"
    bl_label = "VRayPlane"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        _object_mode(context)
        me = bpy.data.meshes.new("VRayPlane")
        s = 5000.0
        me.from_pydata([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], [], [(0, 1, 2, 3)])
        ob = _link(context, bpy.data.objects.new(max_name("VRayPlane"), me))
        ob.location = (0, 0, context.scene.cursor.location.z)
        ob.color = (0.6, 0.6, 0.6, 1)
        return {"FINISHED"}


class MAX_OT_set_renderer(Operator):
    """Set the production renderer"""
    bl_idname = "max.set_renderer"
    bl_label = "Production Renderer"

    engine: StringProperty()

    def execute(self, context):
        if self.engine == "VRAY":
            eng = vray_engine()
            if eng is None:
                self.report({"WARNING"}, "V-Ray for Blender is not installed (Rendering > V-Ray > Get V-Ray)")
                return {"CANCELLED"}
            context.scene.render.engine = eng
        else:
            context.scene.render.engine = self.engine
        self.report({"INFO"}, f"Renderer: {context.scene.render.engine}")
        return {"FINISHED"}


class MAX_OT_vray_render_preset(Operator):
    """V-Ray-style quality preset (progressive sampling with a noise limit + denoiser)"""
    bl_idname = "max.vray_render_preset"
    bl_label = "Render Quality"
    bl_options = {"REGISTER", "UNDO"}

    quality: EnumProperty(items=[("DRAFT", "Draft", ""), ("MEDIUM", "Medium", ""),
                                 ("HIGH", "High", ""), ("VERY_HIGH", "Very High", "")])

    def execute(self, context):
        scene = context.scene
        eng = vray_engine()
        if eng and scene.render.engine == eng:
            self.report({"INFO"}, "V-Ray is active: use its own Render Setup (F10) for quality")
            return {"FINISHED"}
        scene.render.engine = "CYCLES"
        cy = scene.cycles
        samples, noise = {"DRAFT": (128, 0.05), "MEDIUM": (512, 0.02),
                          "HIGH": (1024, 0.01), "VERY_HIGH": (4096, 0.005)}[self.quality]
        cy.samples = samples
        cy.use_adaptive_sampling = True
        cy.adaptive_threshold = noise          # = V-Ray "Noise limit"
        cy.use_denoising = True                # = V-Ray denoiser render element
        cy.max_bounces = 12 if self.quality in {"HIGH", "VERY_HIGH"} else 8
        self.report({"INFO"}, f"{self.quality.title()}: {samples} max samples, noise limit {noise}")
        return {"FINISHED"}


class MAX_MT_vray(Menu):
    bl_label = "V-Ray"
    bl_idname = "MAX_MT_vray"

    def draw(self, context):
        lay = self.layout
        lay.operator_context = "INVOKE_DEFAULT"
        eng = vray_engine()
        if eng:
            lay.operator("max.set_renderer", text="Renderer: V-Ray", icon="CHECKMARK"
                         if context.scene.render.engine == eng else "BLANK1").engine = "VRAY"
        else:
            lay.operator("wm.url_open", text="Get V-Ray for Blender...", icon="URL").url = VRAY_URL
        lay.operator("max.set_renderer", text="Renderer: Cycles (V-Ray-style)", icon="CHECKMARK"
                     if context.scene.render.engine == "CYCLES" else "BLANK1").engine = "CYCLES"
        lay.separator()
        lay.operator_menu_enum("max.vray_render_preset", "quality", text="Quality Preset")
        lay.operator_menu_enum("max.vray_material", "preset", text="Apply VRayMtl")
        lay.operator_menu_enum("max.vray_light", "kind", text="Create VRayLight")
        lay.operator("max.vray_camera", text="Create VRayPhysicalCamera")
        lay.operator("max.vray_plane", text="Create VRayPlane")
        lay.separator()
        lay.operator("render.view_show", text="V-Ray Frame Buffer")
        mods = vray_operator_modules()
        if mods:
            lay.separator()
            lay.label(text="V-Ray for Blender tools:")
            for m in mods:
                for name in dir(getattr(bpy.ops, m))[:30]:
                    lay.operator(f"{m}.{name}")


classes = (MaxVRayCamera, MAX_OT_vray_material, MAX_OT_vray_light, MAX_OT_vray_camera,
           MAX_OT_vray_plane, MAX_OT_set_renderer, MAX_OT_vray_render_preset, MAX_MT_vray)


def register_props():
    bpy.types.Camera.max_vray = bpy.props.PointerProperty(type=MaxVRayCamera)
    bpy.types.Material.max_vray_glossiness = FloatProperty(
        name="Refl. Glossiness", min=0.0, max=1.0, subtype="FACTOR",
        get=_gloss_get, set=_gloss_set, description="V-Ray glossiness (1 - roughness)")


def unregister_props():
    del bpy.types.Material.max_vray_glossiness
    del bpy.types.Camera.max_vray
