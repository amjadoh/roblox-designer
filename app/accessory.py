"""إكسسوار صلب (نظارة وجه) كمجسم واحد مغلق + خامة ≤2048، بتصدير glTF.
الحدود مأخوذة من صفحة Rigid Accessory Specifications الرسمية (قُرئت بتاريخ 2026-10-31):
≤4000 مثلث، مجسم واحد، مغلق بلا ثقوب، حجم Face للـClassic = 3×2×2 ستد، خامة ≤2048×2048.
نقطة التثبيت FaceFrontAttachment لا تُستورد مع الملف؛ تُضاف في Studio عبر Accessory Fitting Tool."""
import io
import numpy as np
from PIL import Image
from .generate import hex2rgb

LIMITS = {"max_tris": 4000, "face_classic_whd": (3.0, 2.0, 2.0), "max_texture": 2048}


def _tm():
    import trimesh
    return trimesh


def _box(w, h, d, pos, rot_z=0.0, uv=(0.25, 0.5)):
    trimesh = _tm()
    m = trimesh.creation.box(extents=(w, h, d))
    if rot_z: m.apply_transform(trimesh.transformations.rotation_matrix(rot_z, [0, 0, 1]))
    m.apply_translation(pos)
    return m, np.tile(np.array(uv), (len(m.vertices), 1))


def build_glasses(frame_hex="#111116", lens_hex="#D71920"):
    """نظارة هندسية حادة. الإحداثيات بالستد، مركزها نقطة التثبيت."""
    parts = [
        _box(1.15, 0.62, 0.14, (-0.68, 0.0, 0.0), rot_z=0.10, uv=(0.75, 0.5)),   # عدسة يمين
        _box(1.15, 0.62, 0.14, (0.68, 0.0, 0.0), rot_z=-0.10, uv=(0.75, 0.5)),   # عدسة يسار
        _box(2.80, 0.16, 0.20, (0.0, 0.40, 0.0)),                                # عارضة علوية
        _box(0.34, 0.14, 0.18, (0.0, 0.10, 0.0)),                                # جسر
        _box(0.14, 0.16, 1.60, (-1.40, 0.30, -0.80)),                            # ذراع
        _box(0.14, 0.16, 1.60, (1.40, 0.30, -0.80)),
    ]
    trimesh = _tm()
    verts, faces, uvs, off = [], [], [], 0
    for m, uv in parts:
        verts.append(m.vertices); faces.append(m.faces + off); uvs.append(uv); off += len(m.vertices)
    mesh = trimesh.Trimesh(np.vstack(verts), np.vstack(faces), process=False)
    uv = np.vstack(uvs)
    tex = Image.new("RGB", (256, 256), hex2rgb(frame_hex))
    tex.paste(hex2rgb(lens_hex), (128, 0, 256, 256))
    mesh.visual = trimesh.visual.TextureVisuals(uv=uv, material=trimesh.visual.material.PBRMaterial(
        baseColorTexture=tex, metallicFactor=0.0, roughnessFactor=0.8))
    return mesh, tex


def checks(mesh, tex):
    out = []
    def add(i, rule, ok, ev): out.append({"id": i, "rule": rule, "status": "passed" if ok else "failed", "evidence": ev})
    tris = len(mesh.faces)
    add("acc_tris", f"≤{LIMITS['max_tris']} مثلث", tris <= LIMITS["max_tris"], f"{tris} مثلث")
    bodies = mesh.split(only_watertight=False)
    wt = all(b.is_watertight for b in bodies)
    add("acc_watertight", "كل الأجسام مغلقة بلا ثقوب", wt, f"{len(bodies)} جسم، watertight={wt}")
    ext = mesh.bounds[1] - mesh.bounds[0]; lim = LIMITS["face_classic_whd"]
    add("acc_size_face_classic", "الحجم ضمن Face للـClassic (3×2×2 ستد)",
        ext[0] <= lim[0] and ext[1] <= lim[1] and ext[2] <= lim[2], f"{[round(float(v), 2) for v in ext]} ستد")
    add("acc_texture", "الخامة ≤2048×2048", max(tex.size) <= LIMITS["max_texture"], f"{tex.size}")
    add("acc_single_mesh", "مجسم واحد", True, "ملف glTF بمجسم واحد")
    out.append({"id": "acc_attachment", "rule": "FaceFrontAttachment على سطح الرأس", "status": "not_run",
                "evidence": "لا تُستورد النقطة مع الملف؛ تُضاف بـAccessory Fitting Tool في Studio"})
    out.append({"id": "acc_orientation_scale", "rule": "الاتجاه والمقياس بعد الاستيراد (Importer Rig Scale: Default)", "status": "not_run",
                "evidence": "لم يُختبر الاستيراد في Studio؛ اتجاه الأمام ومقياس الوحدة غير مثبتين"})
    return out


def export_glasses(frame_hex="#111116", lens_hex="#D71920"):
    mesh, tex = build_glasses(frame_hex, lens_hex)
    glb = mesh.export(file_type="glb")
    b = io.BytesIO(); tex.save(b, "PNG")
    return {"glb": glb, "texture": b.getvalue(), "checks": checks(mesh, tex), "tris": len(mesh.faces)}
