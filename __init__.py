# SPDX-License-Identifier: GPL-3.0-or-later
"""Kontur — человеческая болванка для Blender: тело, скелет, веса."""

bl_info = {
    "name": "Kontur",
    "author": "Kontur",
    "version": (1, 0, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > Kontur",
    "description": "Человеческая болванка: пропорции, цельный меш и скелет",
    "category": "Rigging",
}

import json

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, PointerProperty
from bpy.types import Operator, Panel, PropertyGroup
from mathutils import Vector

from . import shape

_LOCK = {"on": False}


def _params_from(settings):
    return {
        "height": settings.height,
        "head": settings.head,
        "shoulders": settings.shoulders,
        "chest": settings.chest,
        "waist": settings.waist,
        "hips": settings.hips,
        "arms": settings.arms,
        "legs": settings.legs,
        "bust": settings.bust,
        "pose": settings.pose,
        "fingers": settings.fingers,
    }


def _apply_dict(settings, data):
    _LOCK["on"] = True
    try:
        for key in ("height", "head", "shoulders", "chest", "waist", "hips", "arms", "legs", "bust"):
            if key in data:
                setattr(settings, key, float(data[key]))
        if data.get("pose") in {"A", "T"}:
            settings.pose = data["pose"]
        if "fingers" in data:
            settings.fingers = bool(data["fingers"])
    finally:
        _LOCK["on"] = False


def _preset_update(self, _context):
    if _LOCK["on"] or self.preset == "custom":
        return
    _apply_dict(self, shape.PRESETS[self.preset])


def _touch(_self, _context):
    if _LOCK["on"]:
        return
    if _self.preset != "custom":
        _LOCK["on"] = True
        try:
            _self.preset = "custom"
        finally:
            _LOCK["on"] = False


class KonturProps(PropertyGroup):
    preset: EnumProperty(
        name="Пресет",
        items=(
            ("male", "Мужчина", ""),
            ("female", "Женщина", ""),
            ("teen", "Подросток", ""),
            ("sturdy", "Крепкий", ""),
            ("custom", "Свои", ""),
        ),
        default="male",
        update=_preset_update,
    )
    height: FloatProperty(name="Рост", default=1.78, min=1.35, max=2.15, unit="LENGTH", update=_touch)
    head: FloatProperty(name="Голова", default=1.0, min=0.75, max=1.35, update=_touch)
    shoulders: FloatProperty(name="Плечи", default=1.08, min=0.7, max=1.35, update=_touch)
    chest: FloatProperty(name="Грудная клетка", default=1.06, min=0.7, max=1.4, update=_touch)
    waist: FloatProperty(name="Талия", default=0.94, min=0.6, max=1.4, update=_touch)
    hips: FloatProperty(name="Бёдра", default=0.96, min=0.7, max=1.4, update=_touch)
    bust: FloatProperty(name="Грудь", default=0.08, min=0.0, max=1.0, update=_touch)
    arms: FloatProperty(name="Руки", default=1.0, min=0.75, max=1.25, update=_touch)
    legs: FloatProperty(name="Ноги", default=1.0, min=0.75, max=1.25, update=_touch)
    pose: EnumProperty(
        name="Поза",
        items=(("A", "А-поза", "Руки опущены"), ("T", "Т-поза", "Руки в стороны")),
        default="A",
    )
    fingers: BoolProperty(name="Пальцы", default=True, description="Отдельные пальцы. Выключи — варежка, проще лепить")
    fuse: BoolProperty(
        name="Сплавить",
        default=True,
        description="Один цельный меш. Без этого части пересекаются и их можно разделить в редактировании",
    )
    detail: EnumProperty(
        name="Сетка",
        items=(
            ("draft", "Крупно", "Быстрее. Пальцы могут слипнуться"),
            ("fingers", "Пальцы", "Мельче, пальцы остаются отдельными"),
        ),
        default="fingers",
    )


class KONTUR_OT_create(Operator):
    bl_idname = "kontur.human_create"
    bl_label = "Создать человека"
    bl_description = "Болванка на 3D-курсоре: меш, глаза, скелет и веса"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT"

    def execute(self, context):
        settings = context.scene.kontur_human
        try:
            root = _spawn(context, _params_from(settings), settings.fuse, settings.detail, None)
        except Exception as exc:
            self.report({"ERROR"}, f"Kontur: {exc}")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Kontur: {root.name}, рост {settings.height:.2f} м")
        return {"FINISHED"}


class KONTUR_OT_rebuild(Operator):
    bl_idname = "kontur.human_rebuild"
    bl_label = "Пересобрать"
    bl_description = "Заново собирает выбранного человека текущими ползунками. Лепка и поза сбросятся"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT" and _find_root(context.active_object) is not None

    def execute(self, context):
        root = _find_root(context.active_object)
        settings = context.scene.kontur_human
        loc = root.matrix_world.translation.copy()
        name = root.name
        _delete_character(root)
        try:
            new_root = _spawn(context, _params_from(settings), settings.fuse, settings.detail, loc)
        except Exception as exc:
            self.report({"ERROR"}, f"Kontur: {exc}")
            return {"CANCELLED"}
        new_root.name = name
        self.report({"INFO"}, "Kontur: пересобрано. Правки сетки сброшены")
        return {"FINISHED"}


class KONTUR_OT_load(Operator):
    bl_idname = "kontur.human_load"
    bl_label = "Взять пропорции"
    bl_description = "Поставить ползунки с выбранного человека"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _find_root(context.active_object) is not None

    def execute(self, context):
        root = _find_root(context.active_object)
        raw = root.get("kontur_params")
        if not raw:
            self.report({"WARNING"}, "У этого человека нет сохранённых пропорций")
            return {"CANCELLED"}
        _apply_dict(context.scene.kontur_human, json.loads(raw))
        context.scene.kontur_human.preset = "custom"
        return {"FINISHED"}


class KONTUR_PT_human(Panel):
    bl_label = "Человек"
    bl_idname = "KONTUR_PT_human"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Kontur"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.kontur_human
        layout.use_property_split = True
        layout.use_property_decorate = False
        col = layout.column(align=True)
        col.prop(settings, "preset")
        col.separator()
        for key in ("height", "head", "shoulders", "chest", "waist", "hips", "bust", "arms", "legs"):
            col.prop(settings, key)
        col.separator()
        col.prop(settings, "pose")
        col.prop(settings, "fingers")
        col.prop(settings, "fuse")
        if settings.fuse:
            col.prop(settings, "detail")
        col.separator()
        col.operator("kontur.human_create", icon="USER")
        col.operator("kontur.human_rebuild", icon="FILE_REFRESH")
        col.operator("kontur.human_load", icon="EYEDROPPER")
        note = layout.column()
        note.scale_y = 0.85
        note.label(text="Стоит на 3D-курсоре.")
        note.label(text="Пересборка стирает лепку и позу.")
        note.label(text="Крутить кости: поза, ось X.")


def _find_root(obj):
    found = None
    while obj is not None:
        if obj.type == "ARMATURE" and obj.get("kontur_id"):
            found = obj
        obj = obj.parent
    return found


def _collection(context):
    col = bpy.data.collections.get("Kontur")
    if col is None:
        col = bpy.data.collections.new("Kontur")
        context.scene.collection.children.link(col)
    return col


def _link(context, obj):
    col = _collection(context)
    if obj.name not in col.objects:
        col.objects.link(obj)
    return obj


def _mesh_object(name, verts, faces):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    mesh.shade_smooth()
    return bpy.data.objects.new(name, mesh)


def _join(parts):
    verts = []
    faces = []
    for part in parts:
        shift = len(verts)
        verts.extend(part.verts)
        faces.extend(tuple(i + shift for i in face) for face in part.faces)
    return verts, faces


def _material(name, color, roughness):
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        bsdf = next((node for node in mat.node_tree.nodes if node.type == "BSDF_PRINCIPLED"), None)
        if bsdf:
            color_in = bsdf.inputs.get("Base Color")
            rough_in = bsdf.inputs.get("Roughness")
            if color_in:
                color_in.default_value = (*color, 1.0)
            if rough_in:
                rough_in.default_value = roughness
        mat.diffuse_color = (*color, 1.0)
    return mat


def _voxel_size(height, detail):
    if detail == "draft":
        return max(0.009, height * 0.0065)
    return max(0.0055, height * 0.0036)


def _fuse(context, obj, voxel):
    mod = obj.modifiers.new("KonturFuse", "REMESH")
    mod.mode = "VOXEL"
    mod.voxel_size = voxel
    mod.adaptivity = 0.0
    mod.use_smooth_shade = True
    context.view_layer.objects.active = obj
    obj.select_set(True)
    context.view_layer.update()
    depsgraph = context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(depsgraph)
    fresh = bpy.data.meshes.new_from_object(evaluated, preserve_all_data_layers=False, depsgraph=depsgraph)
    obj.modifiers.clear()
    old = obj.data
    obj.data = fresh
    if old.users == 0:
        bpy.data.meshes.remove(old)
    fresh.shade_smooth()


def _armature(name, bones):
    data = bpy.data.armatures.new(name)
    data.display_type = "OCTAHEDRAL"
    obj = bpy.data.objects.new(name, data)
    obj.show_in_front = True
    return obj, data


def _build_bones(context, arm_obj, bones):
    context.view_layer.objects.active = arm_obj
    bpy.ops.object.mode_set(mode="EDIT")
    edit = {}
    for bone in bones:
        edit_bone = arm_obj.data.edit_bones.new(bone.name)
        edit_bone.head = Vector(bone.head)
        edit_bone.tail = Vector(bone.tail)
        if (Vector(bone.tail) - Vector(bone.head)).length < 1e-4:
            edit_bone.tail = Vector(bone.head) + Vector((0.0, 0.0, 0.02))
        edit_bone.use_deform = bone.deform
        edit[bone.name] = edit_bone
    for bone in bones:
        edit_bone = edit[bone.name]
        if bone.parent and bone.parent in edit:
            edit_bone.parent = edit[bone.parent]
            edit_bone.use_connect = bone.connect
        try:
            edit_bone.align_roll(Vector(bone.roll))
        except Exception:
            pass
    bpy.ops.object.mode_set(mode="OBJECT")
    context.view_layer.update()
    for pose_bone in arm_obj.pose.bones:
        pose_bone.rotation_mode = "XYZ"


def _bind_auto(context, body, arm):
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    body.select_set(True)
    arm.select_set(True)
    context.view_layer.objects.active = arm
    bpy.ops.object.parent_set(type="ARMATURE_AUTO")


def _dist_segment(point, head, tail):
    ab = tail - head
    length2 = ab.length_squared
    if length2 < 1e-8:
        return (point - head).length
    t = max(0.0, min(1.0, (point - head).dot(ab) / length2))
    return (point - (head + ab * t)).length


def _bind_fallback(body, arm):
    if body.parent != arm:
        body.parent = arm
        body.matrix_parent_inverse = arm.matrix_world.inverted() @ body.matrix_world
    modifier = next((m for m in body.modifiers if m.type == "ARMATURE"), None)
    if modifier is None:
        modifier = body.modifiers.new("Armature", "ARMATURE")
    modifier.object = arm
    groups = {}
    for pose_bone in arm.pose.bones:
        if pose_bone.bone.use_deform:
            groups[pose_bone.name] = body.vertex_groups.new(name=pose_bone.name)
    segments = []
    for pose_bone in arm.pose.bones:
        if not pose_bone.bone.use_deform:
            continue
        head = Vector(pose_bone.bone.head_local)
        tail = Vector(pose_bone.bone.tail_local)
        segments.append((pose_bone.name, head, tail, max(0.035, (tail - head).length * 0.42)))
    for vertex in body.data.vertices:
        point = vertex.co
        scored = []
        for name, head, tail, sigma in segments:
            dist = _dist_segment(point, head, tail)
            scored.append((pow(2.718281828, -(dist * dist) / (sigma * sigma)), name))
        scored.sort(reverse=True)
        top = scored[:4]
        total = sum(weight for weight, _name in top) or 1.0
        for weight, name in top:
            share = weight / total
            if share > 0.03:
                groups[name].add([vertex.index], share, "REPLACE")


def _unweighted(body):
    if not body.vertex_groups:
        return True
    for vertex in body.data.vertices:
        if not vertex.groups:
            return True
    return False


def _eyes(human, location):
    mat = _material("KonturEye", (0.08, 0.07, 0.06), 0.22)
    objects = []
    for index, (center, radius) in enumerate(human.eyes):
        verts, faces = shape.sphere(center, radius, nu=12, nv=8)
        eye = _mesh_object("KonturEye", verts, faces)
        eye.data.materials.append(mat)
        eye.location = location
        group = eye.vertex_groups.new(name="head")
        group.add(list(range(len(eye.data.vertices))), 1.0, "REPLACE")
        objects.append(eye)
    return objects


def _delete_character(root):
    pending = [root]
    seen = set()
    while pending:
        obj = pending.pop()
        if obj is None or obj.name in seen:
            continue
        seen.add(obj.name)
        pending.extend(list(obj.children))
    for obj in list(seen):
        block = bpy.data.objects.get(obj)
        if block is None:
            continue
        data = block.data
        bpy.data.objects.remove(block, do_unlink=True)
        if data and getattr(data, "users", 1) == 0:
            if isinstance(data, bpy.types.Mesh):
                bpy.data.meshes.remove(data)
            elif isinstance(data, bpy.types.Armature):
                bpy.data.armatures.remove(data)


def _spawn(context, params, fuse, detail, location):
    human = shape.build_human(params)
    verts, faces = _join(human.parts)
    if not verts or not faces:
        raise RuntimeError("пустая сетка")
    body = _mesh_object("KonturBody", verts, faces)
    body.data.materials.append(_material("KonturClay", (0.80, 0.67, 0.56), 0.52))
    _link(context, body)
    if location is None:
        location = context.scene.cursor.location.copy()
    body.location = location
    fused = False
    if fuse:
        try:
            _fuse(context, body, _voxel_size(params["height"], detail))
            fused = True
        except Exception:
            body.modifiers.clear()

    arm, _data = _armature("Kontur", human.bones)
    _link(context, arm)
    arm.location = location
    _build_bones(context, arm, human.bones)

    try:
        _bind_auto(context, body, arm)
        if _unweighted(body):
            raise RuntimeError("пустые веса")
    except Exception:
        _bind_fallback(body, arm)

    for eye in _eyes(human, location):
        _link(context, eye)
        modifier = eye.modifiers.new("Armature", "ARMATURE")
        modifier.object = arm
        context.view_layer.update()
        world = eye.matrix_world.copy()
        eye.parent = arm
        eye.matrix_world = world

    arm["kontur_id"] = 1
    arm["kontur_params"] = json.dumps(params)
    arm["kontur_fused"] = fused
    bpy.ops.object.select_all(action="DESELECT")
    body.select_set(True)
    arm.select_set(True)
    context.view_layer.objects.active = arm
    return arm


CLASSES = (
    KonturProps,
    KONTUR_OT_create,
    KONTUR_OT_rebuild,
    KONTUR_OT_load,
    KONTUR_PT_human,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.kontur_human = PointerProperty(type=KonturProps)


def unregister():
    del bpy.types.Scene.kontur_human
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
