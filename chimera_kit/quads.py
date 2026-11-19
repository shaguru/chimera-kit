"""Quad body for Build mesh from skeleton.

The body is modelled the way a modeller would box it out:

* One eight-sided trunk runs the whole length of the creature, from the tip
  of the tail through the hips, spine and neck to the top of the head.
* Arms and legs are extruded from the trunk: a two-by-two patch of trunk faces
  is opened and its eight edges carry on as the limb. Two legs that hang
  straight down from the hips split the bottom of the trunk instead, the way
  a pair of trousers divides.
* Thin parts (fingers, toes, wings, fins, ears, antennae) are four-sided and
  are extruded from the single face nearest to where they grow.
* Every bone carries a taper: full in the belly of the muscle, tight at the
  joints. Each joint has three close loops; the length of a bone has one or two.
"""
import math
from mathutils import Vector
from . import geometry as geo

# Muscle profiles: (position along the bone, girth). Positions of the middle
# entries are also where the bone's own loops are placed.
PROFILES = {
    "thigh": ((0, 1.34), (.30, 1.28), (.72, 1.0), (1, .90)),
    "shin": ((0, .95), (.28, 1.22), (.72, .84), (1, .78)),
    "upper_arm": ((0, 1.16), (.40, 1.16), (1, .88)),
    "forearm": ((0, .94), (.25, 1.18), (.72, .82), (1, .74)),
    # Four-legged animals: a deep haunch or shoulder that narrows fast to the knee,
    # then a lean lower leg.
    "haunch": ((0, 2.1), (.30, 1.9), (.70, 1.34), (1, 1.06)),
    "gaskin": ((0, 1.30), (.25, 1.42), (.70, .94), (1, .84)),
    "plain": ((0, 1.0), (.5, 1.0), (1, 1.0)),
}
# Trunk profiles from the hips (0) to the shoulders (1): (position, width, depth, shift).
# Shift slides the section along its depth, as a fraction of that depth.
# Upright: seat pushed back, waist drawn in, chest carried forward.  + is back.
TORSO = ((0, 1.02, 1.30, .10), (.12, 1.0, 1.26, .08), (.36, .84, 1.04, .0), (.72, 1.03, 1.30, -.07), (1, 1.08, 1.02, -.02))
# Level: loin tucked up under the back, chest slung deep between the forelegs.  + is up.
BARREL = ((0, 1.0, 1.04, .0), (.30, .93, .88, .06), (.72, 1.0, 1.14, -.06), (1, .94, 1.04, -.03))
FOUR_LEGGED = False
LIMBS = 1.0
DEBUG = False


def profile_of(name):
    if name.endswith(".upper"): return "haunch" if FOUR_LEGGED else "thigh"
    if name.endswith(".lower"): return "gaskin" if FOUR_LEGGED else "shin"
    if name.startswith("arm."): return "upper_arm"
    if name.startswith("forearm."): return "forearm"
    return "plain"


def trunk_at(table, u, amount):
    """(width factor, depth factor, shift) of a trunk profile at u."""
    for (u0, w0, d0, s0), (u1, w1, d1, s1) in zip(table, table[1:]):
        if u <= u1:
            f = (u - u0) / max(u1 - u0, 1e-9)
            f = f * f * (3 - 2 * f)
            return 1 + (w0 + (w1 - w0) * f - 1) * amount, 1 + (d0 + (d1 - d0) * f - 1) * amount, (s0 + (s1 - s0) * f) * amount
    return 1 + (table[-1][1] - 1) * amount, 1 + (table[-1][2] - 1) * amount, table[-1][3] * amount


def girth_at(kind, t, amount):
    rows = PROFILES[kind]
    for (t0, g0), (t1, g1) in zip(rows, rows[1:]):
        if t <= t1:
            f = (t - t0) / max(t1 - t0, 1e-9)
            f = f * f * (3 - 2 * f)
            return 1 + (g0 + (g1 - g0) * f - 1) * amount
    return 1 + (rows[-1][1] - 1) * amount


class Part:
    """One fleshed bone."""
    def __init__(self, bone, thickness):
        self.name = bone.name
        self.head, self.tail = bone.head_local.copy(), bone.tail_local.copy()
        self.sec = tuple(v * thickness for v in bone["cs_box"])
        hint = bone.get("cs_side")
        self.hint = Vector(hint) if hint else None
        self.shift = Vector(bone["cs_offset"]) if "cs_offset" in bone.keys() else Vector((0, 0, 0))
        self.parent = None
        self.children = []
        self.length = (self.tail - self.head).length
        self.taken = False

    def radius(self, end):
        return max(self.sec[2:] if end else self.sec[:2]) * .5

    def area(self, end):
        return self.sec[2] * self.sec[3] if end else self.sec[0] * self.sec[1]


class Tube:
    def __init__(self, sides):
        self.sides = sides
        self.rings = []      # vertex indices, one list per ring
        self.centres = []    # (centre, side, front, half width, half depth) per ring
        self.grid = {}       # (ring, column) -> face index
        self.caps = []       # face indices closing an end
        self.bones = set()
        self.owner = []      # the bone each ring was placed for, or None at a joint


class Body:
    def __init__(self):
        self.verts, self.faces, self.weights = [], [], []

    def vert(self, co, weights):
        self.verts.append(Vector(co))
        self.weights.append(dict(weights))
        return len(self.verts) - 1

    def face(self, loop):
        self.faces.append(tuple(loop))
        return len(self.faces) - 1


def collect(arm, thickness):
    parts = {}
    for bone in arm.data.bones:
        if bone.use_deform and "cs_box" in bone.keys() and bone.length > 1e-6:
            parts[bone.name] = Part(bone, thickness)
    for bone in arm.data.bones:
        part = parts.get(bone.name)
        if not part:
            continue
        parent = bone.parent
        while parent and parent.name not in parts:
            parent = parent.parent
        if parent:
            part.parent = parts[parent.name]
            part.parent.children.append(part)
    return parts


def near(a, b, part, other):
    return (a - b).length < .35 * min(max(part.sec) * .5, max(other.sec) * .5) + 1e-5


def chain_from(root, backwards):
    """The run of bones one tube is lofted through: (part, reversed) pairs."""
    sequence = [(root, False)]
    root.taken = True
    current = root
    while True:
        spinal = ("spine.", "torso.", "neck", "head", "tail.")
        options = [c for c in current.children if not c.taken and near(c.head, current.tail, c, current)
                   and (c.area(False) >= .25 * current.area(True) or (c.name.startswith(spinal) and current.name.startswith(spinal + ("pelvis",))))]
        if not options:
            break
        current = max(options, key=lambda c: (c.name.startswith(spinal), c.area(False)))
        current.taken = True
        sequence.append((current, False))
    if backwards:
        # A tail leaves the hips the other way: it joins the front of the same tube.
        ahead = (root.tail - root.head).normalized()
        options = [c for c in root.children if not c.taken and near(c.head, root.head, c, root)
                   and (c.tail - c.head).normalized().dot(ahead) < .3 and c.area(False) >= .1 * root.area(False)]
        if options:
            current = max(options, key=lambda c: c.area(False))
            while current:
                current.taken = True
                sequence.insert(0, (current, True))
                following = [c for c in current.children if not c.taken and near(c.head, current.tail, c, current)]
                current = max(following, key=lambda c: c.area(False)) if following else None
    return sequence


def head_rows(forms, neck_top):
    """Sections for a head drawn as body forms: a human skull from the jaw to
    the crown, or an animal head from the back of the skull to the snout and
    on along its muzzle. Returns (stations, ears)."""
    main = next((f for f in forms if f["bone"] == "head" and not f.get("ball") and f["color"] == 0), None)
    if not main:
        return None, []
    centre = Vector(main["center"])
    sx, sy, sz = main["scale"]
    rows = []
    amount = main.get("skull", 0)
    if amount or sz >= sy * 1.15:
        for v, w, d, off in geo.skull_rows(amount, True):
            rows.append((centre + Vector((0, sy * off, sz * v)), (2 * sx * w, 2 * sy * d)))
        # A small last section rounds the crown instead of leaving it cut flat.
        top, size = rows[-1]
        rows.append((top + Vector((0, 0, sz * .09)), (size[0] * .52, size[1] * .52)))
    else:
        for v, w in ((-1, .5), (-.62, .88), (-.15, 1.0), (.35, .88), (.75, .64), (1.0, .42)):
            rows.append((centre + Vector((0, -sy * v, 0)), (2 * sx * w, 2 * sz * w)))
        muzzle = next((f for f in forms if f is not main and f["bone"] == "head" and not f.get("ball")
                       and f["color"] == 0 and f["center"][1] < centre.y - sy * .3), None)
        if muzzle:
            c = Vector(muzzle["center"])
            fx, fy, fz = muzzle["scale"]
            rows = [row for row in rows if row[0].y > c.y + fy * .2]
            rows.append((c, (2 * fx, 2 * fz)))
            rows.append((c + Vector((0, -fy * .9, 0)), (1.4 * fx, 1.4 * fz)))
    # Only what lies beyond the top of the neck: a section behind it would fold the surface back.
    onward = (centre - neck_top)
    if onward.length > 1e-6:
        onward.normalize()
        kept = [row for row in rows if (row[0] - neck_top).dot(onward) > .12 * max(sx, sy, sz)]
        rows = kept if len(kept) >= 2 else rows[-2:]
    ears = []
    for form in forms:
        fx, fy, fz = form["scale"]
        if form["bone"] == "head" and form["color"] == 1 and not form.get("ball") and fz > fx * 1.3:
            c = Vector(form["center"])
            ears.append([(c - Vector((0, 0, fz * .2)), (1.7 * fx, 1.7 * fy)), (c + Vector((0, 0, fz * .95)), (.5 * fx, .5 * fy))])
    return rows, ears


def stations_for(sequence, forms, taper, branch_parent=None):
    """Sections along a chain: dicts of pos, sec (width, depth) and weights."""
    out = []
    def add(pos, sec, weights, bone=None, t=None):
        out.append(dict(pos=Vector(pos), sec=(max(sec[0], 1e-5), max(sec[1], 1e-5)), weights=dict(weights), bone=bone, t=t,
                        hint=parts_hint.get(bone)))
    count = len(sequence)
    # A bone built in another pose (an arm lifted to a T) says which way its width runs,
    # so a palm stays flat to the floor instead of turning edge-on.
    parts_hint = {part.name: part.hint for part, _ in sequence if part.hint is not None}
    easing = None
    floor = None    # (point, direction, bone): stations of that bone must lie beyond the point
    spine = [part.name for part, _ in sequence if part.name.startswith("spine.")]
    for index, (part, flipped) in enumerate(sequence):
        before = sequence[index - 1][0] if index else branch_parent
        after = sequence[index + 1][0] if index + 1 < count else None
        # In chain order a flipped bone runs tail to head.
        head_side, tail_side = (after, before) if flipped else (before, after)
        kind = profile_of(part.name)
        w0, d0, w1, d1 = part.sec
        limb = LIMBS if part.name.startswith(("leg.", "arm.", "forearm.")) else 1.0
        upright = abs((part.tail - part.head).normalized().z) > .7
        place = spine.index(part.name) if part.name in spine else None
        table = TORSO if upright else BARREL if FOUR_LEGGED else None
        lift = Vector((0, 1, 0)) if upright else Vector((0, 0, 1))
        def shape_at(t):
            if table and place is not None:
                return trunk_at(table, (place + t) / len(spine), taper)
            if table and part.name == "pelvis":
                return trunk_at(table, 0.0, taper)
            return 1.0, 1.0, 0.0
        def section(t):
            g = girth_at(kind, t, taper) * limb
            gw, gd, _ = shape_at(t)
            return ((w0 + (w1 - w0) * t) * g * gw, (d0 + (d1 - d0) * t) * g * gd)
        def point(t):
            base = part.head + (part.tail - part.head) * t + (part.shift if t > 1e-6 else Vector((0, 0, 0)))
            shift = shape_at(t)[2]
            return base + lift * (shift * (d0 + (d1 - d0) * t)) if shift else base
        radius = max(w0, d0, w1, d1) * .5
        stops = []
        crest = None
        caps = {}       # t -> widest the chest may be there (at the shoulders)
        if part.name == "head" and not flipped and index == count - 1:
            rows, _ = head_rows(forms, part.head)
            if rows:
                if index == 0:
                    add(part.head, (w0 * .6, d0 * .6), {part.name: 1.0})
                for pos, sec in rows:
                    add(pos, sec, {part.name: 1.0})
                continue
        # Three loops at a joint: this bone's own loop sits close beside it.
        loop = .5 * radius / part.length
        backbone = part.name.startswith(("spine.", "torso.", "pelvis"))
        if backbone and part.length > 1.0 * radius:
            # A back is not a hinge: evenly spaced loops, so a chest can flow into a neck or a waist.
            number = max(1, min(4, int(part.length / (1.1 * radius))))
            stops += [((i + 1) / (number + 1), {part.name: 1.0}) for i in range(number)]
        elif part.length > 2.4 * radius:
            stops.append((loop, {part.name: .85, head_side.name: .15} if head_side else {part.name: 1.0}))
            middles = [t for t, _ in PROFILES[kind][1:-1]]
            if kind == "plain":
                # The length of a bone takes a loop or two: more only where a trunk needs them to stay round.
                trunk = part.name.startswith(("spine.", "torso.", "pelvis", "tail.", "neck"))
                spacing = (1.1 if trunk else 2.6) * radius
                number = max(0, min(4 if trunk else 1, int(part.length * (1 - 2 * loop) / spacing)))
                if part.name.startswith("neck"):
                    number = max(number, 1)   # a neck always has a loop of its own between its two ends
                middles = [(i + 1) / (number + 1) for i in range(number)]
            elif part.length < 5 * radius:
                middles = middles[:1]
            stops += [(t, {part.name: 1.0}) for t in middles if loop + .08 < t < 1 - loop - .08]
            stops.append((1 - loop, {part.name: .85, tail_side.name: .15} if tail_side else {part.name: 1.0}))
        elif part.name.startswith("neck") and part.length > 1.2 * radius:
            # A short neck still turns and nods: three loops of its own.
            stops += [(.22, {part.name: .85, head_side.name: .15} if head_side else {part.name: 1.0}),
                      (.5, {part.name: 1.0}),
                      (.78, {part.name: .85, tail_side.name: .15} if tail_side else {part.name: 1.0})]
        elif part.length > 1.0 * radius:
            stops.append((.5, {part.name: 1.0}))
        # Where an arm or leg grows from this bone, three rings sit one limb-width apart,
        # so the patch it is extruded from is the size of the limb and no bigger.
        for child in part.children:
            if child.taken or not child.name.startswith(("leg.", "arm.", "clavicle.", "clawarm.")) or part.length < 1e-6:
                continue
            along = (child.head - part.head).dot(part.tail - part.head) / part.length ** 2
            reach = 1.25 * max(child.sec[:2]) * .5 / part.length
            centre = max(reach * 1.1, min(1 - reach * 1.1, along))
            if abs((part.tail - part.head).normalized().z) > .7:
                # Upright: the three rings sit at the armpit, level with the shoulder joint
                # and over the top of the shoulder, so the arm opens from the side of the chest.
                # A shoulder near the top of the chest gets its top ring above the bone's end,
                # and the slope to the neck starts beyond it (see `crest` below).
                rt = max(child.sec[:2]) * .5 * 1.1 / part.length
                if along + rt > .86 and child.name.startswith(("arm.", "clavicle.")):
                    reach = rt
                    centre = min(along, 1.05)
                    # The top ring only just clears the ball of the shoulder and the neck starts
                    # a little above it: higher, and the shoulders read as a shrug.
                    over = rt * .75
                    wanted = [t for t in (centre - rt, centre, centre + over) if t > .03]
                    crest = max(crest or 0.0, centre + over + rt * .55)
                    # The ball of the shoulder sits at the edge of the chest and the deltoid
                    # belongs to the arm, so the chest is no wider than the shoulder joints
                    # there and narrows over them, instead of standing out as a shelf.
                    joint_at = child.tail if child.name.startswith("clavicle.") else child.head
                    across = 2 * abs(joint_at.x - point(along).x)
                    caps[round(centre, 4)] = (across * 1.02, 1.0)
                    # Over the shoulders the body is thin front to back: only the slope of the
                    # trapezius, not the depth of the ribcage, or it swells into a lump.
                    caps[round(centre + over, 4)] = (across * .80, .50)
                else:
                    centre = max(reach + .04, min(.80 - reach, along))
                    wanted = [t for t in (centre - reach, centre, centre + reach) if .03 < t < .86]
            else:
                wanted = [t for t in (centre - reach, centre, centre + reach) if .1 < t < .9]
            if not wanted:
                continue
            stops = [(t, w) for t, w in stops if all(abs(t - n) > reach * .55 for n in wanted)]
            stops += [(t, {part.name: 1.0}) for t in wanted]
            stops.sort(key=lambda stop: stop[0])
        if flipped:
            stops.reverse()
        start_t, end_t = (1.0, 0.0) if flipped else (0.0, 1.0)
        if index == 0 and branch_parent is None:
            w, d = section(start_t)
            add(point(start_t), (w * .62, d * .62), {part.name: 1.0})
        if floor is not None and floor[2] == part.name:
            stops = [(t, w) for t, w in stops if (point(t) - floor[0]).dot(floor[1]) > .3 * radius]
        for number, (t, weights) in enumerate(stops):
            sec = section(t)
            cap = caps.get(round(t, 4))
            if cap is not None:
                sec = (min(sec[0], cap[0]), sec[1] * cap[1])
            if number == 0 and easing:
                # A carried neck flows out of the chest instead of stepping down from it.
                sec = ((sec[0] + easing[0]) * .5, (sec[1] + easing[1]) * .5)
            add(point(t), sec, weights, part.name, t)
        easing = None
        if index + 1 < count:
            following, following_flipped = sequence[index + 1]
            fw = following.sec[2:] if following_flipped else following.sec[:2]
            w, d = section(end_t)
            tight = 1 - .08 * taper if kind != "plain" else 1.0
            if following.name == "head" and any(f["bone"] == "head" and not f.get("ball") and f["color"] == 0 for f in forms):
                fw = (0, 0)   # a head drawn as a form starts from the neck's own size
            joint = (max(w, fw[0]) * tight, max(d, fw[1]) * tight)
            level = abs((part.tail - part.head).normalized().z) < .7
            where = point(end_t)
            if following.name == "neck" and fw[0] > 0:
                if level:
                    joint = ((w + fw[0]) * .5, (d + fw[1]) * .5)
                    easing = joint   # a carried neck flows out of the chest
                else:
                    # Upright: the shoulders slope up to the base of the neck and stop there.
                    # The neck itself then rises as its own column, not as more slope.
                    joint = (min(w, fw[0] * 1.5), min(d, fw[1] * 1.35))
            if part.name.endswith(".lower") and following.name.endswith(".foot") and not following_flipped:
                run = following.tail - following.head
                flat = Vector((run.x, run.y, 0))
                if flat.length > 1e-6 and -run.z <= flat.length:
                    # A flat foot has a heel: the ankle section reaches back and down behind the shin.
                    back = -flat.normalized()
                    heel = max(fw) * .5
                    drop = min(where.z - heel * .55, heel * .5) if where.z > heel * .55 else 0.0
                    where = where + back * (heel * .55) - Vector((0, 0, drop * .6))
                    joint = (joint[0] * 1.05, joint[1] * 1.45)
            if crest is not None and following.name.startswith("neck"):
                # Above the shoulders: the base of the neck starts a little over the top of them.
                where = point(crest)
                floor = (where.copy(), (following.tail - following.head).normalized(), following.name)
            add(where, joint, {part.name: .5, following.name: .5})
        else:
            w, d = section(end_t)
            add(point(end_t), (w * .7, d * .7), {part.name: 1.0})
    # Two sections almost on top of each other pinch the surface into a hard line.
    # Where that happens, the joint stays and the loop beside it goes.
    i = 1
    while i < len(out) - 1:
        room = .28 * min(min(out[i]["sec"]), min(out[i - 1]["sec"])) * .5
        if (out[i]["pos"] - out[i - 1]["pos"]).length < room:
            del out[i if out[i]["bone"] is not None or out[i - 1]["bone"] is None else i - 1]
        else:
            i += 1
    return out


def ease(stations):
    """Let a level trunk flow: a deep chest into the neck, the rump into the
    tail. Each section leans towards the two beside it."""
    for _ in range(3):
        sizes = [s["sec"] for s in stations]
        for i in range(1, len(stations) - 1):
            if stations[i]["bone"] is None and set(stations[i]["weights"]) == {"head"}:
                continue   # the head keeps the shape it was drawn with
            stations[i]["sec"] = tuple(sizes[i - 1][axis] * .25 + sizes[i][axis] * .5 + sizes[i + 1][axis] * .25 for axis in (0, 1))


def unfold(stations):
    """Where a trunk turns sharply (a neck carried upright off a level back), sections
    packed close to the turn would cross each other on its inside and crease the
    surface. Clear the ones that sit nearer than the turn allows."""
    changed = True
    while changed and len(stations) > 3:
        changed = False
        for i in range(1, len(stations) - 1):
            a, b, c = stations[i - 1]["pos"], stations[i]["pos"], stations[i + 1]["pos"]
            into, out = b - a, c - b
            if into.length < 1e-9 or out.length < 1e-9:
                continue
            angle = into.angle(out)
            if angle < .35:
                continue
            clearance = max(stations[i]["sec"]) * .5 * math.tan(angle * .5) * 1.15
            for j, gap in ((i - 1, into.length), (i + 1, out.length)):
                if gap < clearance and 0 < j < len(stations) - 1:
                    del stations[j]
                    changed = True
                    break
            if changed:
                break


def ring_points(centre, side, front, half_w, half_d, sides):
    points = []
    for k in range(sides):
        angle = math.tau * k / sides + (math.pi / 4 if sides == 4 else 0)
        points.append(centre + side * (math.cos(angle) * half_w) + front * (math.sin(angle) * half_d))
    return points


def frames_for(stations, hint):
    """A side and front direction at every station, carried along without twisting."""
    centres = [s["pos"] for s in stations]
    frames = []
    side = None
    for i in range(len(centres)):
        a, b = centres[max(0, i - 1)], centres[min(len(centres) - 1, i + 1)]
        axis = b - a
        if axis.length < 1e-9:
            axis = Vector((0, 0, 1))
        axis.normalize()
        own = stations[i].get("hint")
        if own is not None and abs(own.normalized().dot(axis)) < .95:
            side = (own - axis * own.dot(axis)).normalized()
        elif side is None:
            _, side, _ = geo.box_frame(axis, hint)
        else:
            trial = side - axis * side.dot(axis)
            if trial.length > 1e-4:
                side = trial.normalized()
            else:
                _, side, _ = geo.box_frame(axis, None)
        frames.append((axis, side.copy(), axis.cross(side).normalized()))
    # Rings before the first station with its own hint (a collar at the root of an arm)
    # are carried back from it; otherwise the frame jumps round to the hint there and
    # the bridge between the two rings twists, up to a quarter turn.
    first = next((i for i, s in enumerate(stations) if s.get("hint") is not None
                  and abs(s["hint"].normalized().dot(frames[i][0])) < .95), None)
    if first:
        for i in range(first - 1, -1, -1):
            axis, carried = frames[i][0], frames[i + 1][1]
            trial = carried - axis * carried.dot(axis)
            if trial.length > 1e-4:
                side = trial.normalized()
                frames[i] = (axis, side, axis.cross(side).normalized())
    return frames


def cap(body, tube, ring):
    """Close a ring with quads."""
    if len(ring) == 4:
        tube.caps.append(body.face(ring))
    elif len(ring) == 8:
        for loop in ((7, 0, 1, 2), (7, 2, 3, 6), (6, 3, 4, 5)):
            tube.caps.append(body.face([ring[i] for i in loop]))
    else:
        tube.caps.append(body.face(ring))


def match(body, loop, points):
    """Order an opening's vertices so vertex k meets ring point k with the least twist.
    Compared by direction from each loop's own centre, not by distance: a ring set off
    to one side of its opening (an arm leaving downwards at an angle) would otherwise
    pair up one step round and twist the bridge between them by an eighth of a turn."""
    n = len(loop)
    middle = sum((body.verts[i] for i in loop), Vector()) / n
    centre = sum(points, Vector()) / len(points)
    ring = [(q - centre).normalized() for q in points]
    best = None
    for step in (1, -1):
        for offset in range(n):
            order = [loop[(step * j + offset) % n] for j in range(n)]
            cost = -sum((body.verts[order[j]] - middle).normalized().dot(ring[j]) for j in range(n))
            if best is None or cost < best[0]:
                best = (cost, order)
    return best[1]


def loft(body, tube, stations, hint, swell, opening=None, close_start=True):
    """Add rings for the stations and quads between them. opening: an existing
    loop of vertices the tube grows out of."""
    sides = tube.sides
    frames = frames_for(stations, hint)
    scale = swell * (math.sqrt(2) if sides == 4 else 1.0)
    first = len(tube.rings)
    for station, (axis, side, front) in zip(stations, frames):
        half_w, half_d = station["sec"][0] * .5 * scale, station["sec"][1] * .5 * scale
        if opening is not None and len(tube.rings) == first:
            # No wider than the opening it grows from, or the root flares into a cup.
            middle = sum((body.verts[i] for i in opening), Vector()) / len(opening)
            spread = sum((body.verts[i] - middle).length for i in opening) / len(opening)
            if max(half_w, half_d) > spread * .8:
                shrink = spread * .8 / max(half_w, half_d)
                half_w, half_d = half_w * shrink, half_d * shrink
        points = ring_points(station["pos"], side, front, half_w, half_d, sides)
        if opening is not None and len(tube.rings) == first:
            tube.rings.append(match(body, opening, points))
            tube.centres.append((sum((body.verts[i] for i in tube.rings[-1]), Vector()) / sides, side, front, half_w, half_d))
        tube.rings.append([body.vert(co, station["weights"]) for co in points])
        tube.centres.append((station["pos"].copy(), side, front, half_w, half_d))
        while len(tube.owner) < len(tube.rings):
            tube.owner.append(station.get("bone"))
    for i in range(first, len(tube.rings) - 1):
        a, b = tube.rings[i], tube.rings[i + 1]
        for k in range(sides):
            tube.grid[(i, k)] = body.face((a[k], a[(k + 1) % sides], b[(k + 1) % sides], b[k]))
    if opening is None and close_start:
        cap(body, tube, tube.rings[first])
    cap(body, tube, tube.rings[-1])


def inside(tube, point, margin=1.1):
    """Is the point within the tube's own flesh? Judged against the few sections
    nearest to it, so a point beside a deep chest is not excused by a slim neck close by."""
    ranked = []
    for index, (centre, side, front, half_w, half_d) in enumerate(tube.centres):
        offset = point - centre
        ranked.append((offset.length_squared, index, (offset.dot(side) / max(half_w, 1e-9)) ** 2 + (offset.dot(front) / max(half_d, 1e-9)) ** 2))
    if not ranked:
        return False
    ranked.sort()
    last = len(tube.centres) - 1
    nearest = ranked[0][1]
    # Past either end of the tube is outside it, however close to its axis.
    if nearest == last and last > 0 and (point - tube.centres[last][0]).dot(tube.centres[last][0] - tube.centres[last - 1][0]) > 0:
        return False
    if nearest == 0 and last > 0 and (point - tube.centres[0][0]).dot(tube.centres[0][0] - tube.centres[1][0]) > 0:
        return False
    return any(radial < margin * margin for _, _, radial in ranked[:3])


def open_patch(body, tube, target, bone=None):
    """Open the two-by-two patch of faces nearest the target, on the named
    bone's own rings where it has any. Returns its eight boundary vertices."""
    sides = tube.sides
    best = None
    own = [i for i in range(1, len(tube.rings) - 1) if bone and tube.owner[i] == bone]
    # The joint rings at either end of the bone count as its own: a hip at the end of the
    # pelvis opens round the hip, not one ring further along the pelvis.
    own = sorted(set(own) | {j for i in own for j in (i - 1, i + 1)
                             if 0 < j < len(tube.rings) - 1 and tube.owner[j] is None})
    for i in own or range(1, len(tube.rings) - 1):
        for k in range(sides):
            keys = [(i - 1, (k - 1) % sides), (i - 1, k), (i, (k - 1) % sides), (i, k)]
            if any(tube.grid.get(key) is None or body.faces[tube.grid[key]] is None for key in keys):
                continue
            distance = (body.verts[tube.rings[i][k]] - target).length_squared
            # Centred on the ring level with the limb: a ring above or below it counts double,
            # so a shoulder opens around the joint and not around the slope over it.
            run = tube.centres[i + 1][0] - tube.centres[i - 1][0]
            if run.length > 1e-9:
                distance += 2 * ((tube.centres[i][0] - target).dot(run.normalized())) ** 2
            if best is None or distance < best[0]:
                best = (distance, i, k, keys)
    if best is None:
        return None
    _, i, k, keys = best
    for key in keys:
        body.faces[tube.grid[key]] = None
        tube.grid[key] = None
    r = tube.rings
    left, right = (k - 1) % sides, (k + 1) % sides
    return [r[i - 1][left], r[i - 1][k], r[i - 1][right], r[i][right], r[i + 1][right], r[i + 1][k], r[i + 1][left], r[i][left]]


def open_face(body, tubes, target, outward=None):
    """Open the single quad nearest the target on any of the tubes. Returns its four vertices."""
    best = None
    for tube in tubes:
        candidates = [(key, index) for key, index in tube.grid.items()] + [(None, index) for index in tube.caps]
        for key, index in candidates:
            if index is None or body.faces[index] is None or len(body.faces[index]) != 4:
                continue
            loop = body.faces[index]
            centre = sum((body.verts[i] for i in loop), Vector()) / 4
            distance = (centre - target).length_squared
            if best is None or distance < best[0]:
                best = (distance, tube, key, index)
    if best is None:
        return None
    _, tube, key, index = best
    loop = list(body.faces[index])
    body.faces[index] = None
    if key is not None:
        tube.grid[key] = None
    else:
        tube.caps.remove(index)
    return loop


def split_crotch(body, tube, axis):
    """Divide the open bottom of the trunk into two eight-sided leg openings.
    Returns (left loop, right loop); left is the +side half."""
    ring = tube.rings[0]
    centre, side, front, half_w, half_d = tube.centres[0]
    # Columns 2 and 6 lie on the front-to-back line and belong to both openings.
    a, b = body.verts[ring[2]], body.verts[ring[6]]
    weights = body.weights[ring[2]]
    bridge = [body.vert(a.lerp(b, (j + 1) / 4) - axis * (half_d * .25 * math.sin(math.pi * (j + 1) / 4)), weights) for j in range(3)]
    left = [ring[6], ring[7], ring[0], ring[1], ring[2]] + bridge
    right = [ring[2], ring[3], ring[4], ring[5], ring[6]] + bridge[::-1]
    return left, right


def build(arm, forms, thickness, taper, smooth, limbs=1.0):
    global FOUR_LEGGED, LIMBS
    parts = collect(arm, thickness)
    legs_total = sum(1 for name in parts if name.endswith(".upper"))
    FOUR_LEGGED = legs_total >= 4 and arm.get("cs_species") not in {"SPIDER", "CRAB", "CENTIPEDE"}
    LIMBS = limbs
    if not parts:
        return [], [], []
    body = Body()
    swell8 = 1.09 if smooth else 1.03
    tube_of = {}
    pending = []    # (chain, parent part)
    trunks = []
    for part in parts.values():
        if part.parent is None and not part.taken:
            trunks.append(chain_from(part, True))
    def queue_children(sequence):
        for part, _ in sequence:
            for child in part.children:
                if not child.taken:
                    pending.append((chain_from(child, False), part))
    for sequence in trunks:
        root = next(part for part, flipped in sequence if not flipped)
        # Some hips are a short stub inside the base of the spine: the spine then is the trunk.
        absorbed = None
        if len(sequence) == 1:
            ahead = (root.tail - root.head).normalized()
            inner = [c for c in root.children if not c.taken and c.name.startswith(("spine.", "torso."))
                     and near(c.head, root.head, c, root) and (c.tail - c.head).normalized().dot(ahead) > .5]
            if inner:
                absorbed = root
                sequence = chain_from(inner[0], False)
        stations = stations_for(sequence, forms, taper)
        if abs((root.tail - root.head).normalized().z) < .7:
            ease(stations)
            unfold(stations)
        if absorbed:
            for station in stations[:2]:
                station["sec"] = (max(station["sec"][0], absorbed.sec[0]), max(station["sec"][1], absorbed.sec[1]))
                station["weights"] = {absorbed.name: .5, sequence[0][0].name: .5}
        tube = Tube(8)
        # Two legs hanging straight down from the bottom of the trunk part it like trousers.
        legs = []
        if sequence[0][0] is root or absorbed:
            down = (root.head - root.tail).normalized()
            legs = [c for c in root.children if not c.taken and c.name.startswith("leg.")
                    and (c.tail - c.head).normalized().dot(down) > .6 and (c.head - root.head).dot(down) > -.6 * root.length]
        crotch = len(legs) == 2 and legs[0].head.x * legs[1].head.x < 0
        if crotch:
            # Start at the hips' full size, level with the hip joints, rather than at a tapered tip.
            w, d = root.sec[:2]
            low = max((c.head - root.head).dot(down) for c in legs)
            stations[0]["sec"] = (w, d)
            stations[0]["pos"] = root.head + down * max(low, 0.0) * .5
        loft(body, tube, stations, root.hint, swell8, close_start=not crotch)
        for part, _ in sequence:
            tube_of[part.name] = tube
        if absorbed:
            tube_of[absorbed.name] = tube
            sequence = [(absorbed, False)] + sequence
        if crotch:
            left, right = split_crotch(body, tube, (root.tail - root.head).normalized())
            for leg in legs:
                chain = chain_from(leg, False)
                opening = left if leg.head.x > 0 else right
                limb = Tube(8)
                leg_stations = [s for s in stations_for(chain, forms, taper, root)
                                if (s["pos"] - stations[0]["pos"]).dot(down) > .3 * max(leg.sec[:2])]
                loft(body, limb, leg_stations or stations_for(chain, forms, taper, root)[-2:], leg.hint, swell8, opening=opening)
                for part, _ in chain:
                    tube_of[part.name] = limb
                queue_children(chain)
        queue_children(sequence)
        _, ears = head_rows(forms, parts["head"].head) if "head" in parts and tube_of.get("head") is tube else (None, [])
        for ear in ears:
            opening = open_face(body, [tube], ear[0][0])
            small = Tube(4)
            loft(body, small, [dict(pos=pos, sec=sec, weights={"head": 1.0}) for pos, sec in ear], None, 1.0, opening=opening)
    while pending:
        sequence, parent = pending.pop(0)
        first = sequence[0][0]
        host = tube_of.get(parent.name)
        stations = stations_for(sequence, forms, taper, parent)
        # A limb's first sections may lie inside the body it grows from; it starts where it comes out.
        shown = [s for s in stations if not (host and inside(host, s["pos"]))]
        if len(shown) < 2:
            shown = stations[-2:]
        if host and first.length > 1e-6:
            # Start the limb right where it leaves the body, so it is not a cape stretched from further out.
            leaves = next((i / 24 for i in range(25) if not inside(host, first.head + (first.tail - first.head) * (i / 24))), None)
            if leaves is not None and 0 < leaves < .9:
                # Far enough out that the whole first loop is clear of the body, not half in it.
                t = min(.9, leaves + (1.5 if FOUR_LEGGED else .45) * first.radius(False) / first.length)
                shown = [s for s in shown if s["bone"] != first.name or s["t"] is None or s["t"] > t + .08] or shown[-2:]
                limit = shown[0]["t"] if shown[0]["bone"] == first.name and shown[0]["t"] is not None else 1.0
                if shown[0]["bone"] in (first.name, None) or True:
                    if t < limit - .08 or shown[0]["bone"] != first.name:
                        if shown[0]["bone"] == first.name or all(s["bone"] != first.name for s in shown):
                            g = girth_at(profile_of(first.name), t, taper)
                            w0, d0, w1, d1 = first.sec
                            shown.insert(0, dict(pos=first.head + (first.tail - first.head) * t + first.shift,
                                                 sec=((w0 + (w1 - w0) * t) * g, (d0 + (d1 - d0) * t) * g),
                                                 weights={first.name: .7, parent.name: .3}, bone=first.name, t=t))
        if host:
            # Beside the body a limb cannot be fuller than where it came out, or it would cut back into it.
            limit_w, limit_d = shown[0]["sec"]
            for station in shown[1:3]:
                limit_w, limit_d = limit_w * 1.12, limit_d * 1.12
                station["sec"] = (min(station["sec"][0], limit_w), min(station["sec"][1], limit_d))
        target = shown[0]["pos"]
        limb_like = first.name.startswith(("leg.", "arm.", "clavicle.", "clawarm."))
        wide = (limb_like and host is not None and host.sides == 8
                and first.radius(False) > .1 * max(max(c[3], c[4]) for c in host.centres))
        if wide:
            # An arm or leg lying along the body it grows from (a foreleg down the side of the chest)
            # starts only where it is well clear, and opens the body at the point nearest that.
            clear = [s for s in shown if not inside(host, s["pos"], 1.35 if FOUR_LEGGED and first.name.startswith("leg.") else 1.12)]
            if len(clear) >= 2:
                shown = clear
            target = shown[0]["pos"]
        if wide and first.name.startswith("leg."):
            run = parent.tail - parent.head
            if run.length > 1e-6 and abs(run.normalized().z) < .7:
                # On a level body the opening is centred on the hip or shoulder along the body:
                # round the body it goes where the leg comes out, but no further fore or aft,
                # or the rings around the joint end up a row off and the leg leaves off-centre.
                run.normalize()
                target = target - run * (target - first.head).dot(run)
        opening = (open_patch(body, host, target, parent.name) or open_patch(body, host, target)) if wide else None
        sides = 8 if opening else 4
        if opening is None and host is not None:
            opening = open_face(body, [host], target)
        if opening and sides == 8:
            # Extrude straight out of the opening first, then turn along the limb:
            # a collar that keeps the root square to the body it grows from.
            middle = sum((body.verts[i] for i in opening), Vector()) / len(opening)
            normal = Vector()
            for a, b in zip(opening, opening[1:] + opening[:1]):
                normal += (body.verts[a] - middle).cross(body.verts[b] - middle)
            if normal.length > 1e-9:
                normal.normalize()
                if normal.dot(shown[0]["pos"] - middle) < 0:
                    normal = -normal
                spread = sum((body.verts[i] - middle).length for i in opening) / len(opening)
                # Only what carries on outwards from there: a section level with the opening,
                # or back towards the body, would fold the root into a cup.
                gap = (shown[0]["pos"] - middle).length
                if gap > .7 * spread:
                    # Halfway in size between the opening and the limb, so the root is a slope and not a step.
                    size = 2 * spread * .72 * .35 + max(shown[0]["sec"]) * .65
                    # Clear of the opening's own bulge: on a rounded body the middle of the opening
                    # sits well inside its outermost edge, and a collar there would fold the root.
                    # Leaving towards the limb, not straight out of the body: an arm held down
                    # at an angle starts down at that angle, so the ring round its root tilts.
                    # (Arms only: a hind leg leaving the hip backwards would start as a stub.)
                    towards = normal
                    if first.name.startswith(("arm.", "clavicle.")):
                        towards = (normal + (shown[0]["pos"] - middle).normalized()).normalized()
                    bulge = max(0.0, max((body.verts[i] - middle).dot(towards) for i in opening))
                    push = min(bulge + .30 * spread, .6 * gap) if bulge > .15 * spread else min(.40 * spread, .40 * gap)
                    shown.insert(0, dict(pos=middle + towards * push, sec=(size, size),
                                         weights={first.name: .5, parent.name: .5}, bone=None, t=None))
        if DEBUG and first.name.startswith("leg."):
            print("DBG", first.name, "wide", wide, "opening", bool(opening), "target", tuple(round(c, 3) for c in target),
                  "stations", len(stations), "shown", [(s["bone"], None if s["t"] is None else round(s["t"], 2), tuple(round(c, 2) for c in s["pos"])) for s in shown])
        tube = Tube(sides)
        loft(body, tube, shown, first.hint, swell8 if sides == 8 else 1.0, opening=opening)
        for part, _ in sequence:
            tube_of[part.name] = tube
        queue_children(sequence)
    # Drop the faces that were opened and the vertices left without a face.
    faces = [face for face in body.faces if face is not None]
    used = sorted({i for face in faces for i in face})
    remap = {old: new for new, old in enumerate(used)}
    verts = [body.verts[i] for i in used]
    weights = []
    for i in used:
        total = sum(body.weights[i].values()) or 1.0
        weights.append({bone: value / total for bone, value in body.weights[i].items() if value > 1e-4})
    faces = [tuple(remap[i] for i in face) for face in faces]
    for v in verts:
        if v.z < 0:
            v.z = 0.0   # soles flat on the floor
    import bmesh
    work = bmesh.new()
    made = [work.verts.new(v) for v in verts]
    for face in faces:
        try:
            work.faces.new([made[i] for i in face])
        except ValueError:
            pass
    bmesh.ops.recalc_face_normals(work, faces=work.faces)
    work.verts.index_update()
    faces = [tuple(v.index for v in face.verts) for face in work.faces]
    work.free()
    return verts, faces, weights
