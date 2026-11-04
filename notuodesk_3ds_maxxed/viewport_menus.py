"""Clickable 3ds Max viewport labels: [+]  [Perspective]  [Standard]  [Default Shading]."""

import bpy
from bpy.props import EnumProperty, StringProperty
from bpy.types import Menu, Operator

from . import overlay
from .operators import find_view3d

LABEL_MENUS = {
    "PLUS": "MAX_MT_vp_general",
    "VIEW": "MAX_MT_vp_point_of_view",
    "QUALITY": "MAX_MT_vp_quality",
    "SHADING": "MAX_MT_vp_shading",
}


class MAX_OT_viewport_label(Operator):
    """Click a viewport label to open its menu (like 3ds Max)"""
    bl_idname = "max.viewport_label"
    bl_label = "Viewport Label Menu"
    bl_options = {"INTERNAL"}

    def invoke(self, context, event):
        region = context.region
        if region is None or region.type != "WINDOW":
            return {"PASS_THROUGH"}
        key = overlay.hit_label(region, event.mouse_region_x, event.mouse_region_y)
        if key is None:
            return {"PASS_THROUGH"}          # normal click: selection etc. continue
        bpy.ops.wm.call_menu(name=LABEL_MENUS[key])
        return {"FINISHED"}


def _space(context):
    sp = context.space_data
    if sp is not None and sp.type == "VIEW_3D":
        return sp
    area, _ = find_view3d(context)
    return area.spaces.active if area else None


SHADING_MODES = [
    ("DEFAULT", "Default Shading", "Solid shading with object colors"),
    ("MAPS", "Shaded Materials with Maps", "Solid shading showing textures"),
    ("MATERIALS", "Shaded Materials", "Solid shading with material colors"),
    ("FLAT", "Flat Color", "Unlit flat colors"),
    ("CLAY", "Clay", "Single clay color, ideal for checking forms"),
    ("WIRE", "Wireframe Override", "Wireframe (F3)"),
    ("REALISTIC", "Realistic", "Material preview with lighting (EEVEE)"),
    ("ACTIVESHADE", "ActiveShade", "Interactive render in the viewport"),
]


class MAX_OT_viewport_shading(Operator):
    """Set the viewport shading style"""
    bl_idname = "max.viewport_shading"
    bl_label = "Viewport Shading"

    mode: EnumProperty(items=SHADING_MODES)

    @classmethod
    def description(cls, context, props):
        return dict((k, d) for k, _, d in SHADING_MODES).get(props.mode, "")

    def execute(self, context):
        sp = _space(context)
        if sp is None:
            return {"CANCELLED"}
        sh = sp.shading
        m = self.mode
        if m == "WIRE":
            sh.type = "WIREFRAME"
            return {"FINISHED"}
        if m == "REALISTIC":
            sh.type = "MATERIAL"
            return {"FINISHED"}
        if m == "ACTIVESHADE":
            sh.type = "RENDERED"
            return {"FINISHED"}
        sh.type = "SOLID"
        sh.light = "FLAT" if m == "FLAT" else "STUDIO"
        if m == "CLAY":
            sh.color_type = "SINGLE"
            sh.single_color = (0.75, 0.55, 0.42)
        elif m == "MAPS":
            sh.color_type = "TEXTURE"
        elif m == "MATERIALS":
            sh.color_type = "MATERIAL"
        else:
            sh.color_type = "OBJECT"
        return {"FINISHED"}


class MAX_OT_viewport_quality(Operator):
    """Viewport rendering level: Standard, Performance or High Quality"""
    bl_idname = "max.viewport_quality"
    bl_label = "Viewport Quality"

    level: EnumProperty(items=[("STANDARD", "Standard", "Solid shading, full detail"),
                               ("PERFORMANCE", "Performance", "Simplified (Adaptive Degradation)"),
                               ("HIGH", "High Quality", "Lit materials with shadows and AO")])

    def execute(self, context):
        sp = _space(context)
        r = context.scene.render
        if self.level == "PERFORMANCE":
            if not r.use_simplify:
                bpy.ops.max.adaptive_degradation()
        else:
            r.use_simplify = False
        if sp is not None:
            if self.level == "HIGH":
                sp.shading.type = "MATERIAL"
            elif sp.shading.type in {"MATERIAL", "RENDERED"}:
                sp.shading.type = "SOLID"
        return {"FINISHED"}


class MAX_OT_view_camera(Operator):
    """Look through this camera"""
    bl_idname = "max.view_camera"
    bl_label = "View Camera"

    name: StringProperty()

    def execute(self, context):
        cam = context.scene.objects.get(self.name)
        if cam is None:
            return {"CANCELLED"}
        context.scene.camera = cam
        rv3d = context.region_data
        if rv3d is None:
            area, region = find_view3d(context)
            rv3d = region.data if region else None
        if rv3d is not None:
            rv3d.lock_rotation = False
            rv3d.view_perspective = "CAMERA"
        return {"FINISHED"}


class MAX_MT_vp_general(Menu):
    bl_label = "[+]"
    bl_idname = "MAX_MT_vp_general"

    def draw(self, context):
        lay = self.layout
        sp = _space(context)
        lay.operator("max.toggle_quad", text="Maximize Viewport          Alt+W")
        lay.operator("max.expert_mode", text="Expert Mode                   Ctrl+X")
        lay.separator()
        lay.operator("max.toggle", text="Show Grids                        G").what = "GRID"
        if sp:
            lay.prop(sp, "show_gizmo_navigate", text="ViewCube / Navigation Gizmo")
            lay.prop(sp, "show_gizmo", text="Transform Gizmo                X")
            lay.prop(sp.overlay, "show_stats", text="xView: Show Statistics       7")
            lay.prop(sp.overlay, "show_axis_x", text="World Axis X")
        lay.separator()
        lay.operator("max.adaptive_degradation", text="Adaptive Degradation          O")
        lay.popover("VIEW3D_PT_overlay", text="Configure Viewports...")


class MAX_MT_vp_point_of_view(Menu):
    bl_label = "Point of View"
    bl_idname = "MAX_MT_vp_point_of_view"

    def draw(self, context):
        lay = self.layout
        for v, label, key in (("PERSP", "Perspective", "P"), ("ORTHO", "Orthographic", "U"),
                              (None, None, None),
                              ("TOP", "Top", "T"), ("BOTTOM", "Bottom", "B"), ("FRONT", "Front", "F"),
                              ("BACK", "Back", "K"), ("LEFT", "Left", "L"), ("RIGHT", "Right", "")):
            if v is None:
                lay.separator()
                continue
            lay.operator("max.set_view", text=f"{label:<18}{key}").view = v
        cams = [o for o in context.scene.objects if o.type == "CAMERA"]
        lay.separator()
        if cams:
            lay.label(text="Cameras")
            for c in cams:
                lay.operator("max.view_camera", text=c.name, icon="CAMERA_DATA").name = c.name
        else:
            lay.operator("max.camera_from_view", text="Create Camera From View   Ctrl+C")
        sp = _space(context)
        if sp:
            lay.separator()
            lay.prop(sp, "lens", text="Viewport Lens (mm)")


class MAX_MT_vp_quality(Menu):
    bl_label = "Viewport Quality"
    bl_idname = "MAX_MT_vp_quality"

    def draw(self, context):
        lay = self.layout
        current = overlay.quality_label(context, _space(context)) if _space(context) else ""
        for key, label in (("HIGH", "High Quality"), ("STANDARD", "Standard"), ("PERFORMANCE", "Performance")):
            lay.operator("max.viewport_quality", text=label,
                         icon="CHECKMARK" if current == label else "BLANK1").level = key
        sp = _space(context)
        if sp:
            lay.separator()
            lay.label(text="Lighting and Shadows")
            lay.prop(sp.shading, "show_shadows", text="Shadows")
            lay.prop(sp.shading, "show_cavity", text="Ambient Occlusion")
            lay.prop(sp.shading, "show_specular_highlight", text="Highlights")


class MAX_MT_vp_shading(Menu):
    bl_label = "Viewport Shading"
    bl_idname = "MAX_MT_vp_shading"

    def draw(self, context):
        lay = self.layout
        sp = _space(context)
        current = overlay.shading_label(context, sp) if sp else ""
        for key, label, _ in SHADING_MODES:
            if key == "WIRE":
                lay.separator()
            lay.operator("max.viewport_shading", text=label,
                         icon="CHECKMARK" if current == label else "BLANK1").mode = key
        lay.separator()
        if sp:
            lay.prop(sp.overlay, "show_wireframes", text="Edged Faces                     F4")
            lay.prop(sp.shading, "show_xray", text="See-Through                     Alt+X")
            lay.prop(sp.shading, "show_backface_culling", text="Backface Cull")
            lay.separator()
            lay.popover("VIEW3D_PT_shading", text="Lighting & Shading Settings...")


classes = (MAX_OT_viewport_label, MAX_OT_viewport_shading, MAX_OT_viewport_quality, MAX_OT_view_camera,
           MAX_MT_vp_general, MAX_MT_vp_point_of_view, MAX_MT_vp_quality, MAX_MT_vp_shading)
