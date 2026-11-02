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
