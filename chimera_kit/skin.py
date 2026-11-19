"""Build mesh from skeleton: one skinned mesh grown along the creature's bones.

The skeleton becomes a graph of cross-sections: one at every joint and one a
little way along each bone on either side of it, so every joint carries three
edge loops. Blender's Skin modifier turns the graph into a connected quad
cage, each cross-section is then pressed into its bone's width and depth, and
every vertex takes its weights from the section it grew out of.

Mechs get separate hard parts instead: one rigid block for each bone."""
import json
import math
import bpy
from mathutils import Vector
from . import geometry as geo


def find(arm):
    """The mesh built for this creature, if it is still ours to rebuild."""
    for obj in arm.children:
        if obj.get("cs_skin"):
            return obj
    return None


def remove(arm):
    obj = find(arm)
    if obj:
        mesh = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)


def keep(arm):
    """Hand the mesh over to the artist: it stops following the body sliders."""
    obj = find(arm)
    if obj:
        del obj["cs_skin"]
        del obj["cs_owned"]
        obj.name = obj.name.replace(" · Mesh", " · My mesh")
    return obj


def template_fits(arm):
    from . import template
    try:
        return template.fits(arm)
    except Exception:
        return False


def style_for(arm, p):
    if p.skin_style != "AUTO":
        return p.skin_style
    return "JOINTED" if str(arm.get("cs_species", "")).startswith("MECH") else "ORGANIC"


class Graph:
    """Cross-sections joined by edges."""

    def __init__(self):
        self.pos, self.sec, self.frame, self.weights, self.edges = [], [], [], [], []

    def node(self, pos, sec, frame, weights):
        self.pos.append(Vector(pos))
        self.sec.append((max(sec[0], 1e-5), max(sec[1], 1e-5)))
        self.frame.append(frame)
        self.weights.append(dict(weights))
        return len(self.pos) - 1

    def edge(self, a, b):
        if a != b and (self.pos[a] - self.pos[b]).length > 1e-6:
            self.edges.append((a, b))


def head_nodes(graph, forms, thickness):
    """A head drawn as body forms becomes a short chain of sections: a human
    skull from chin to crown, or an animal head from the back of the skull to
    the snout, plus a muzzle and ears where the preset draws them."""
    main = None
    for form in forms:
        if form["bone"] == "head" and not form.get("ball") and form["color"] == 0:
            main = form
            break
    if not main:
        return []
    center = Vector(main["center"])
    sx, sy, sz = main["scale"]
    weight = {"head": 1.0}
    nodes = []
    amount = main.get("skull", 0)
    if amount or sz >= sy * 1.15:
        frame = geo.box_frame(Vector((0, 0, 1)))
        # From the jaw up: the chin point itself would only make a spur under the head.
        for v, w, d, off in geo.skull_rows(amount, True)[1:]:
            nodes.append(graph.node(center + Vector((0, sy * off, sz * v)), (2 * sx * w, 2 * sy * d), frame, weight))
        graph.neck_socket = nodes[0]
    else:
        frame = geo.box_frame(Vector((0, -1, 0)))
        for v, w in ((-1, .55), (-.6, .9), (-.1, 1.0), (.4, .86), (.8, .62), (1.0, .42)):
            nodes.append(graph.node(center + Vector((0, -sy * v, 0)), (2 * sx * w, 2 * sz * w), frame, weight))
    for a, b in zip(nodes, nodes[1:]):
        graph.edge(a, b)
    main_nodes = list(nodes)
    def nearest(point):
        return min(main_nodes, key=lambda i: (graph.pos[i] - point).length)
    for form in forms:
        if form is main or form["bone"] != "head" or form.get("ball") or form["color"] == 2:
            continue
        c = Vector(form["center"])
        fx, fy, fz = form["scale"]
        if form["color"] == 0 and c.y < center.y - sy * .3:
            # A muzzle or snout out in front of the skull.
            frame = geo.box_frame(Vector((0, -1, 0)))
            a = graph.node(c, (2 * fx, 2 * fz), frame, weight)
            b = graph.node(c + Vector((0, -fy * .85, 0)), (1.5 * fx, 1.5 * fz), frame, weight)
            graph.edge(nearest(c), a)
            graph.edge(a, b)
            nodes += [a, b]
        elif form["color"] == 1 and fz > fx * 1.3:
            # An ear: a flat spike standing on, or hanging beside, the head.
            frame = geo.box_frame(Vector((0, 0, 1)))
            base = c - Vector((0, 0, fz * .7))
            a = graph.node(base, (2 * fx, 2 * fy), frame, weight)
            b = graph.node(c + Vector((0, 0, fz * .9)), (.8 * fx, .8 * fy), frame, weight)
            graph.edge(nearest(base), a)
            graph.edge(a, b)
            nodes += [a, b]
    return nodes


def build_graph(arm, forms, thickness):
    bones = arm.data.bones
    graph = Graph()
    fleshed = {b.name for b in bones if b.use_deform and "cs_box" in b.keys()}
    nodes_of = {}      # bone -> every node drawn for it
    ends = {}          # bone -> (head node, tail node)
    near_tail = {}     # bone -> the loop just before its tail
    followers = {}     # bone -> children that share its tail joint
    joint_at = {}      # bone -> where its tail joint is on the skeleton
    for bone in bones:
        if bone.name not in fleshed:
            continue
        head, tail = bone.head_local.copy(), bone.tail_local.copy()
        length = (tail - head).length
        if length < 1e-6:
            continue
        w0, d0, w1, d1 = (v * thickness for v in bone["cs_box"])
        hint = bone.get("cs_side")
        frame = geo.box_frame(tail - head, Vector(hint) if hint else None)
        parent = bone.parent
        while parent and parent.name not in nodes_of:
            parent = parent.parent
        tolerance = max(1e-5, .02 * length)
        rooted = False
        # A body form drawn off the bone's own line (a foot resting on the floor) carries its section with it.
        shift = Vector(bone["cs_offset"]) if "cs_offset" in bone.keys() else Vector((0, 0, 0))
        shared = False
        if parent and parent.name in ends:
            p_head, p_tail = ends[parent.name]
            if (joint_at[parent.name] - head).length < tolerance:
                start, shared = p_tail, True
                followers.setdefault(parent.name, []).append(bone.name)
            elif (graph.pos[p_head] - head).length < tolerance:
                start = p_head
            else:
                start = None
        else:
            start = None
        if start is not None:
            # A joint between two bones: both own it, and it takes the fuller section,
            # so a chest stays broad right up to the neck.
            sw, sd = graph.sec[start]
            graph.sec[start] = (max(sw, w0), max(sd, d0))
            graph.weights[start][bone.name] = graph.weights[start].get(bone.name, 0) + 1.0
        else:
            if parent:
                # A limb that starts inside its parent's body grows straight out of the
                # parent's nearest section: a joint buried in there would only knot the surface.
                start = min(nodes_of[parent.name], key=lambda i: (graph.pos[i] - head).length)
                rooted = True
            else:
                start = graph.node(head, (w0, d0), frame, {bone.name: 1.0})
        mine = [] if rooted else [start]
        if bone.name == "head":
            skull_nodes = head_nodes(graph, forms, thickness)
            if skull_nodes:
                socket = getattr(graph, "neck_socket", None)
                graph.edge(start, socket if socket is not None else min(skull_nodes, key=lambda i: (graph.pos[i] - head).length))
                nodes_of[bone.name] = skull_nodes
                continue
        radius = max(w0, d0, w1, d1) * .5
        def along(t, weights):
            return graph.node(head + (tail - head) * t + shift, (w0 + (w1 - w0) * t, d0 + (d1 - d0) * t), frame, weights)
        previous = start
        def buried(t):
            """Is this point of a rooted limb still inside the section it grows from?"""
            if not rooted:
                return False
            _, side0, front0 = graph.frame[start]
            sw, sd = graph.sec[start]
            offset = head + (tail - head) * t - graph.pos[start]
            return (offset.dot(side0) / (sw * .5)) ** 2 + (offset.dot(front0) / (sd * .5)) ** 2 < 1.2
        if length > 2.2 * radius:
            # A loop either side of each joint; with the joint itself that makes three.
            a = min(.33, .9 * radius / length)
            b = 1 - a
            while buried(a) and a < b - .1:
                a += .05
            last = along(b, {bone.name: 1.0})
            if not buried(a):
                first = along(a, {bone.name: .85, parent.name: .15} if shared or rooted else {bone.name: 1.0})
                graph.edge(previous, first)
                graph.edge(first, last)
                mine.append(first)
            else:
                graph.edge(previous, last)
            previous = last
            mine.append(last)
            near_tail[bone.name] = last
        elif length > 1.1 * radius:
            middle = along(.5, {bone.name: 1.0})
            graph.edge(previous, middle)
            previous = middle
            mine.append(middle)
        end = graph.node(tail + shift, (w1, d1), frame, {bone.name: 1.0})
        joint_at[bone.name] = tail
        graph.edge(previous, end)
        mine.append(end)
        ends[bone.name] = (start, end)
        nodes_of[bone.name] = mine
    for name, children in followers.items():
        if len(children) == 1 and name in near_tail:
            graph.weights[near_tail[name]] = {name: .85, children[0]: .15}
    used = {i for edge in graph.edges for i in edge}
    # A tip nobody continues from is drawn in, so limbs and tails end rounded.
    degree = {}
    for a, b in graph.edges:
        degree[a] = degree.get(a, 0) + 1
        degree[b] = degree.get(b, 0) + 1
    for i in used:
        if degree.get(i) == 1:
            w, d = graph.sec[i]
            graph.sec[i] = (w * .8, d * .8)
    return graph


def skin_cage(context, graph, name):
    """Run the Skin modifier over the graph. Returns (vertices, faces, source node per vertex)."""
    count = len(graph.pos)
    mesh = bpy.data.meshes.new(name + " · graph")
    mesh.from_pydata([tuple(p) for p in graph.pos], graph.edges, [])
    mesh.update()
    obj = bpy.data.objects.new(name + " · graph", mesh)
    context.scene.collection.objects.link(obj)
    try:
        for i in range(count):
            obj.vertex_groups.new(name=f"~{i}").add([i], 1.0, "REPLACE")
        modifier = obj.modifiers.new("Skin", "SKIN")
        modifier.use_smooth_shade = True
        modifier.branch_smoothing = 0.0
        modifier.use_x_symmetry = modifier.use_y_symmetry = modifier.use_z_symmetry = False
        # One root for every connected piece of the graph.
        group = list(range(count))
        def top(i):
            while group[i] != i:
                group[i] = group[group[i]]
                i = group[i]
            return i
        for a, b in graph.edges:
            group[top(a)] = top(b)
        roots = {top(i) for i in range(count)}
        layer = mesh.skin_vertices[0].data
        for i in range(count):
            r = max(graph.sec[i]) * .5
            layer[i].radius = (r, r)
            layer[i].use_root = i in roots
        depsgraph = context.evaluated_depsgraph_get()
        cage = bpy.data.meshes.new_from_object(obj.evaluated_get(depsgraph), preserve_all_data_layers=True, depsgraph=depsgraph)
        verts = [v.co.copy() for v in cage.vertices]
        faces = [tuple(p.vertices) for p in cage.polygons]
        source = []
        for v in cage.vertices:
            best = max(v.groups, key=lambda g: g.weight, default=None)
            source.append(best.group if best else -1)
        bpy.data.meshes.remove(cage)
    finally:
        bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.meshes.remove(mesh)
    return verts, faces, source


def organic(context, arm, forms, thickness, name, swell=1.0, grounded=True):
    graph = build_graph(arm, forms, thickness)
    if not graph.edges:
        return [], [], []
    verts, faces, source = skin_cage(context, graph, name)
    count = len(graph.pos)
    radius = [max(sec) * .5 for sec in graph.sec]
    shares = []
    for table in graph.weights:
        total = sum(table.values())
        shares.append({bone: value / total for bone, value in table.items()})
    # The modifier draws a ring at most sections and tags it with that section.
    # How far out does it put a ring, relative to the radius it was given?
    ratios = []
    for index, node in enumerate(source):
        if node >= 0:
            axis, side, front = graph.frame[node]
            offset = verts[index] - graph.pos[node]
            ratios.append(math.hypot(offset.dot(side), offset.dot(front)) / radius[node])
    ratios.sort()
    ring = ratios[len(ratios) // 2] if ratios else 1.414
    # Branch hulls and the extra rings it adds along a bone carry no tag. Each
    # takes the section of the nearest tagged ring across the surface, then
    # slides along that section's edges to the closest point.
    links = [[] for _ in verts]
    for face in faces:
        for i, a in enumerate(face):
            b = face[(i + 1) % len(face)]
            links[a].append(b)
            links[b].append(a)
    seed = list(source)
    frontier = [i for i, node in enumerate(source) if node >= 0]
    while frontier:
        following = []
        for i in frontier:
            for j in links[i]:
                if seed[j] < 0:
                    seed[j] = seed[i]
                    following.append(j)
        frontier = following
    touching = [[] for _ in range(count)]
    for a, b in graph.edges:
        touching[a].append(b)
        touching[b].append(a)
    weights = []
    for index, node in enumerate(seed):
        if node < 0:
            node = min(range(count), key=lambda i: (graph.pos[i] - verts[index]).length)
        other, t = node, 0.0
        if source[index] < 0:
            best = None
            for neighbour in touching[node]:
                span = graph.pos[neighbour] - graph.pos[node]
                along = max(0.0, min(1.0, (verts[index] - graph.pos[node]).dot(span) / span.length_squared))
                distance = (verts[index] - graph.pos[node] - span * along).length
                if best is None or distance < best:
                    best, other, t = distance, neighbour, along
        point = graph.pos[node].lerp(graph.pos[other], t)
        # Towards a branch the limb keeps its own section, or it would flare into a collar.
        blend = t
        far_w, far_d, far_r = graph.sec[other][0], graph.sec[other][1], radius[other]
        if len(touching[other]) > 2:
            cap = 1.5
            far_w, far_d = min(far_w, graph.sec[node][0] * cap), min(far_d, graph.sec[node][1] * cap)
        w = graph.sec[node][0] + (far_w - graph.sec[node][0]) * blend
        d = graph.sec[node][1] + (far_d - graph.sec[node][1]) * blend
        unit = swell / (ring * (radius[node] + (far_r - radius[node]) * blend))
        axis, side, front = graph.frame[node if t < .5 else other]
        offset = verts[index] - point
        # Press the round tube into the section's own width and depth.
        verts[index] = (point + axis * offset.dot(axis) + side * offset.dot(side) * (w * .5 * unit)
                        + front * offset.dot(front) * (d * .5 * unit))
        table = {}
        for bone, value in shares[node].items():
            table[bone] = value * (1 - t)
        for bone, value in shares[other].items():
            table[bone] = table.get(bone, 0.0) + value * t
        weights.append({bone: value for bone, value in table.items() if value > 1e-4})
    if grounded:
        for v in verts:
            if v.z < 0:
                v.z = 0.0   # soles flat on the floor
    # Close any gap the modifier left at a crowded branch, and make every face point outwards.
    import bmesh
    work = bmesh.new()
    made = [work.verts.new(v) for v in verts]
    for face in faces:
        try:
            work.faces.new([made[i] for i in face])
        except ValueError:
            pass   # a doubled face
    bmesh.ops.holes_fill(work, edges=work.edges, sides=12)
    bmesh.ops.recalc_face_normals(work, faces=work.faces)
    work.verts.index_update()
    faces = [tuple(v.index for v in face.verts) for face in work.faces]
    work.free()
    return verts, faces, weights


def jointed(arm, forms, thickness):
    """A hard block for every bone and every body form, each rigid on its own bone."""
    verts, faces, weights = [], [], []
    def add(part_verts, part_faces, bone):
        base = len(verts)
        verts.extend(part_verts)
        faces.extend(tuple(base + i for i in face) for face in part_faces)
        weights.extend({bone: 1.0} for _ in part_verts)
    for bone in arm.data.bones:
        if not bone.use_deform or "cs_box" not in bone.keys():
            continue
        if bone.get("cs_formed"):
            continue   # its body form below is the part
        hint = bone.get("cs_side")
        box = tuple(v * thickness for v in bone["cs_box"])
        part = geo.box_shell(bone.head_local, bone.tail_local, box, .03, Vector(hint) if hint else None)
        add(part[0], part[1], bone.name)
    for form in forms:
        sx, sy, sz = form["scale"]
        if form.get("ball") or form["color"] == 2 or (abs(sx - sy) < 1e-9 and abs(sy - sz) < 1e-9):
            continue
        if form["bone"] not in arm.data.bones:
            continue
        if form.get("skull"):
            part = geo.skull_shell(form["center"], form["scale"], form["skull"], False)
        else:
            part = geo.form_shell(form["center"], tuple(v * thickness for v in form["scale"]))
        add(part[0], part[1], form["bone"])
    return verts, faces, weights


def sphere(center, scale, segments=12, rings=8):
    center, scale = Vector(center), Vector(scale)
    verts = [center + Vector((0, 0, scale.z))]
    for j in range(1, rings):
        phi = math.pi * j / rings
        for i in range(segments):
            theta = math.tau * i / segments
            verts.append(center + Vector((scale.x * math.sin(phi) * math.cos(theta),
                                          scale.y * math.sin(phi) * math.sin(theta), scale.z * math.cos(phi))))
    bottom = len(verts)
    verts.append(center - Vector((0, 0, scale.z)))
    faces = [(0, 1 + i, 1 + (i + 1) % segments) for i in range(segments)]
    for j in range(rings - 2):
        a, b = 1 + j * segments, 1 + (j + 1) * segments
        for i in range(segments):
            k = (i + 1) % segments
            faces.append((a + i, b + i, b + k, a + k))
    last = 1 + (rings - 2) * segments
    faces += [(bottom, last + (i + 1) % segments, last + i) for i in range(segments)]
    return verts, faces


class _Settings:
    """The creature's own sliders, as built, with a few of them changed."""
    def __init__(self, p, stored, **changes):
        self._p, self._values = p, dict(stored)
        self._values.update(changes)
    def __getattr__(self, key):
        values = self.__dict__.get("_values", {})
        return values[key] if key in values else getattr(self.__dict__["_p"], key)


class _Bone:
    """Just enough of a Blender bone for the quad mesher."""
    def __init__(self, spec, section, formed, offset):
        self.name = spec["name"]
        self.head_local, self.tail_local = Vector(spec["head"]), Vector(spec["tail"])
        self.length = (self.tail_local - self.head_local).length
        self.use_deform = spec["deform"]
        self.parent = None
        self._props = {}
        if section:
            self._props["cs_box"] = section
            if offset: self._props["cs_offset"] = offset
        if spec.get("side"):
            self._props["cs_side"] = list(spec["side"])
    def keys(self): return self._props.keys()
    def get(self, key, default=None): return self._props.get(key, default)
    def __getitem__(self, key): return self._props[key]


class _Skeleton:
    def __init__(self, bones, species):
        self.data = type("Data", (), {})()
        self.data.bones = bones
        self._species = species
    def get(self, key, default=None):
        return self._species if key == "cs_species" else default


A_POSE = math.radians(45)


def a_pose_raise(p, stored=None, species=None):
    """The arm rest (the arm_raise slider) that puts the arms 45 degrees out from
    hanging straight down, for this creature. 0 when they already hang that wide."""
    from .anatomy import blueprint
    try:
        plan = blueprint(_Settings(p, stored or {}, arm_raise=0.0, **({"species": species} if species else {})))
    except Exception:
        return 0.0
    bones = {spec["name"]: spec for spec in plan.bones}
    upper, fore = bones.get("arm.L"), bones.get("forearm.L")
    if not upper or not fore:
        return 0.0
    dx, dz = fore["tail"][0] - upper["head"][0], fore["tail"][2] - upper["head"][2]
    out = math.atan2(dx, -dz)
    if out >= A_POSE or out >= math.pi * .5 - 1e-3:
        return 0.0
    return (A_POSE - out) / (math.pi * .5 - out)


def layout_source(arm, p):
    """A creature whose arms rest anywhere below an A-pose (hanging at the sides,
    or part way up) gets its mesh laid out on the same skeleton with the arms in
    an A-pose, 45 degrees out, where a shoulder can be modelled cleanly, then
    turned round the shoulder to the real rest through its own skin weights.
    From an A the shoulder never has to bend more than 45 degrees, either way.
    Returns (stand-in skeleton, forms, lower(verts, weights)) or None when the
    arms already rest at an A or wider (a T is meshed as it is) or there are none."""
    from . import rig
    from .anatomy import blueprint, family, turn_y, THEROPODS
    stored = rig.stored_settings(arm)
    if "arm.L" not in arm.data.bones or not stored:
        return None
    species = arm.get("cs_species", stored.get("species"))
    if species in THEROPODS:
        return None
    rest = stored.get("arm_raise", 0.0)
    layout = a_pose_raise(p, stored, species)
    if layout <= rest + 1e-3:
        return None
    try:
        plan = blueprint(_Settings(p, stored, arm_raise=layout, species=species))
    except Exception as exc:
        print("Chimera Kit: A-pose layout skipped (" + repr(exc) + ")")
        return None
    relaxed = {}
    for upper, lifted in getattr(plan, "arm_drop", {}).items():
        # The lift is in proportion to the slider, so from the layout to the real rest is the rest of it.
        drop = lifted * (1 - rest / layout)
        bone = arm.data.bones.get(upper)
        if bone is None:
            return None
        names = family(plan, upper)
        pivot = tuple(bone.head_local)
        # Lowered with the same turn the skeleton was raised by, every bone must land on the real one.
        for spec in plan.bones:
            if spec["name"] in names and spec["name"] in arm.data.bones:
                real = arm.data.bones[spec["name"]]
                for key, target in (("head", real.head_local), ("tail", real.tail_local)):
                    if (Vector(turn_y(spec[key], pivot, drop)) - target).length > 1e-3 * max(1.0, real.length * 50):
                        return None
            if spec["name"] in names:
                relaxed[spec["name"]] = (pivot, drop)
    if not relaxed:
        return None
    bones = {}
    for spec in plan.bones:
        section, formed, offset = rig.bone_section(spec, plan.forms)
        bones[spec["name"]] = _Bone(spec, section, formed, offset)
    for spec in plan.bones:
        if spec["parent"]:
            bones[spec["name"]].parent = bones.get(spec["parent"])
    class Bones(list):
        def get(self, name, default=None): return bones.get(name, default)
        def __contains__(self, name): return name in bones if isinstance(name, str) else list.__contains__(self, name)
        def __getitem__(self, key): return bones[key] if isinstance(key, str) else list.__getitem__(self, key)
    stand_in = _Skeleton(Bones(bones[spec["name"]] for spec in plan.bones), species)
    # Each arm, as it lies in the layout: shoulder, outward direction and thickness.
    arms = []
    for upper, (pivot, drop) in {name: relaxed[name] for name in getattr(plan, "arm_drop", {}) if name in relaxed}.items():
        spec = next(s_ for s_ in plan.bones if s_["name"] == upper)
        out = Vector(spec["tail"]) - Vector(spec["head"])
        section = rig.bone_section(spec, plan.forms)[0] or [out.length * .3] * 4
        arms.append((Vector(spec["head"]), out.normalized(), max(section[:2]) * .5, pivot, drop))
    def lower(verts, weights):
        # The turn is blended, not the positions: a vertex half way between chest and arm
        # turns half way round the shoulder, so the shoulder rolls over into the arm.
        # Besides its weights, how far a vertex turns follows where it sits: the flesh over
        # the shoulder goes down with the arm, the chest beside it stays.
        out = []
        for v, table in zip(verts, weights):
            v = Vector(v)
            total = sum(table.values()) or 1.0
            share, turn = 0.0, None
            for bone, w in table.items():
                if bone in relaxed:
                    share += w / total
                    turn = relaxed[bone]
            for head, axis, radius, pivot, drop in arms:
                offset = v - head
                along = offset.dot(axis)
                across = (offset - axis * along).length
                if across < 2.0 * radius and along > -1.2 * radius:
                    f = max(0.0, min(1.0, (along + 1.0 * radius) / (2.4 * radius)))
                    f = f * f * (3 - 2 * f)
                    # Fading out away from the arm's line, so the side of the chest is left alone.
                    g = max(0.0, min(1.0, (2.0 * radius - across) / (1.0 * radius)))
                    if f * g > share:
                        share, turn = f * g, (pivot, drop)
            out.append(Vector(turn_y(v, turn[0], turn[1] * share)) if turn else v)
        return out
    return stand_in, plan.forms, lower


def build(context, arm, p, style=None, thickness=None, smooth=None, taper=None, base=None):
    """Build, or rebuild, the creature's mesh and skin it to the skeleton."""
    style = style or style_for(arm, p)
    thickness = p.skin_thickness if thickness is None else thickness
    smooth = p.skin_smooth if smooth is None else smooth
    remove(arm)
    try:
        forms = json.loads(arm.get("cs_forms", "[]"))
    except ValueError:
        forms = []
    name = arm.name[:-len(" · Rig")] if arm.name.endswith(" · Rig") else arm.name
    base = base or getattr(p, "skin_base", "PROCEDURAL")
    templated = style != "JOINTED" and base != "PROCEDURAL" and template_fits(arm)
    source = layout_source(arm, p) if style != "JOINTED" and not templated else None
    if templated:
        from . import template
        verts, faces, weights = template.build(arm, base, thickness, p.skin_limbs)
    elif style == "JOINTED":
        verts, faces, weights = jointed(arm, forms, thickness)
    else:
        from . import quads
        try:
            if source:
                stand_in, t_forms, lower = source
                verts, faces, weights = quads.build(stand_in, t_forms, thickness, p.skin_taper if taper is None else taper, smooth, p.skin_limbs)
                verts = lower(verts, weights)
            else:
                verts, faces, weights = quads.build(arm, forms, thickness, p.skin_taper if taper is None else taper, smooth, p.skin_limbs)
        except Exception as exc:
            # An unusual skeleton the quad builder cannot lay out still gets a skin.
            print("Chimera Kit: quad body failed (" + repr(exc) + "), using the hull builder")
            verts, faces, weights = organic(context, arm, forms, thickness, name, 1.5 if smooth else 1.4)
    if not faces:
        raise RuntimeError("this skeleton has no bones with a body to build from")
    material_of = [0] * len(faces)
    species = arm.get("cs_species", "HUMAN")
    colors = geo.PALETTES.get(species, geo.PALETTES["HUMAN"])
    materials = [geo.material("CK · " + species + " skin", colors[0], .0, .55)]
    def island(part_verts, part_faces, part_weights, material):
        base = len(verts)
        verts.extend(part_verts)
        faces.extend(tuple(base + i for i in face) for face in part_faces)
        weights.extend(part_weights)
        if material not in materials:
            materials.append(material)
        material_of.extend([materials.index(material)] * len(part_faces))
    # Wing membranes: each corner rides its own bone, as on the mannequin.
    panels = geo.wing_panels(arm.data.bones)
    if panels:
        membrane = geo.material("CK · " + species + " joints", colors[1], .30)
        for corners in panels:
            island([c[0] for c in corners], [tuple(range(len(corners)))], [{c[1]: 1.0} for c in corners], membrane)
    balls = {"eye_white": ((.93, .93, .90), .25), "eye_pupil": ((.02, .02, .025), .2)}
    for form in ([] if templated else forms):
        kind = form.get("ball")
        if kind in balls and form["bone"] in arm.data.bones:
            part = sphere(form["center"], form["scale"])
            island(part[0], part[1], [{form["bone"]: 1.0}] * len(part[0]),
                   geo.material("CK · " + kind, balls[kind][0], .0, balls[kind][1]))
    mesh = bpy.data.meshes.new(name + " · Mesh")
    mesh.from_pydata([tuple(v) for v in verts], [], faces)
    mesh.update()
    for material in materials:
        mesh.materials.append(material)
    hard = style == "JOINTED"
    for poly, index in zip(mesh.polygons, material_of):
        poly.material_index = index
        poly.use_smooth = not hard
    obj = bpy.data.objects.new(name + " · Mesh", mesh)
    arm.users_collection[0].objects.link(obj)
    obj.color = materials[0].diffuse_color
    groups = {}
    for index, table in enumerate(weights):
        for bone, value in table.items():
            group = groups.get(bone)
            if group is None:
                group = groups[bone] = obj.vertex_groups.new(name=bone)
            group.add([index], value, "REPLACE")
    obj.parent = arm
    if hard:
        bevel = obj.modifiers.new("Chamfer", "BEVEL")
        bevel.width = float(arm.get("cs_size", 1.8)) * .004
        bevel.segments = 2
        bevel.limit_method = "ANGLE"
    obj.modifiers.new("Chimera Kit", "ARMATURE").object = arm
    if smooth and not hard:
        subdivision = obj.modifiers.new("Smooth", "SUBSURF")
        subdivision.levels = subdivision.render_levels = smooth
    obj["cs_skin"] = True
    obj["cs_owned"] = True
    obj["cs_skin_style"] = style
    obj["cs_skin_base"] = base if templated else "PROCEDURAL"
    obj["cs_skin_thickness"] = thickness
    obj["cs_skin_smooth"] = smooth
    obj["cs_skin_taper"] = p.skin_taper if taper is None else taper
    # The mesh replaces the mannequin on screen; Show / hide mannequin brings it back.
    for child in arm.children:
        if child.get("cs_preview"):
            child.hide_set(True)
            child.hide_render = True
    return obj
