"""Viewport labels ([+] [Perspective] [Standard] [Default Shading]) and random object colors."""

import blf
import bpy
from bpy.app.handlers import persistent
from mathutils import Vector

_handle = None

AXES = (
    ((0, 0, 1), "Top"), ((0, 0, -1), "Bottom"), ((0, -1, 0), "Front"),
    ((0, 1, 0), "Back"), ((1, 0, 0), "Right"), ((-1, 0, 0), "Left"),
)

SHADING = {"WIREFRAME": "Wireframe", "SOLID": "Default Shading",
           "MATERIAL": "High Quality", "RENDERED": "ActiveShade"}


def view_name(context, rv3d):
    if rv3d.view_perspective == "CAMERA":
        cam = context.scene.camera
        return cam.name if cam else "Camera"
    if rv3d.is_perspective:
        return "Perspective"
    d = rv3d.view_rotation @ Vector((0, 0, 1))
    for vec, name in AXES:
        if d.dot(Vector(vec)) > 0.9999:
            return name
    return "Orthographic"


def _draw():
    context = bpy.context
    space = context.space_data
    ws = context.workspace
    if space.overlay.show_text and not (ws and ws.name == "3ds Max"):
        return   # Blender's own view name is showing here; don't draw over it
    from . import get_prefs
    p = get_prefs()
    if p is not None and not p.show_labels:
        return
    region, rv3d, area = context.region, context.region_data, context.area
    if region is None or rv3d is None or area is None:
        return
    scale = context.preferences.system.ui_scale
    x = 8 * scale
    # Skip the toolbar if it overlaps this (left-most) region
    if region.x <= area.x + 2:
        for r in area.regions:
            if r.type == "TOOLS" and r.width > 1 and space.show_region_toolbar:
                x += r.width
    top = region.height
    if region.y + region.height >= area.y + area.height - 2:
        for r in area.regions:
            if r.type in {"HEADER", "TOOL_HEADER"} and r.height > 1 and r.y >= region.y + region.height // 2:
                top -= r.height
    y = top - 18 * scale
    shade = SHADING.get(space.shading.type, "")
    if space.shading.type in {"SOLID", "MATERIAL"} and space.overlay.show_wireframes:
        shade = "Edged Faces"
    text = f"[+] [{view_name(context, rv3d)}] [Standard] [{shade}]"
    font = 0
    blf.size(font, 10.5 * scale)
    blf.enable(font, blf.SHADOW)
    blf.shadow(font, 3, 0, 0, 0, 0.8)
    blf.color(font, 0.80, 0.80, 0.80, 1.0)
    blf.position(font, x, y, 0)
    blf.draw(font, text)
    blf.disable(font, blf.SHADOW)


_last_count = [-1]


@persistent
def color_new_objects(scene, depsgraph):
    """Give new objects a random 3ds Max color. Runs after every edit, so it
    returns immediately unless the number of objects changed."""
    n = len(bpy.data.objects)
    if n == _last_count[0]:
        return
    grew = n > _last_count[0] >= 0
    _last_count[0] = n
    if not grew:
        return
    from . import get_prefs
    p = get_prefs()
    if p is None or not p.random_colors:
        return
    from .create import random_color
    for upd in depsgraph.updates:
        idb = upd.id
        if not isinstance(idb, bpy.types.Object):
            continue
        ob = idb.original
        if ob.type in {"MESH", "CURVE", "FONT", "SURFACE", "META"} and tuple(ob.color) == (1.0, 1.0, 1.0, 1.0) \
                and not ob.get("max_keep_color"):
            try:
                ob.color = random_color()
                ob["max_keep_color"] = 1
            except Exception:
                pass


@persistent
def on_load(*_args):
    _last_count[0] = -1
    from .operators import unlock_max_workspace_quads
    unlock_max_workspace_quads()


def register():
    global _handle
    if _handle is None:
        _handle = bpy.types.SpaceView3D.draw_handler_add(_draw, (), "WINDOW", "POST_PIXEL")
    if color_new_objects not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(color_new_objects)
    if on_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(on_load)


def unregister():
    global _handle
    if _handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_handle, "WINDOW")
        _handle = None
    if color_new_objects in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(color_new_objects)
    if on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(on_load)
