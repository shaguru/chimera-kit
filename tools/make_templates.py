"""Build chimera_kit/templates/human.json: the two MakeHuman light proxies
(01 Low: proxy741, 02 Base: male1591), fitted to the HM08 body, with skin
weights and bone landmarks in Chimera Kit's bone names.

Run with Python 3 + NumPy and internet access (GitHub), from the project folder:

    python tools/make_templates.py "G:/DEV/TESTS/parametric base model/tools/source"

The argument is the folder holding proxy741.obj/.proxy and male1591.obj/.proxy
(MakeHuman system assets, CC0). The HM08 body, its default skeleton and its
default weights are read from the pinned MakeHuman repository (CC0 assets).

Coordinates: MakeHuman is Y up, +Z front, decimetres. Blender here is Z up,
-Y front, metres: (x, y, z) -> (x, -z, y) / 10.
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from urllib.request import urlopen

import numpy as np

URL = "https://raw.githubusercontent.com/makehumancommunity/makehuman/a8bc2d54ff0ac92e78ff71431b1023eda42bf482/makehuman/data/"
ROOT = Path(__file__).resolve().parents[1]

# MakeHuman bone -> Chimera Kit bone. Face, tongue and eye bones ride the head.
SPINE = {"root": "pelvis", "pelvis": "pelvis", "spine05": "pelvis", "spine04": "pelvis",
         "spine03": "spine.01", "spine02": "spine.02", "spine01": "spine.03", "breast": "spine.03",
         "neck01": "neck", "neck02": "neck", "neck03": "neck"}
FINGERS = {"1": "thumb", "2": "index", "3": "middle", "4": "ring", "5": "pinky"}
# Where each Chimera bone lies on the HM08 skeleton: (MakeHuman bone, end) for head and tail.
SEGMENTS = {
    "pelvis": (("spine05", "head"), ("spine04", "tail")),
    "spine.01": (("spine03", "head"), ("spine03", "tail")),
    "spine.02": (("spine02", "head"), ("spine02", "tail")),
    "spine.03": (("spine01", "head"), ("spine01", "tail")),
    "neck": (("neck01", "head"), ("neck03", "tail")),
    "head": (("head", "head"), ("head", "tail")),
    "clavicle.{s}": (("clavicle.{s}", "head"), ("shoulder01.{s}", "tail")),
    "arm.{s}": (("upperarm01.{s}", "head"), ("upperarm02.{s}", "tail")),
    "forearm.{s}": (("lowerarm01.{s}", "head"), ("lowerarm02.{s}", "tail")),
    "hand.{s}": (("wrist.{s}", "head"), ("metacarpal2.{s}", "tail")),
    "leg.01.{s}.upper": (("upperleg01.{s}", "head"), ("upperleg02.{s}", "tail")),
    "leg.01.{s}.lower": (("lowerleg01.{s}", "head"), ("lowerleg02.{s}", "tail")),
    "leg.01.{s}.foot": (("foot.{s}", "head"), ("toe3-1.{s}", "head")),
    "toe.{s}": (("toe3-1.{s}", "head"), ("toe3-3.{s}", "tail")),
}
for number, finger in FINGERS.items():
    for joint in "123":
        SEGMENTS[finger + ".0" + joint + ".{s}"] = (("finger%s-%s.{s}" % (number, joint), "head"),
                                                    ("finger%s-%s.{s}" % (number, joint), "tail"))


def chimera_bone(name):
    side = name[-1] if name.endswith((".L", ".R")) else None
    base = name[:-2] if side else name
    if base in SPINE:
        return SPINE[base]
    if side is None:
        return "head"
    def sided(n):
        return n + "." + side
    if base in ("clavicle", "shoulder01"):
        return sided("clavicle")
    if base.startswith("upperarm"):
        return sided("arm")
    if base.startswith("lowerarm"):
        return sided("forearm")
    if base.startswith(("wrist", "metacarpal")):
        return sided("hand")
    match = re.match(r"finger(\d)-(\d)", base)
    if match:
        return sided(FINGERS[match.group(1)] + ".0" + match.group(2))
    if base.startswith("upperleg") or base == "pelvis":
        return "leg.01.%s.upper" % side if base != "pelvis" else "pelvis"
    if base.startswith("lowerleg"):
        return "leg.01.%s.lower" % side
    if base == "foot":
        return "leg.01.%s.foot" % side
    if base.startswith("toe"):
        return sided("toe")
    return "head"     # eyes, lids, lips, jaw, tongue, brows


def fetch(path):
    with urlopen(URL + path, timeout=60) as f:
        return f.read().decode()


def read_obj(text):
    verts, faces = [], []
    group = "body"
    groups = defaultdict(list)
    for line in text.splitlines():
        s = line.split()
        if not s:
            continue
        if s[0] == "v":
            verts.append([float(x) for x in s[1:4]])
        elif s[0] == "g":
            group = s[1]
        elif s[0] == "f":
            face = [int(x.split("/")[0]) - 1 for x in s[1:]]
            faces.append(face)
            groups[group].append(face)
    return np.array(verts), faces, groups


def to_blender(a):
    a = np.asarray(a, dtype=float)
    return np.stack([a[..., 0], -a[..., 2], a[..., 1]], axis=-1) * .1


def main(source):
    source = Path(source)
    base, _, _ = read_obj(fetch("3dobjs/base.obj"))
    skeleton = json.loads(fetch("rigs/default.mhskel"))
    raw = json.loads(fetch("rigs/default_weights.mhw"))["weights"]
    joints = {name: base[np.array(ids)].mean(axis=0) for name, ids in skeleton["joints"].items()}
    def end(bone, which):
        return joints[skeleton["bones"][bone][which]]
    segments = {}
    for pattern, ((hb, he), (tb, te)) in SEGMENTS.items():
        for s in ("L", "R") if "{s}" in pattern else (None,):
            fill = (lambda x: x.format(s=s)) if s else (lambda x: x)
            segments[fill(pattern)] = [to_blender(end(fill(hb), he)).round(5).tolist(),
                                       to_blender(end(fill(tb), te)).round(5).tolist()]
    # Weights on the HM08 body, gathered onto Chimera bones.
    bones = sorted({chimera_bone(n) for n in raw} | set(segments))
    index = {b: i for i, b in enumerate(bones)}
    weights = np.zeros((len(base), len(bones)))
    for name, pairs in raw.items():
        pairs = np.array(pairs)
        weights[pairs[:, 0].astype(int), index[chimera_bone(name)]] += pairs[:, 1]
    levels = {}
    for key, name in (("LOW", "proxy741"), ("BASE", "male1591")):
        text = (source / (name + ".proxy")).read_text(encoding="utf-8")
        _, faces, _ = read_obj((source / (name + ".obj")).read_text(encoding="utf-8"))
        table = []
        for line in text.split("verts 0")[1].strip().splitlines():
            t = line.split()
            if not t:
                continue
            if not t[0].isdigit():
                break
            row = [float(x) for x in t]
            table.append(row if len(row) == 9 else [row[0]] * 3 + [1, 0, 0, 0, 0, 0])
        table = np.array(table)
        refs, coeff = table[:, :3].astype(int), table[:, 3:6, None]
        scale = []
        for k, axis in enumerate("xyz"):
            i, j, d = re.search(axis + r"_scale (\d+) (\d+) ([\d.]+)", text).groups()
            scale.append(abs(base[int(i), k] - base[int(j), k]) / float(d))
        points = (base[refs] * coeff).sum(axis=1) + table[:, 6:] * np.array(scale)
        w = (weights[refs] * coeff).sum(axis=1)
        w = np.clip(w, 0, None)
        w /= np.maximum(w.sum(axis=1, keepdims=True), 1e-9)
        sparse = []
        for row in w:
            keep = [(int(b), round(float(x), 4)) for b, x in enumerate(row) if x > .01]
            total = sum(x for _, x in keep) or 1.0
            sparse.append([[b, round(x / total, 4)] for b, x in keep])
        assert all(len(f) == 4 for f in faces), name + " is not all quads"
        levels[key] = dict(name=name, verts=to_blender(points).round(5).tolist(), quads=faces, weights=sparse)
        print(key, name, len(points), "verts", len(faces), "quads")
    out = dict(source="MakeHuman HM08 light proxies (proxy741, male1591), CC0. See licenses/MakeHuman-CC0.md.",
               bones=bones, segments=segments, levels=levels)
    path = ROOT / "chimera_kit" / "templates" / "human.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(out, separators=(",", ":")))
    print("wrote", path, path.stat().st_size, "bytes")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ROOT / "tools" / "source")
