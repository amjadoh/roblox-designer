import copy, importlib, os, sys, tempfile, io, zipfile
os.environ["RD_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fastapi.testclient import TestClient
from PIL import Image
from app import layout, commands
from app.main import app, rev_info, rdir
from app.generate import sha256, DEFAULT_SPEC, render_shirt

c = TestClient(app)

def new(): return c.post("/api/projects").json()

def cmd(pid, text, sel=None):
    r = c.post(f"/api/projects/{pid}/command", json={"text": text, "selection": sel}).json(); return r

def test_first_set_files():
    p = new(); n = p["current"]["n"]
    for g in ("shirt", "pants"):
        assert Image.open(os.path.join(rdir(p["id"], n), g + ".png")).size == (585, 559)
    v = {x["id"]: x["status"] for x in c.get(f"/api/projects/{p['id']}/validation/{n}").json()}
    assert all(v[k] == "passed" for k in v if k.endswith(("png_size", "psd_reopen", "regions_opaque", "no_stray")))
    assert v["studio_import"] == "not_run" and v["template_layout"] == "not_run"

def test_color_edit_keeps_pants_locked():
    p = new(); pid = p["id"]
    r = cmd(pid, "ثبّت البنطلون"); assert r["ok"]
    a = r["state"]["current"]; r2 = cmd(pid, "خفف الأحمر"); assert r2["ok"], r2
    b = r2["state"]["current"]
    assert a["pants_sha"] == b["pants_sha"] and a["shirt_sha"] != b["shirt_sha"]
    assert b["spec"]["shirt"]["colors"]["accent"] != a["spec"]["shirt"]["colors"]["accent"]
    ok = c.get(f"/api/projects/{pid}/validation/{b['n']}").json()
    assert {x["id"]: x["status"] for x in ok}["locks_respected"] == "passed"

def test_pocket_scale_and_selection():
    p = new(); pid = p["id"]
    r = cmd(pid, "كبّر الجيب"); assert r["state"]["current"]["spec"]["shirt"]["pocket_scale"] == 1.25
    h = c.post(f"/api/projects/{pid}/hit/{r['state']['current']['n']}", json={"x": 295, "y": 170, "garment": "shirt"}).json()
    assert h["element"] == "pocket"
    r = cmd(pid, "صغّر هذا", sel=h); assert r["state"]["current"]["spec"]["shirt"]["pocket_scale"] < 1.25

def test_undo_and_restore_keeps_history():
    p = new(); pid = p["id"]; cmd(pid, "كبّر الشعار")
    r = cmd(pid, "تراجع"); assert r["ok"]
    cur = r["state"]["current"]; assert cur["spec"]["shirt"]["emblem_scale"] == 1.0 and len(r["state"]["revisions"]) == 3

def test_unknown_command_is_honest():
    p = new(); r = cmd(p["id"], "اعمل لي سيارة طائرة"); assert not r["ok"] and "ما فهمت" in r["reply"]

def test_psd_layers_edit_and_reexport():
    from psd_tools import PSDImage
    p = new(); d = rdir(p["id"], p["current"]["n"])
    psd = PSDImage.open(os.path.join(d, "shirt.psd")); names = [l.name for l in psd]
    assert "base" in names and "pocket" in names
    for l in psd:
        if l.name == "pocket": l.visible = False
    out = os.path.join(d, "edited.png"); psd.composite().save(out)
    assert sha256(out) != sha256(os.path.join(d, "shirt.png"))

def test_template_validator_self_consistent():
    # يحاكي القالب الرسمي: خلفية رمادية معتمة والأوجه مربعات ملوّنة
    img = Image.new("RGB", layout.SIZE, (227, 227, 227))
    for (_, _), (x, y, w, h) in layout.REGIONS.items(): img.paste((220, 40, 40), (x, y, x + w, y + h))
    assert layout.validate_template(img)["status"] == "passed"
    bad = Image.new("RGB", layout.SIZE, (227, 227, 227)); assert layout.validate_template(bad)["status"] == "failed"
    shifted = Image.new("RGB", layout.SIZE, (227, 227, 227))
    for (_, _), (x, y, w, h) in layout.REGIONS.items(): shifted.paste((220, 40, 40), (x + 20, y + 20, x + w + 20, y + h + 20))
    assert layout.validate_template(shifted)["status"] == "failed"


def test_limb_layout_matches_official_r15():
    # من القالب الرسمي: اليمين L B R F و U/D فوق F عند x=217؛ اليسار F L B R و U/D عند x=308
    R = layout.REGIONS
    assert [R[("limbA", f)][0] for f in ("left", "back", "right", "front")] == [19, 85, 151, 217]
    assert [R[("limbB", f)][0] for f in ("front", "left", "back", "right")] == [308, 374, 440, 506]
    assert R[("limbA", "up")][:2] == (217, 289) and R[("limbA", "down")][:2] == (217, 485)
    assert R[("limbB", "up")][:2] == (308, 289) and R[("limbB", "down")][:2] == (308, 485)

def test_package_contents_and_no_overclaim():
    p = new(); n = p["current"]["n"]
    z = zipfile.ZipFile(io.BytesIO(c.get(f"/api/projects/{p['id']}/package/{n}").content)); names = z.namelist()
    for need in ("upload/classic-shirt.png", "upload/classic-pants.png", "source/classic-shirt.psd", "manifest.json", "reports/technical-validation.json", "README_AR.md"):
        assert need in names
    import json
    t = json.loads(z.read("reports/technical-validation.json"))
    assert t["technical_status"] == "files_generated" and t["rights_status"] == "unchecked" and t["publishing_status"] == "not_uploaded"

def test_approve_is_design_only():
    p = new(); r = c.post(f"/api/projects/{p['id']}/approve/{p['current']['n']}").json(); assert r["ok"] and "لا رفع" in r["note"]

def test_accessory_in_package_with_honest_status():
    import json
    p = new(); z = zipfile.ZipFile(io.BytesIO(c.get(f"/api/projects/{p['id']}/package/{p['current']['n']}").content))
    assert "accessory/glasses.glb" in z.namelist()
    a = {x["id"]: x["status"] for x in json.loads(z.read("reports/accessory-validation.json"))}
    assert a["acc_tris"] == a["acc_watertight"] == "passed" and a["acc_attachment"] == "not_run"


def test_design_cli_patch_validation():
    import pytest
    from app.design_cli import validate_patch, merge, SpecError
    ok = {"shirt": {"colors": {"base": "#C2A878"}, "pattern": "chevron", "pocket_scale": 1.2}, "locked": ["pants"]}
    validate_patch(ok)
    m = merge(DEFAULT_SPEC, ok)
    assert m["shirt"]["colors"] == {"base": "#C2A878", "accent": DEFAULT_SPEC["shirt"]["colors"]["accent"]}
    for bad in ({"shirt": {"wings": True}}, {"shirt": {"pocket_scale": 5}}, {"shirt": {"colors": {"base": "red"}}},
                {"pants": {"pattern": "logo"}}, {"locked": ["hat"]}, {"shirt": {"pocket": "yes"}}):
        with pytest.raises(SpecError):
            validate_patch(bad)


def test_basic_auth_when_password_set():
    import base64
    from app import main as m
    old = m.RD_PASSWORD; m.RD_PASSWORD = "s3cret"
    try:
        assert c.get("/api/projects").status_code == 401
        bad = base64.b64encode(b"roblox:nope").decode()
        assert c.get("/api/projects", headers={"Authorization": "Basic " + bad}).status_code == 401
        good = base64.b64encode(b"roblox:s3cret").decode()
        assert c.get("/api/projects", headers={"Authorization": "Basic " + good}).status_code == 200
    finally:
        m.RD_PASSWORD = old


def test_stale_command_is_rejected_not_overwritten():
    p = new(); pid = p["id"]; base = p["current"]["n"]
    r1 = c.post(f"/api/projects/{pid}/command", json={"text": "كبّر الجيب", "base_revision": base}).json(); assert r1["ok"]
    # أمر ثاني مبني على الإصدار القديم (مثل تبويب ثاني ما تحدّث)
    r2 = c.post(f"/api/projects/{pid}/command", json={"text": "صغّر الشعار", "base_revision": base}).json()
    assert not r2["ok"] and r2.get("conflict") and "أحدث" in r2["reply"]
    assert r2["state"]["current"]["n"] == r1["state"]["current"]["n"]  # ما انكتب فوقه
    assert c.post(f"/api/projects/{pid}/restore/{base}?base_revision={base}").status_code == 409


def test_commercial_approval_blocked_until_rights_resolved():
    p = new(); pid = p["id"]; n = p["current"]["n"]
    r = c.post(f"/api/projects/{pid}/approve/{n}?kind=commercial").json()
    assert not r["ok"] and r["blocked"] and len(r["blockers"]) >= 1
    assert r["state"]["approved_rev"] is None  # ما انحفظ أي اعتماد


def test_undo_and_reopen_restores_same_files():
    from app import main as m
    p = new(); pid = p["id"]; first = p["current"]
    cmd(pid, "خفف الأحمر"); r = cmd(pid, "تراجع"); assert r["ok"]
    # "إعادة فتح": قراءة جديدة من القاعدة والملفات بدون أي حالة في الذاكرة
    again = m.project_state(pid)["current"]
    assert again["spec"] == first["spec"]
    assert again["shirt_sha"] == first["shirt_sha"] and again["pants_sha"] == first["pants_sha"]


def test_psd_edit_saved_and_reopened():
    from psd_tools import PSDImage
    p = new(); d = rdir(p["id"], p["current"]["n"])
    psd = PSDImage.open(os.path.join(d, "shirt.psd"))
    for l in psd:
        if l.name == "pocket": l.visible = False
    out = os.path.join(d, "edited.psd"); psd.save(out)
    re = PSDImage.open(out)
    assert {l.name: l.visible for l in re}["pocket"] is False
    a = os.path.join(d, "a.png"); re.composite(force=True).save(a)
    assert sha256(a) != sha256(os.path.join(d, "shirt.png"))


def test_template_regions_endpoint_matches_layout():
    r = c.get("/api/template/regions").json()
    assert r["limbA"]["up"] == [217, 289, 64, 64] and r["limbB"]["front"] == [308, 355, 64, 128]


def test_free_request_queue_and_reply():
    from app import design_cli
    import argparse
    p = new(); pid = p["id"]
    r = c.post(f"/api/projects/{pid}/requests", json={"text": "  أبغى طقم تنين أزرق  ", "base_revision": p["current"]["n"]}).json()
    assert r["ok"] and "وصل" in r["reply"]
    lst = c.get(f"/api/projects/{pid}/requests").json()
    assert lst[0]["text"] == "أبغى طقم تنين أزرق" and lst[0]["status"] == "pending"
    design_cli.cmd_reply(argparse.Namespace(rid=r["id"], text="سويت لك طقم التنين 🐉", reject=False))
    done = c.get(f"/api/projects/{pid}/requests").json()[0]
    assert done["status"] == "done" and done["reply"].startswith("سويت") and done["reply_rev"] == p["current"]["n"]


def test_free_request_limits():
    p = new(); pid = p["id"]
    assert c.post(f"/api/projects/{pid}/requests", json={"text": "   "}).status_code == 400
    assert c.post(f"/api/projects/{pid}/requests", json={"text": "x" * 301}).status_code == 400
    for i in range(3): assert c.post(f"/api/projects/{pid}/requests", json={"text": f"طلب {i}"}).status_code == 200
    assert c.post(f"/api/projects/{pid}/requests", json={"text": "طلب رابع"}).status_code == 429


def test_library_actions_apply_and_respect_locks():
    p = new(); pid = p["id"]
    lib = c.get("/api/library").json(); assert len(lib["styles"]) >= 10 and len(lib["palettes"]) >= 10
    r = c.post(f"/api/projects/{pid}/apply", json={"action": "style", "style": "explorer"}).json()
    assert r["ok"] and r["state"]["current"]["spec"]["pants"]["cargo_pocket_scale"] == 1.3
    cmd(pid, "ثبّت البنطلون"); before = c.get(f"/api/projects/{pid}").json()["current"]
    r = c.post(f"/api/projects/{pid}/apply", json={"action": "palette", "palette": "ocean"}).json()
    after = r["state"]["current"]
    assert r["ok"] and after["pants_sha"] == before["pants_sha"] and after["shirt_sha"] != before["shirt_sha"]
    r = c.post(f"/api/projects/{pid}/apply", json={"action": "toggle", "key": "belt", "garment": "pants"}).json()
    assert not r["ok"] and "مثبّت" in r["reply"]
    r = c.post(f"/api/projects/{pid}/apply", json={"action": "color", "slot": "accent", "hex": "javascript:1"}).json()
    assert not r["ok"]
    r = c.post(f"/api/projects/{pid}/apply", json={"action": "surprise"}).json(); assert r["state"]["current"]["n"] >= 4


def test_render_is_deterministic():
    from app.generate import render_shirt
    import hashlib
    a = render_shirt(DEFAULT_SPEC["shirt"]).composite().tobytes(); b = render_shirt(DEFAULT_SPEC["shirt"]).composite().tobytes()
    assert hashlib.sha256(a).digest() == hashlib.sha256(b).digest()
