"""3ds Max default hotkeys, registered in Blender's add-on keyconfig.

Add-on keymap items take priority over Blender's defaults, and they are removed
cleanly when the add-on (or the "3ds Max Hotkeys" preference) is disabled.
"""

import bpy

_registered = []


def K(idname, key, value="PRESS", ctrl=False, shift=False, alt=False, **props):
    return (idname, key, value, ctrl, shift, alt, props)


# Active in every viewport mode (registered in 3D View + each mode keymap, because
# Blender's mode keymaps (Object Mode, Mesh, ...) are checked before "3D View").
VIEWPORT = [
    # Main toolbar tools
    K("wm.tool_set_by_id", "Q", name="builtin.select_box"),
    K("wm.tool_set_by_id", "W", name="builtin.move"),
    K("wm.tool_set_by_id", "E", name="builtin.rotate"),
    K("wm.tool_set_by_id", "R", name="builtin.scale"),
    # Selection
    K("max.select_all", "A", ctrl=True, action="SELECT"),
    K("max.select_all", "D", ctrl=True, action="DESELECT"),
    K("max.select_all", "I", ctrl=True, action="INVERT"),
    K("max.select_by_name", "H"),
    K("view3d.select", "LEFTMOUSE", "CLICK", ctrl=True, extend=True),
    K("view3d.select", "LEFTMOUSE", "CLICK", alt=True, deselect=True),
    K("max.delete", "DEL"),
    # Sub-object levels
    K("max.subobject", "ONE", level=1),
    K("max.subobject", "TWO", level=2),
    K("max.subobject", "THREE", level=3),
    K("max.subobject", "FOUR", level=4),
    K("max.subobject", "FIVE", level=5),
    K("max.subobject", "SIX", level=0),
    # Views
    K("max.set_view", "T", view="TOP"),
    K("max.set_view", "B", view="BOTTOM"),
    K("max.set_view", "F", view="FRONT"),
    K("max.set_view", "K", view="BACK"),
    K("max.set_view", "L", view="LEFT"),
    K("max.set_view", "P", view="PERSP"),
    K("max.set_view", "U", view="ORTHO"),
    K("max.set_view", "C", view="CAMERA"),
    K("max.zoom_extents", "Z"),
    K("view3d.view_all", "Z", ctrl=True, shift=True, center=False),
    K("view3d.zoom_border", "W", ctrl=True),
    K("max.toggle_quad", "W", alt=True),
    K("view3d.localview", "Q", alt=True),
    # Display toggles
    K("max.toggle", "F3", what="WIREFRAME"),
    K("max.toggle", "F4", what="EDGED_FACES"),
    K("max.toggle", "X", alt=True, what="SEE_THROUGH"),
    K("max.toggle", "G", what="GRID"),
    K("max.toggle", "X", what="GIZMO"),
    K("max.toggle", "SEVEN", what="STATS"),
    K("max.toggle", "S", what="SNAP"),
    K("max.toggle", "A", what="ANGLE_SNAP"),
    K("max.toggle", "N", what="AUTOKEY"),
    K("max.expert_mode", "X", ctrl=True),
    K("max.adaptive_degradation", "O"),
    K("max.transform_typein", "F12"),
    # Editors
    K("max.open_editor", "M", editor="MATERIAL"),
    K("max.open_editor", "EIGHT", editor="ENVIRONMENT"),
    # Quad menus
    K("wm.call_menu", "RIGHTMOUSE", name="MAX_MT_quad"),
    K("wm.call_menu", "RIGHTMOUSE", ctrl=True, name="MAX_MT_quad_modeling"),
]

# Navigation lives only in "3D View"
NAVIGATION = [
    K("view3d.move", "MIDDLEMOUSE"),
    K("view3d.rotate", "MIDDLEMOUSE", alt=True),
    K("view3d.zoom", "MIDDLEMOUSE", ctrl=True, alt=True),
]

OBJECT_MODE = [
    K("max.clone", "V", ctrl=True),
    K("max.camera_from_view", "C", ctrl=True),
    K("max.set_key", "K"),
    K("object.select_hierarchy", "PAGE_UP", direction="PARENT", extend=False),
    K("object.select_hierarchy", "PAGE_DOWN", direction="CHILD", extend=False),
]

# Edit Poly hotkeys
MESH = [
    K("view3d.edit_mesh_extrude_move_normal", "E", shift=True),
    K("max.edit_poly", "E", ctrl=True, shift=True, op="CONNECT"),
    K("max.edit_poly", "C", ctrl=True, shift=True, op="CHAMFER"),
    K("mesh.knife_tool", "C", alt=True),
    K("max.edit_poly", "BACK_SPACE", op="REMOVE"),
    K("max.edit_poly", "BACK_SPACE", ctrl=True, op="REMOVE_WITH_VERTS"),
    K("max.edit_poly", "L", alt=True, op="LOOP"),
    K("max.edit_poly", "R", alt=True, op="RING"),
    K("mesh.select_more", "PAGE_UP", ctrl=True),
    K("mesh.select_less", "PAGE_DOWN", ctrl=True),
]

FRAMES = [
    K("screen.frame_offset", "COMMA", delta=-1),
    K("screen.frame_offset", "PERIOD", delta=1),
    K("screen.frame_jump", "HOME", end=False),
    K("screen.frame_jump", "END", end=True),
    K("screen.animation_play", "SLASH"),
]

WINDOW = [
    K("max.open_editor", "F10", editor="RENDER_SETUP"),
    K("render.render", "Q", shift=True, use_viewport=True),
    K("render.render", "F9", use_viewport=True),
]


def _groups():
    modes = ("Object Mode", "Mesh", "Curve")
    yield "3D View", "VIEW_3D", "WINDOW", VIEWPORT + NAVIGATION
    for m in modes:
        yield m, "EMPTY", "WINDOW", VIEWPORT
    yield "Object Mode", "EMPTY", "WINDOW", OBJECT_MODE
    yield "Mesh", "EMPTY", "WINDOW", MESH
    yield "Frames", "EMPTY", "WINDOW", FRAMES
    yield "Window", "EMPTY", "WINDOW", WINDOW


def register_keymaps():
    if _registered:
        return
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon if wm else None
    if kc is None:  # background mode
        return
    for name, space, region, items in _groups():
        km = kc.keymaps.new(name=name, space_type=space, region_type=region)
        for idname, key, value, ctrl, shift, alt, props in items:
            kmi = km.keymap_items.new(idname, key, value, ctrl=ctrl, shift=shift, alt=alt)
            for k, v in props.items():
                try:
                    setattr(kmi.properties, k, v)
                except Exception as exc:
                    print(f"[3ds Maxxed] keymap {idname}.{k}: {exc}")
            _registered.append((km, kmi))


def unregister_keymaps():
    for km, kmi in _registered:
        try:
            km.keymap_items.remove(kmi)
        except Exception:
            pass
    _registered.clear()


def keymap_enabled():
    return bool(_registered)
