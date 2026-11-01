"""ينزّل Three.js إلى app/static/vendor إن لم يكن موجودًا (للمعاينة ثلاثية الأبعاد). فشله لا يوقف التطبيق."""
import os, urllib.request

V = "0.160.0"
DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "vendor")
SRC = {
    "three.module.js": f"https://cdn.jsdelivr.net/npm/three@{V}/build/three.module.js",
    "OrbitControls.js": f"https://cdn.jsdelivr.net/npm/three@{V}/examples/jsm/controls/OrbitControls.js",
}


def main():
    os.makedirs(DIR, exist_ok=True)
    for name, url in SRC.items():
        p = os.path.join(DIR, name)
        if os.path.exists(p) and os.path.getsize(p) > 1000:
            continue
        try:
            data = urllib.request.urlopen(url, timeout=30).read().decode("utf-8")
            if name == "OrbitControls.js":
                data = data.replace("from 'three'", "from './three.module.js'").replace('from "three"', "from './three.module.js'")
            open(p, "w", encoding="utf-8").write(data)
            print("downloaded", name)
        except Exception as e:
            print("3D preview library not downloaded (flat view still works):", name, e)


if __name__ == "__main__":
    main()
