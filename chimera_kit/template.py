"""Human base models from a template mesh: the MakeHuman light proxies
(01 Low, 741 vertices; 02 Base, 1,591 vertices; CC0), fitted to the skeleton.

Every bone of the template's skeleton is carried onto the creature's bone of
the same name: moved to its head, turned to its direction, stretched to its
length and scaled in girth. A vertex follows its bones by its skin weights, so
the joints blend. The template's eye and mouth openings are closed with quads.
Data: templates/human.json, made by tools/make_templates.py.
"""
import json
import os

from mathutils import Matrix, Vector

LEVELS = {"LOW": "01 Low", "BASE": "02 Base"}
_cache = {}

# The creature's chain, root to tip: a bone it lacks hands its share to the one before it.
SPINE = ["pelvis", "spine.01", "spine.02", "spine.03", "neck", "head"]
LIMBS = [["clavicle.{s}", "arm.{s}", "forearm.{s}", "hand.{s}"],
         ["leg.01.{s}.upper", "leg.01.{s}.lower", "leg.01.{s}.foot", "toe.{s}"]]
DIGITS = ["thumb", "index", "middle", "ring", "pinky"]
NEEDED = ["pelvis", "neck", "head", "arm.L", "arm.R", "forearm.L", "forearm.R", "hand.L", "hand.R",
          "leg.01.L.upper", "leg.01.L.lower", "leg.01.L.foot",
          "leg.01.R.upper", "leg.01.R.lower", "leg.01.R.foot"]


def data():
    if "human" not in _cache:
        path = os.path.join(os.path.dirname(__file__), "templates", "human.json")
        with open(path, encoding="utf-8") as f:
            _cache["human"] = json.load(f)
    return _cache["human"]


def fits(arm):
    """A two-legged, upright creature with arms: the human template can dress it."""
    bones = arm.data.bones
    if any(name not in bones for name in NEEDED) or "leg.02.L.upper" in bones:
        return False
    spine = bones["pelvis"]
    neck = bones["neck"].head_local
    return (neck - spine.head_local).normalized().z > .7


def chains():
    out = [SPINE]
    for s in "LR":
        out.extend([[b.format(s=s) for b in chain] for chain in LIMBS])
        for digit in DIGITS:
            out.append(["hand." + s] + ["%s.0%d.%s" % (digit, n, s) for n in (1, 2, 3)])
    return out


def stand_in(name, present, parent_of):
    """The creature's bone that takes over a template bone it does not have."""
    while name not in present:
        name = parent_of.get(name)
        if name is None:
            return None
    return name


def build(arm, level, thickness=1.0, limbs=1.0):
    """Verts, quads and weights of the template at this level, fitted to the skeleton."""
    d = data()
    lv = d["levels"][level]
    bones = arm.data.bones
    present = {b.name for b in bones if b.use_deform}
    parent_of = {}
    for chain in chains():
        for a, b in zip(chain, chain[1:]):
            parent_of[b] = a
    parent_of["clavicle.L"] = parent_of["clavicle.R"] = "spine.03"
    # Template segments, a missing bone's length handed to the bone before it in the chain.
    segments = {name: [Vector(h), Vector(t)] for name, (h, t) in d["segments"].items()}
    for chain in chains():
        last = None
        for name in chain:
            if name in present and name in segments:
                last = name
            elif last is not None and name in segments and name not in present and name not in ("clavicle.L", "clavicle.R"):
                if not any(n in present for n in chain[chain.index(name) + 1:]):
                    continue    # the end of a chain (no fingers): the hand keeps its own length
                segments[last][1] = segments[name][1]
    # A clavicle the creature lacks: its template length goes nowhere, the arm starts at the shoulder.
    # Girth follows the creature's height from ankle to the top of the head over the template's.
    template_points = [Vector(v) for v in lv["verts"]]
    top_t, ankle_t = segments["head"][1].z, segments["leg.01.L.foot"][0].z
    top_c, ankle_c = bones["head"].tail_local.z, bones["leg.01.L.foot"].head_local.z
    girth = max(1e-6, (top_c - ankle_c) / max(1e-6, top_t - ankle_t))
    transforms = {}
    # The trunk moves as one piece, from the bottom of the pelvis to the top of the chest:
    # the template's spine is divided at other heights than the creature's, and bone by
    # bone the chest would be stretched in one place and squeezed in the next.
    trunk = [n for n in SPINE[:4] if n in present and n in segments]
    top = trunk[-1]
    whole_t = (segments[trunk[0]][0], segments[top][1])
    whole_c = (bones[trunk[0]].head_local.copy(), bones[top].tail_local.copy())
    for name, (h_t, t_t) in segments.items():
        if name not in present:
            continue
        bone = bones[name]
        h_c, t_c = bone.head_local.copy(), bone.tail_local.copy()
        if name in trunk:
            (h_t, t_t), (h_c, t_c) = whole_t, whole_c
        d_t, d_c = t_t - h_t, t_c - h_c
        if d_t.length < 1e-6 or d_c.length < 1e-6:
            continue
        u = d_t.normalized()
        g = girth * thickness * (limbs if name not in SPINE else 1.0)
        along = d_c.length / d_t.length
        if name == "head" or name.startswith(tuple(DIGITS)) or name.startswith(("hand.", "toe.")) or name.endswith(".foot"):
            # The head, hands and feet keep their proportions: scaled, never stretched.
            g = along = girth * thickness
        stretch = Matrix.Identity(3) * g + _outer(u, u) * (along - g)
        turn = u.rotation_difference(d_c.normalized()).to_matrix()
        transforms[name] = (h_t, h_c, turn @ stretch)
    names = d["bones"]
    verts, weights = [], []
    for p, table in zip(template_points, lv["weights"]):
        moved = Vector((0, 0, 0))
        total = 0.0
        out = {}
        for index, w in table:
            name = stand_in(names[index], present, parent_of)
            if name is None:
                continue
            out[name] = out.get(name, 0.0) + w
        for name, w in out.items():
            # A bone with no segment of its own (rare) moves with the nearest one that has.
            key = name
            while key not in transforms and key in parent_of:
                key = parent_of[key]
            if key not in transforms:
                key = "pelvis"
            h_t, h_c, m = transforms[key]
            moved += (h_c + m @ (p - h_t)) * w
            total += w
        verts.append(moved / total if total > 0 else p.copy())
        weights.append({n: w / sum(out.values()) for n, w in out.items()} if out else {"pelvis": 1.0})
    # Soles on the ground: the template's feet sit a little differently under the ankle,
    # so each foot is lowered (or raised) onto z = 0, fading out up the shin to the knee.
    for s in "LR":
        foot, toe, shin = "leg.01.%s.foot" % s, "toe.%s" % s, "leg.01.%s.lower" % s
        own = [i for i, t in enumerate(weights) if t.get(foot, 0) + t.get(toe, 0) > .5]
        if not own or shin not in bones:
            continue
        sole = min(verts[i].z for i in own)
        if abs(sole) < 1e-4:
            continue
        knee, ankle = bones[shin].head_local.z, bones[shin].tail_local.z
        for v, t in zip(verts, weights):
            share = t.get(foot, 0) + t.get(toe, 0)
            if t.get(shin):
                share += t[shin] * max(0.0, min(1.0, (knee - v.z) / max(1e-6, knee - ankle)))
            v.z -= sole * min(1.0, share)
    quads = [tuple(q) for q in lv["quads"]]
    quads += close_openings(verts, quads, weights)
    return verts, quads, weights


def _outer(a, b):
    return Matrix([[a[i] * b[j] for j in range(3)] for i in range(3)])


def close_openings(verts, quads, weights):
    """Close every open loop (the eyes and mouth) with quads fanned from one corner."""
    edges = set()
    for q in quads:
        for a, b in zip(q, q[1:] + q[:1]):
            edges.add((a, b))
    # A boundary edge has no twin running the other way. Walking each one backwards
    # gives the loop in the order that makes the new faces wind like their neighbours.
    nxt = {b: a for (a, b) in edges if (b, a) not in edges}
    out, seen = [], set()
    for start in list(nxt):
        if start in seen:
            continue
        loop = [start]
        seen.add(start)
        while nxt.get(loop[-1]) is not None and nxt[loop[-1]] not in seen:
            loop.append(nxt[loop[-1]])
            seen.add(loop[-1])
        n = len(loop)
        if n < 4 or n % 2:
            continue        # an odd opening stays open
        # Closed like a zip from one corner to the other (the far ends of the opening's
        # long axis): rungs across a slit of a mouth or an eye, not slivers fanned from one point.
        centre = sum((verts[i] for i in loop), Vector()) / n
        far = max(range(n), key=lambda k: (verts[loop[k]] - centre).length)
        loop = loop[far:] + loop[:far]
        for k in range(n // 2 - 1):
            out.append((loop[k], loop[k + 1], loop[n - 2 - k], loop[(n - 1 - k) % n]))
    return out
