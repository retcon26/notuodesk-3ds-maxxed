"""3ds Max Compact Material Editor.

Lives in the sidebar ("Material Editor" tab) of a Shader Editor window that M
opens; the node canvas next to it plays the role of the Slate editor. Every
Max parameter reads and writes the material's Principled BSDF directly, so the
material renders the same in EEVEE, Cycles and (via conversion) V-Ray.
"""

import os

import bpy
from bpy.props import (BoolProperty, CollectionProperty, EnumProperty, FloatProperty,
                       FloatVectorProperty, IntProperty, PointerProperty, StringProperty)
from bpy.types import Menu, Operator, Panel, PropertyGroup
from bpy_extras import view3d_utils
from bpy_extras.io_utils import ImportHelper

NUM_SLOTS = 24
MAX_DEFAULT_DIFFUSE = (150 / 255, 150 / 255, 150 / 255)   # 3ds Max default material grey


# ---------------------------------------------------------------------------
# Principled helpers
# ---------------------------------------------------------------------------

def bsdf(mat):
    if mat is None or not mat.use_nodes or mat.node_tree is None:
        return None
    for n in mat.node_tree.nodes:
        if n.type == "BSDF_PRINCIPLED":
            return n
    return None


def _sock(mat, name):
    p = bsdf(mat)
    return p.inputs.get(name) if p else None


def _getf(mat, name, default=0.0):
    s = _sock(mat, name)
    return s.default_value if s is not None else default


def _setf(mat, name, value):
    s = _sock(mat, name)
    if s is not None:
        s.default_value = value


def _getc(mat, name, default=(0.8, 0.8, 0.8)):
    s = _sock(mat, name)
    return tuple(s.default_value[:3]) if s is not None else default


def _setc(mat, name, value):
    s = _sock(mat, name)
    if s is not None:
        s.default_value = (*value[:3], 1.0)
    if name == "Base Color":
        mat.diffuse_color = (*value[:3], mat.diffuse_color[3])


def ensure_nodes(mat):
    if not mat.use_nodes:
        mat.use_nodes = True
    return bsdf(mat)


# ---------------------------------------------------------------------------
# Standard material parameters (computed properties over the Principled BSDF)
# ---------------------------------------------------------------------------

SHADERS = [
    ("BLINN", "Blinn", "Classic plastic-like shading"),
    ("PHONG", "Phong", "Smooth, slightly sharper highlights"),
    ("METAL", "Metal", "Metallic surface"),
    ("ANISOTROPIC", "Anisotropic", "Brushed / stretched highlights"),
    ("OREN_NAYAR", "Oren-Nayar-Blinn", "Matte, rough surfaces like fabric or clay"),
    ("TRANSLUCENT", "Translucent Shader", "Light passes through (subsurface)"),
    ("MULTI_LAYER", "Multi-Layer", "Two highlight layers (coat)"),
]


def _shader_update(self, context):
    mat = self.id_data
    if bsdf(mat) is None:
        return
    s = self.shader
    _setf(mat, "Metallic", 1.0 if s == "METAL" else 0.0)
    _setf(mat, "Anisotropic", 0.6 if s == "ANISOTROPIC" else 0.0)
    _setf(mat, "Diffuse Roughness", 0.6 if s == "OREN_NAYAR" else 0.0)
    _setf(mat, "Subsurface Weight", 0.5 if s == "TRANSLUCENT" else 0.0)
    _setf(mat, "Coat Weight", 1.0 if s == "MULTI_LAYER" else 0.0)


def _users(mat):
    return [o for o in bpy.data.objects if o.type == "MESH" and mat.name in [m.name for m in o.data.materials if m]]


def _wire_update(self, context):
    for ob in _users(self.id_data):
        ob.show_wire = self.wire


def _faceted_update(self, context):
    for ob in _users(self.id_data):
        ob.data.polygons.foreach_set("use_smooth", [not self.faceted] * len(ob.data.polygons))
        ob.data.update()


class MaxStdMaterial(PropertyGroup):
    shader: EnumProperty(name="Shader", items=SHADERS, default="BLINN", update=_shader_update)
    wire: BoolProperty(name="Wire", update=_wire_update)
    faceted: BoolProperty(name="Faceted", update=_faceted_update)
    soften: FloatProperty(name="Soften", default=0.1, min=0.0, max=1.0)
    self_illum_color_on: BoolProperty(name="Color", default=False,
                                      update=lambda s, c: _apply_self_illum(s.id_data))
    self_illum_color: FloatVectorProperty(name="Self-Illumination Color", subtype="COLOR", size=3,
                                          default=(1.0, 1.0, 1.0), min=0.0, max=1.0,
                                          update=lambda s, c: _apply_self_illum(s.id_data))
    self_illum_amount: FloatProperty(name="Self-Illumination", default=0.0, min=0.0, max=100.0,
                                     update=lambda s, c: _apply_self_illum(s.id_data))
    bump_amount: FloatProperty(name="Bump Amount", default=30.0, min=0.0, max=999.0,
                               update=lambda s, c: _apply_bump_amount(s.id_data))


def _apply_self_illum(mat):
    m = mat.max_std
    if m.self_illum_color_on:
        _setc(mat, "Emission Color", m.self_illum_color)
        _setf(mat, "Emission Strength", 1.0)
    else:
        _setc(mat, "Emission Color", _getc(mat, "Base Color"))
        _setf(mat, "Emission Strength", m.self_illum_amount / 100.0)


# Computed Material properties (get/set straight into the Principled BSDF)
def _p_diffuse_get(mat): return _getc(mat, "Base Color", MAX_DEFAULT_DIFFUSE)
def _p_diffuse_set(mat, v): _setc(mat, "Base Color", v)
def _p_spec_get(mat): return _getc(mat, "Specular Tint", (1, 1, 1))
def _p_spec_set(mat, v): _setc(mat, "Specular Tint", v)
def _p_level_get(mat): return round(_getf(mat, "Specular IOR Level", 0.5) * 100.0)
def _p_level_set(mat, v): _setf(mat, "Specular IOR Level", v / 100.0)
def _p_gloss_get(mat): return round((1.0 - _getf(mat, "Roughness", 0.5)) * 100.0)
def _p_gloss_set(mat, v): _setf(mat, "Roughness", 1.0 - v / 100.0)
def _p_opacity_get(mat): return round(_getf(mat, "Alpha", 1.0) * 100.0)
def _p_ior_get(mat): return _getf(mat, "IOR", 1.5)
def _p_ior_set(mat, v): _setf(mat, "IOR", v)


def _p_opacity_set(mat, v):
    _setf(mat, "Alpha", v / 100.0)
    try:
        mat.surface_render_method = "BLENDED" if v < 100 else "DITHERED"
    except Exception:
        pass


def _p_two_sided_get(mat): return not mat.use_backface_culling
def _p_two_sided_set(mat, v): mat.use_backface_culling = not v


MATERIAL_PROPS = {
    "max_diffuse": FloatVectorProperty(name="Diffuse", subtype="COLOR", size=3, min=0, max=1,
                                       get=_p_diffuse_get, set=_p_diffuse_set),
    "max_specular": FloatVectorProperty(name="Specular", subtype="COLOR", size=3, min=0, max=1,
                                        get=_p_spec_get, set=_p_spec_set),
    "max_spec_level": IntProperty(name="Specular Level", min=0, max=999, soft_max=100,
                                  get=_p_level_get, set=_p_level_set),
    "max_glossiness": IntProperty(name="Glossiness", min=0, max=100, get=_p_gloss_get, set=_p_gloss_set),
    "max_opacity": IntProperty(name="Opacity", min=0, max=100, subtype="PERCENTAGE",
                               get=_p_opacity_get, set=_p_opacity_set),
    "max_ior": FloatProperty(name="Index of Refraction", min=1.0, max=10.0, get=_p_ior_get, set=_p_ior_set),
    "max_two_sided": BoolProperty(name="2-Sided", get=_p_two_sided_get, set=_p_two_sided_set),
}


# ---------------------------------------------------------------------------
# Map channels
# ---------------------------------------------------------------------------

# key: (label, Principled socket, is color data)
MAP_CHANNELS = [
    ("AMBIENT", "Ambient Color", None, True),
    ("DIFFUSE", "Diffuse Color", "Base Color", True),
    ("SPECULAR_COLOR", "Specular Color", "Specular Tint", True),
    ("SPECULAR_LEVEL", "Specular Level", "Specular IOR Level", False),
    ("GLOSSINESS", "Glossiness", "Roughness", False),
    ("SELF_ILLUM", "Self-Illumination", "Emission Color", True),
    ("OPACITY", "Opacity", "Alpha", False),
    ("FILTER", "Filter Color", "Specular Tint", True),
    ("BUMP", "Bump", "Normal", False),
    ("REFLECTION", "Reflection", "Metallic", False),
    ("REFRACTION", "Refraction", "Transmission Weight", False),
    ("DISPLACEMENT", "Displacement", None, False),
]
MAP_INFO = {k: (label, sock, color) for k, label, sock, color in MAP_CHANNELS}
MAP_PREFIX = "MaxMap_"


def map_node(mat, channel):
    if mat is None or mat.node_tree is None:
        return None
    return mat.node_tree.nodes.get(MAP_PREFIX + channel)


def clear_map(mat, channel):
    nt = mat.node_tree
    for n in list(nt.nodes):
        if n.name.startswith(MAP_PREFIX + channel):
            nt.nodes.remove(n)


def set_map(mat, channel, image):
    p = ensure_nodes(mat)
    nt = mat.node_tree
    label, sock, is_color = MAP_INFO[channel]
    clear_map(mat, channel)
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.name = MAP_PREFIX + channel
    tex.label = f"{label} Map"
    tex.image = image
    tex.location = (p.location.x - 600, p.location.y - 120 * [k for k, *_ in MAP_CHANNELS].index(channel))
    if not is_color and image is not None:
        try:
            image.colorspace_settings.name = "Non-Color"
        except TypeError:
            pass
    out = tex.outputs["Color"]
    if channel == "GLOSSINESS":                    # glossiness map = inverted roughness
        inv = nt.nodes.new("ShaderNodeInvert")
        inv.name = MAP_PREFIX + channel + "_invert"
        inv.location = (tex.location.x + 300, tex.location.y)
        nt.links.new(out, inv.inputs["Color"])
        out = inv.outputs["Color"]
    if channel == "BUMP":
        bump = nt.nodes.new("ShaderNodeBump")
        bump.name = MAP_PREFIX + channel + "_bump"
        bump.location = (tex.location.x + 300, tex.location.y)
        bump.inputs["Strength"].default_value = mat.max_std.bump_amount / 100.0
        nt.links.new(out, bump.inputs["Height"])
        nt.links.new(bump.outputs["Normal"], p.inputs["Normal"])
        return tex
    if channel == "DISPLACEMENT":
        outn = next((n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"), None)
        disp = nt.nodes.new("ShaderNodeDisplacement")
        disp.name = MAP_PREFIX + channel + "_disp"
        disp.location = (tex.location.x + 300, tex.location.y)
        nt.links.new(out, disp.inputs["Height"])
        if outn:
            nt.links.new(disp.outputs[0], outn.inputs["Displacement"])
        return tex
    if channel == "AMBIENT":                       # ambient is locked to diffuse in Max
        sock = "Base Color"
    if channel == "SELF_ILLUM":
        _setf(mat, "Emission Strength", 1.0)
    if channel == "OPACITY":
        try:
            mat.surface_render_method = "DITHERED"
        except Exception:
            pass
    nt.links.new(out, p.inputs[sock])
    return tex


def _apply_bump_amount(mat):
    n = mat.node_tree.nodes.get(MAP_PREFIX + "BUMP_bump") if mat.node_tree else None
    if n:
        n.inputs["Strength"].default_value = mat.max_std.bump_amount / 100.0


# ---------------------------------------------------------------------------
# Sample slots
# ---------------------------------------------------------------------------

class MaxMtlSlot(PropertyGroup):
    material: PointerProperty(type=bpy.types.Material)


class MaxMtlEditorState(PropertyGroup):
    slots: CollectionProperty(type=MaxMtlSlot)
    active: IntProperty(default=0, min=0, max=NUM_SLOTS - 1)
    visible: EnumProperty(name="Sample Slots", items=[("6", "3 x 2", ""), ("15", "5 x 3", ""), ("24", "6 x 4", "")],
                          default="6")


def new_default_material(index):
    mat = bpy.data.materials.new(f"{index + 1:02d} - Default")
    mat.use_nodes = True
    mat.use_fake_user = True            # keep editor materials like Max does, even if unassigned
    p = bsdf(mat)
    _setc(mat, "Base Color", MAX_DEFAULT_DIFFUSE)
    _setf(mat, "Specular IOR Level", 0.0)    # Max default: Specular Level 0, Glossiness 10
    _setf(mat, "Roughness", 0.9)
    return mat


def state(context):
    return context.scene.max_mtl_editor


def ensure_slots(scene):
    st = scene.max_mtl_editor
    while len(st.slots) < NUM_SLOTS:
        st.slots.add()


def active_material(context):
    st = state(context)
    if st.active < len(st.slots):
        return st.slots[st.active].material
    return None


def _show_in_node_editor(context, mat):
    sp = context.space_data
    if sp is not None and sp.type == "NODE_EDITOR" and mat is not None and mat.node_tree is not None:
        try:
            sp.pin = True
            sp.node_tree = mat.node_tree
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------

class MAX_OT_mtl_slot(Operator):
    """Sample slot: click to make it active"""
    bl_idname = "max.mtl_slot"
    bl_label = "Sample Slot"
    bl_options = {"INTERNAL", "UNDO"}

    index: IntProperty()

    def execute(self, context):
        ensure_slots(context.scene)
        st = state(context)
        st.active = self.index
        slot = st.slots[self.index]
        if slot.material is None:
            slot.material = new_default_material(self.index)
        _show_in_node_editor(context, slot.material)
        return {"FINISHED"}


class MAX_OT_mtl_get(Operator):
    """Get Material: put an existing material into the active sample slot"""
    bl_idname = "max.mtl_get"
    bl_label = "Get Material"
    bl_property = "material"
    bl_options = {"UNDO"}

    def _items(self, context):
        items = [(m.name, m.name, "", m.preview.icon_id if m.preview else 0, i)
                 for i, m in enumerate(sorted(bpy.data.materials, key=lambda m: m.name.lower()))
                 if not m.is_grease_pencil]
        MAX_OT_mtl_get._cache = items
        return items

    material: EnumProperty(items=_items)

    def invoke(self, context, event):
        context.window_manager.invoke_search_popup(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        ensure_slots(context.scene)
        mat = bpy.data.materials.get(self.material)
        if mat is None:
            return {"CANCELLED"}
        st = state(context)
        st.slots[st.active].material = mat
        _show_in_node_editor(context, mat)
        return {"FINISHED"}


class MAX_OT_mtl_assign(Operator):
    """Assign Material to Selection"""
    bl_idname = "max.mtl_assign"
    bl_label = "Assign Material to Selection"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return active_material(context) is not None and any(
            o.type in {"MESH", "CURVE", "FONT", "SURFACE", "META"} for o in context.selected_objects)

    def execute(self, context):
        mat = active_material(context)
        n = 0
        for ob in context.selected_objects:
            if ob.type not in {"MESH", "CURVE", "FONT", "SURFACE", "META"}:
                continue
            ob.data.materials.clear()          # Max replaces the object's material
            ob.data.materials.append(mat)
            n += 1
        mat.use_fake_user = False if mat.users > 1 else mat.use_fake_user
        self.report({"INFO"}, f"{mat.name} assigned to {n} object(s)")
        return {"FINISHED"}


class MAX_OT_mtl_reset(Operator):
    """Reset Map/Mtl to Default Settings"""
    bl_idname = "max.mtl_reset"
    bl_label = "Reset Map/Mtl to Default Settings"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        mat = active_material(context)
        if mat is None:
            return {"CANCELLED"}
        for k, *_ in MAP_CHANNELS:
            clear_map(mat, k)
        mat.max_std.shader = "BLINN"
        mat.max_diffuse = MAX_DEFAULT_DIFFUSE
        mat.max_specular = (1, 1, 1)
        mat.max_spec_level = 0
        mat.max_glossiness = 10
        mat.max_opacity = 100
        mat.max_std.self_illum_amount = 0
        mat.max_std.self_illum_color_on = False
        return {"FINISHED"}


class MAX_OT_mtl_make_unique(Operator):
    """Make Material Copy / Make Unique"""
    bl_idname = "max.mtl_make_unique"
    bl_label = "Make Material Copy"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        st = state(context)
        mat = active_material(context)
        if mat is None:
            return {"CANCELLED"}
        new = mat.copy()
        new.use_fake_user = True
        st.slots[st.active].material = new
        _show_in_node_editor(context, new)
        return {"FINISHED"}


class MAX_OT_mtl_put_library(Operator):
    """Put to Library: mark the material as an asset so it appears in the Asset Browser"""
    bl_idname = "max.mtl_put_library"
    bl_label = "Put to Library"

    def execute(self, context):
        mat = active_material(context)
        if mat is None:
            return {"CANCELLED"}
        mat.asset_mark()
        mat.asset_generate_preview()
        self.report({"INFO"}, f"{mat.name} added to the asset library (Asset Browser > Current File)")
        return {"FINISHED"}


class MAX_OT_mtl_select_by(Operator):
    """Select by Material: select every object that uses this material"""
    bl_idname = "max.mtl_select_by"
    bl_label = "Select by Material"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        mat = active_material(context)
        if mat is None:
            return {"CANCELLED"}
        users = [o for o in context.view_layer.objects
                 if hasattr(o.data, "materials") and o.data and mat.name in [m.name for m in o.data.materials if m]]
        for o in context.view_layer.objects:
            o.select_set(o in users)
        if users:
            context.view_layer.objects.active = users[0]
        self.report({"INFO"}, f"{len(users)} object(s) use {mat.name}")
        return {"FINISHED"}


class MAX_OT_mtl_show_in_viewport(Operator):
    """Show Shaded Material in Viewport (textures in the 3D views)"""
    bl_idname = "max.mtl_show_in_viewport"
    bl_label = "Show Shaded Material in Viewport"

    def execute(self, context):
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == "VIEW_3D":
                    sh = area.spaces.active.shading
                    sh.type = "SOLID"
                    sh.color_type = "OBJECT" if sh.color_type == "TEXTURE" else "TEXTURE"
        return {"FINISHED"}


class MAX_OT_mtl_set_type(Operator):
    """Material type"""
    bl_idname = "max.mtl_set_type"
    bl_label = "Material Type"
    bl_options = {"REGISTER", "UNDO"}

    kind: EnumProperty(items=[("STANDARD", "Standard", ""), ("VRAY", "VRayMtl", ""),
                              ("PHYSICAL", "Physical Material", "")])

    def execute(self, context):
        mat = active_material(context)
        if mat is None:
            return {"CANCELLED"}
        if self.kind == "VRAY":
            mat["max_vray"] = 1
        else:
            if "max_vray" in mat:
                del mat["max_vray"]
        mat["max_type"] = self.kind
        return {"FINISHED"}


class MAX_OT_mtl_load_map(Operator, ImportHelper):
    """Load a Bitmap into this map channel"""
    bl_idname = "max.mtl_load_map"
    bl_label = "Bitmap"
    bl_options = {"REGISTER", "UNDO"}

    channel: StringProperty(options={"HIDDEN"})
    filter_glob: StringProperty(default="*.png;*.jpg;*.jpeg;*.tga;*.tif;*.tiff;*.bmp;*.exr;*.hdr;*.psd;*.webp",
                                options={"HIDDEN"})

    @classmethod
    def description(cls, context, props):
        return f"{MAP_INFO.get(props.channel, ('Map',))[0]}: choose a bitmap"

    def execute(self, context):
        mat = active_material(context)
        if mat is None:
            return {"CANCELLED"}
        img = bpy.data.images.load(self.filepath, check_existing=True)
        set_map(mat, self.channel, img)
        return {"FINISHED"}


class MAX_OT_mtl_clear_map(Operator):
    """Remove this map"""
    bl_idname = "max.mtl_clear_map"
    bl_label = "Clear Map"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    channel: StringProperty()

    def execute(self, context):
        mat = active_material(context)
        if mat is not None:
            clear_map(mat, self.channel)
        return {"FINISHED"}


class MAX_OT_mtl_pick(Operator):
    """Pick Material from Object: click an object in a viewport (eyedropper)"""
    bl_idname = "max.mtl_pick"
    bl_label = "Pick Material from Object"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        context.window_manager.modal_handler_add(self)
        context.window.cursor_modal_set("EYEDROPPER")
        context.workspace.status_text_set("Pick Material: click an object.  Right-click / Esc: cancel")
        return {"RUNNING_MODAL"}

    def _finish(self, context):
        context.window.cursor_modal_restore()
        context.workspace.status_text_set(None)

    def modal(self, context, event):
        if event.type in {"RIGHTMOUSE", "ESC"}:
            self._finish(context)
            return {"CANCELLED"}
        if event.type == "LEFTMOUSE" and event.value == "PRESS":
            from .create import region_under_mouse
            area, region = region_under_mouse(context, event.mouse_x, event.mouse_y)
            if region is None:
                return {"RUNNING_MODAL"}
            co = (event.mouse_x - region.x, event.mouse_y - region.y)
            rv3d = region.data
            origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, co)
            direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, co)
            dg = context.evaluated_depsgraph_get()
            hit, _loc, _n, face, ob, _m = context.scene.ray_cast(dg, origin, direction)
            self._finish(context)
            if not hit or ob is None:
                self.report({"WARNING"}, "No object under the cursor")
                return {"CANCELLED"}
            ob = ob.original
            mat = None
            if ob.type == "MESH" and ob.data.materials:
                try:
                    mi = ob.evaluated_get(dg).data.polygons[face].material_index
                    mat = ob.material_slots[mi].material
                except (IndexError, AttributeError):
                    mat = ob.active_material
            else:
                mat = ob.active_material
            if mat is None:
                self.report({"WARNING"}, f"{ob.name} has no material")
                return {"CANCELLED"}
            ensure_slots(context.scene)
            st = state(context)
            st.slots[st.active].material = mat
            self.report({"INFO"}, f"Picked {mat.name} from {ob.name}")
            for area in context.window.screen.areas:
                area.tag_redraw()
            return {"FINISHED"}
        return {"PASS_THROUGH"}


class MAX_OT_mtl_reset_slots(Operator):
    """Reset Material Editor Slots"""
    bl_idname = "max.mtl_reset_slots"
    bl_label = "Reset Material Editor Slots"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        ensure_slots(context.scene)
        for i, slot in enumerate(state(context).slots):
            slot.material = None
        state(context).active = 0
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

def _icon_value(name):
    return bpy.types.UILayout.bl_rna.functions["prop"].parameters["icon"].enum_items[name].value


class _MtlPanel:
    bl_space_type = "NODE_EDITOR"
    bl_region_type = "UI"
    bl_category = "Material Editor"

    @classmethod
    def poll(cls, context):
        sp = context.space_data
        return sp is not None and getattr(sp, "tree_type", "") == "ShaderNodeTree"


class MAX_MT_mtl_material(Menu):
    bl_label = "Material"
    bl_idname = "MAX_MT_mtl_material"

    def draw(self, context):
        lay = self.layout
        lay.operator_context = "INVOKE_DEFAULT"
        lay.operator("max.mtl_get", text="Get Material...")
        lay.operator("max.mtl_pick", text="Pick from Object")
        lay.operator("max.mtl_assign", text="Assign to Selection")
        lay.operator("max.mtl_reset", text="Reset Map/Mtl to Default Settings")
        lay.operator("max.mtl_make_unique", text="Make Material Copy")
        lay.operator("max.mtl_put_library", text="Put to Library")
        lay.separator()
        lay.operator("max.mtl_select_by", text="Select by Material")


class MAX_MT_mtl_options(Menu):
    bl_label = "Options"
    bl_idname = "MAX_MT_mtl_options"

    def draw(self, context):
        lay = self.layout
        lay.props_enum(state(context), "visible")
        mat = active_material(context)
        if mat:
            lay.separator()
            lay.prop(mat, "use_preview_world", text="Background (World)")


class MAX_MT_mtl_utilities(Menu):
    bl_label = "Utilities"
    bl_idname = "MAX_MT_mtl_utilities"

    def draw(self, context):
        lay = self.layout
        lay.operator("max.mtl_reset_slots")
        lay.operator("max.relink_textures", text="Relink Missing Bitmaps...")
        lay.operator("outliner.orphans_purge", text="Clean Unused Materials").do_recursive = True


class MAX_PT_mtl_editor(_MtlPanel, Panel):
    bl_label = "Material Editor"
    bl_options = {"HIDE_HEADER"}

    def draw(self, context):
        lay = self.layout
        scene = context.scene
        st = state(context)
        # menu bar: Modes  Material  Navigation  Options  Utilities
        row = lay.row(align=True)
        row.emboss = "PULLDOWN_MENU"            # text menus like Max's menu bar
        row.menu("MAX_MT_mtl_material", text="Material")
        row.menu("MAX_MT_mtl_options", text="Options")
        row.menu("MAX_MT_mtl_utilities", text="Utils")

        if len(st.slots) < NUM_SLOTS:
            lay.operator("max.mtl_slot", text="Open Material Editor", icon="MATERIAL").index = 0
            return

        count = int(st.visible)
        cols = {6: 3, 15: 5, 24: 6}[count]
        width = context.region.width / max(context.preferences.system.ui_scale, 0.5)
        icon_scale = max(2.0, min(5.0, (width - 60) / cols / 22))

        split = lay.split(factor=0.86)
        grid = split.grid_flow(row_major=True, columns=cols, even_columns=True, align=True)
        for i in range(count):
            mat = st.slots[i].material
            cell = grid.box() if i == st.active else grid.column()
            if mat is not None:
                cell.template_icon(icon_value=mat.preview.icon_id if mat.preview else 0, scale=icon_scale)
            else:
                cell.template_icon(icon_value=_icon_value("SHADING_SOLID"), scale=icon_scale)
            # "hot" material (Max's white corner triangles): used by something besides
            # the editor itself (its slot references and the fake user)
            refs = sum(1 for sl in st.slots if sl.material == mat) if mat is not None else 0
            hot = mat is not None and mat.users - refs - (1 if mat.use_fake_user else 0) > 0
            btn = cell.row(align=True)
            btn.scale_y = 0.7
            btn.operator("max.mtl_slot", text=str(i + 1) + ("•" if hot else ""),
                         depress=(i == st.active), emboss=(i == st.active)).index = i

        # right-hand toolbar
        tools = split.column(align=True)
        mat = active_material(context)
        if mat is not None:
            tools.prop(mat, "preview_render_type", text="", expand=True, icon_only=True)
        tools.separator()
        tools.operator("max.mtl_select_by", text="", icon="RESTRICT_SELECT_OFF")
        tools.menu("MAX_MT_mtl_options", text="", icon="PREFERENCES")

        # bottom toolbar
        row = lay.row(align=True)
        row.operator("max.mtl_get", text="", icon="FILEBROWSER")
        row.operator("max.mtl_assign", text="", icon="MATERIAL")
        row.operator("max.mtl_reset", text="", icon="X")
        row.operator("max.mtl_make_unique", text="", icon="DUPLICATE")
        row.operator("max.mtl_put_library", text="", icon="ASSET_MANAGER")
        if mat is not None:
            row.prop(mat, "pass_index", text="ID")
        row.operator("max.mtl_show_in_viewport", text="", icon="TEXTURE")

        # name / type row
        if mat is None:
            lay.label(text="Empty slot: click it to create a material")
            return
        row = lay.row(align=True)
        row.operator("max.mtl_pick", text="", icon="EYEDROPPER")
        row.prop(mat, "name", text="")
        kind = "VRayMtl" if mat.get("max_vray") else {"PHYSICAL": "Physical"}.get(
            mat.get("max_type", "STANDARD"), "Standard")
        sub = row.row(align=True)
        sub.ui_units_x = 4.2
        sub.operator_menu_enum("max.mtl_set_type", "kind", text=kind)


def _mat_poll(context, need_standard=False):
    if not _MtlPanel.poll(context):
        return False
    st = state(context)
    if len(st.slots) < NUM_SLOTS:
        return False
    mat = active_material(context)
    if mat is None:
        return False
    if need_standard and mat.get("max_vray"):
        return False
    return True


class MAX_PT_mtl_shader_basic(_MtlPanel, Panel):
    bl_label = "Shader Basic Parameters"
    bl_parent_id = "MAX_PT_mtl_editor"

    @classmethod
    def poll(cls, context):
        return _mat_poll(context, need_standard=True)

    def draw(self, context):
        mat = active_material(context)
        lay = self.layout
        lay.prop(mat.max_std, "shader", text="")
        row = lay.row(align=True)
        row.prop(mat.max_std, "wire", toggle=True)
        row.prop(mat, "max_two_sided", toggle=True)
        row.prop(mat.max_std, "faceted", toggle=True)


def _map_button(layout, mat, channel):
    """Small square map button (like Max's): M = has a map, blank = none."""
    n = map_node(mat, channel)
    row = layout.row(align=True)
    row.ui_units_x = 1.2 if (n is None or n.image is None) else 2.2
    if n is not None and n.image is not None:
        row.operator("max.mtl_load_map", text="M").channel = channel
        row.operator("max.mtl_clear_map", text="", icon="X").channel = channel
    else:
        row.operator("max.mtl_load_map", text="").channel = channel


class MAX_PT_mtl_blinn(_MtlPanel, Panel):
    bl_label = " "
    bl_parent_id = "MAX_PT_mtl_editor"

    @classmethod
    def poll(cls, context):
        return _mat_poll(context, need_standard=True)

    def draw_header(self, context):
        mat = active_material(context)
        name = dict((k, n) for k, n, _ in SHADERS).get(mat.max_std.shader, "Blinn") if mat else "Blinn"
        self.layout.label(text=f"{name} Basic Parameters")

    def draw(self, context):
        mat = active_material(context)
        lay = self.layout

        def row_with_label(col, text, icon="NONE"):
            sp = col.split(factor=0.42, align=True)
            sp.label(text=text, icon=icon)
            return sp.row(align=True)

        col = lay.column(align=True)
        r = row_with_label(col, "Ambient")
        r.prop(mat, "max_diffuse", text="")
        r.label(text="", icon="BLANK1")
        r = row_with_label(col, "Diffuse")
        r.prop(mat, "max_diffuse", text="")
        _map_button(r, mat, "DIFFUSE")
        r = row_with_label(col, "Specular")
        r.prop(mat, "max_specular", text="")
        _map_button(r, mat, "SPECULAR_COLOR")
        col.separator()
        sp = col.split(factor=0.42, align=True)
        sp.prop(mat.max_std, "self_illum_color_on", text="Self-Illum")
        r = sp.row(align=True)
        if mat.max_std.self_illum_color_on:
            r.prop(mat.max_std, "self_illum_color", text="")
        else:
            r.prop(mat.max_std, "self_illum_amount", text="")
        _map_button(r, mat, "SELF_ILLUM")
        r = row_with_label(col, "Opacity")
        r.prop(mat, "max_opacity", text="")
        _map_button(r, mat, "OPACITY")

        lay.label(text="Specular Highlights")
        col = lay.column(align=True)
        r = row_with_label(col, "Level")
        r.prop(mat, "max_spec_level", text="")
        _map_button(r, mat, "SPECULAR_LEVEL")
        r = row_with_label(col, "Gloss")
        r.prop(mat, "max_glossiness", text="")
        _map_button(r, mat, "GLOSSINESS")
        r = row_with_label(col, "Soften")
        r.prop(mat.max_std, "soften", text="")
        r.label(text="", icon="BLANK1")


class MAX_PT_mtl_vray(_MtlPanel, Panel):
    bl_label = "Basic Parameters (VRayMtl)"
    bl_parent_id = "MAX_PT_mtl_editor"

    @classmethod
    def poll(cls, context):
        mat = active_material(context) if _MtlPanel.poll(context) and len(state(context).slots) >= NUM_SLOTS else None
        return mat is not None and bool(mat.get("max_vray"))

    def draw(self, context):
        from . import vray
        vray.draw_vraymtl(self.layout, active_material(context))


class MAX_PT_mtl_extended(_MtlPanel, Panel):
    bl_label = "Extended Parameters"
    bl_parent_id = "MAX_PT_mtl_editor"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        return _mat_poll(context)

    def draw(self, context):
        mat = active_material(context)
        col = self.layout.column(align=True)
        col.use_property_split = True
        col.use_property_decorate = False
        col.prop(mat, "max_ior")
        col.prop(mat, "use_backface_culling", text="Backface Cull")
        try:
            col.prop(mat, "surface_render_method", text="Transparency")
        except Exception:
            pass
        col.prop(mat, "pass_index", text="Material ID")


class MAX_PT_mtl_maps(_MtlPanel, Panel):
    bl_label = "Maps"
    bl_parent_id = "MAX_PT_mtl_editor"

    @classmethod
    def poll(cls, context):
        return _mat_poll(context)

    def draw(self, context):
        mat = active_material(context)
        lay = self.layout
        col = lay.column(align=True)
        short = {"AMBIENT": "Ambient", "DIFFUSE": "Diffuse", "SPECULAR_COLOR": "Spec Color",
                 "SPECULAR_LEVEL": "Spec Level", "GLOSSINESS": "Glossiness", "SELF_ILLUM": "Self-Illum",
                 "OPACITY": "Opacity", "FILTER": "Filter", "BUMP": "Bump", "REFLECTION": "Reflection",
                 "REFRACTION": "Refraction", "DISPLACEMENT": "Displace"}
        for key, label, _sock, _c in MAP_CHANNELS:
            n = map_node(mat, key)
            r = col.row(align=True)
            sp = r.split(factor=0.52, align=True)
            left = sp.row(align=True)
            if n is not None:
                left.prop(n, "mute", text="", invert_checkbox=True)
            else:
                left.label(text="", icon="CHECKBOX_DEHLT")
            left.label(text=short[key])
            right = sp.row(align=True)
            if key == "BUMP":
                amt = right.row(align=True)
                amt.ui_units_x = 2.5
                amt.prop(mat.max_std, "bump_amount", text="")
            name = n.image.name if (n is not None and n.image) else "None"
            right.operator("max.mtl_load_map", text=name).channel = key
            if n is not None:
                right.operator("max.mtl_clear_map", text="", icon="X").channel = key


classes = (MaxStdMaterial, MaxMtlSlot, MaxMtlEditorState,
           MAX_OT_mtl_slot, MAX_OT_mtl_get, MAX_OT_mtl_assign, MAX_OT_mtl_reset, MAX_OT_mtl_make_unique,
           MAX_OT_mtl_put_library, MAX_OT_mtl_select_by, MAX_OT_mtl_show_in_viewport, MAX_OT_mtl_set_type,
           MAX_OT_mtl_load_map, MAX_OT_mtl_clear_map, MAX_OT_mtl_pick, MAX_OT_mtl_reset_slots,
           MAX_MT_mtl_material, MAX_MT_mtl_options, MAX_MT_mtl_utilities,
           MAX_PT_mtl_editor, MAX_PT_mtl_shader_basic, MAX_PT_mtl_blinn, MAX_PT_mtl_vray,
           MAX_PT_mtl_extended, MAX_PT_mtl_maps)


def register_props():
    bpy.types.Material.max_std = PointerProperty(type=MaxStdMaterial)
    bpy.types.Scene.max_mtl_editor = PointerProperty(type=MaxMtlEditorState)
    for name, prop in MATERIAL_PROPS.items():
        setattr(bpy.types.Material, name, prop)


def unregister_props():
    for name in MATERIAL_PROPS:
        if hasattr(bpy.types.Material, name):
            delattr(bpy.types.Material, name)
    del bpy.types.Scene.max_mtl_editor
    del bpy.types.Material.max_std
