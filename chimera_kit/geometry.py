"""Small, package-free meshes for rig previews. No proprietary assets."""
import math
import bpy
from mathutils import Vector

PALETTES = {
    "APE": ((.16,.10,.07),(.45,.30,.19)),
    "MECH": ((.16,.21,.27),(.94,.48,.08)),
    "GNOU": ((.22,.18,.14),(.61,.51,.37)),
    "LIZARD": ((.15,.34,.12),(.63,.79,.24)),
    "ALIEN": ((.18,.12,.30),(.21,.78,.62)),
    "ANGEL": ((.66,.72,.82),(.94,.68,.25)),
    "CRAB": ((.48,.10,.08),(.94,.40,.14)),
    "MECH_TROOPER": ((.55,.57,.60),(.90,.35,.10)),
    "MECH_FLYER": ((.80,.82,.85),(.75,.12,.12)),
    "MECH_POD": ((.33,.38,.28),(.85,.60,.15)),
    "BIRD": ((.55,.33,.18),(.90,.70,.25)),
    "EAGLE": ((.30,.20,.12),(.92,.80,.35)),
    "OSTRICH": ((.16,.14,.13),(.85,.70,.62)),
    "PENGUIN": ((.07,.08,.10),(.95,.60,.12)),
    "FISH": ((.90,.45,.10),(.95,.85,.60)),
    "SHARK": ((.38,.44,.50),(.85,.87,.88)),
    "DOLPHIN": ((.45,.55,.64),(.85,.88,.90)),
    "WHALE": ((.16,.22,.32),(.70,.75,.80)),
    "BRONTO": ((.36,.42,.33),(.62,.66,.52)),
    "FROG": ((.20,.55,.16),(.80,.82,.30)),
    "SNAKE": ((.42,.50,.14),(.85,.75,.25)),
    "WORM": ((.78,.42,.40),(.90,.60,.55)),
    "TADPOLE": ((.16,.18,.14),(.50,.52,.40)),
    "GIRAFFE": ((.80,.58,.22),(.45,.27,.10)),
    "GECKO": ((.42,.55,.16),(.90,.72,.30)),
    "TREX": ((.30,.24,.16),(.75,.50,.25)),
    "GORILLA": ((.07,.07,.08),(.30,.30,.33)),
    "CENTAUR": ((.33, .20, .11), (.86, .66, .45)),
    "BIPED": ((.80,.56,.10),(.13,.42,.80)),
    "HUMAN": ((0.13, .38, .56), (.95, .44, .12)),
    "HORSE": ((.36, .17, .08), (.86, .59, .27)),
    "PANTHER": ((.055, .11, .18), (.14, .65, .60)),
    "ALLOSAUR": ((.19, .32, .17), (.79, .43, .12)),
    "DRAGON": ((.25, .12, .36), (.77, .32, .20)),
    "SPIDER": ((.07, .16, .21), (.92, .28, .09)),
    "CENTIPEDE": ((.14, .28, .23), (.71, .46, .12)),
}

def material(name, color, metallic=0.15, roughness=0.36):
    mat = bpy.data.materials.get(name)
    if mat:
        return mat
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1)
    mat.use_nodes = True
    shader = mat.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1)
    shader.inputs["Metallic"].default_value = metallic
    shader.inputs["Roughness"].default_value = roughness
    return mat

# Left red, right green (as on a ship's port and starboard lights), blue body, yellow head.
# The red leans orange and the green leans teal so the pair stays distinguishable to most colour-blind viewers.
SIDE_COLORS={"L":(.82,.10,.04),"R":(.02,.50,.30),"C":(.07,.22,.72),"H":(.92,.68,.05)}

def side_material(name):
    """Left red, right green, blue body, yellow head."""
    key="L" if name.endswith(".L") or ".L." in name else "R" if name.endswith(".R") or ".R." in name else \
        "H" if name=="head" or name.startswith("neck") else "C"
    return material("CK · box "+key,SIDE_COLORS[key],.0,.55)

def mesh_object(collection, name, vertices, faces, mat=None, smooth=True):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    if mat:
        mesh.materials.append(mat)
        obj.color = mat.diffuse_color
    for poly in mesh.polygons:
        poly.use_smooth = smooth
    obj["cs_owned"] = True
    return obj

def box_frame(axis):
    """Side-to-side and front-to-back directions for a bone axis."""
    axis=axis.normalized()
    side=Vector((1,0,0)) if abs(axis.x)<.8 else Vector((0,1,0))
    side=(side-axis*side.dot(axis)).normalized()
    return axis,side,axis.cross(side).normalized()

def box_segment(collection, name, head, tail, box, mat, gap=.03):
    """Tapered, chamfered box along a bone: flat shaded like a figure-mode biped."""
    head,tail=Vector(head),Vector(tail)
    axis,side,front=box_frame(tail-head)
    length=(tail-head).length
    w0,d0,w1,d1=box
    chamfer=min(.12,.35*min(w0,d0,w1,d1)/max(length,1e-6))
    verts=[]
    for fraction,scale in ((gap,.72),(gap+chamfer,1),(1-gap-chamfer,1),(1-gap,.72)):
        w=(w0+(w1-w0)*fraction)*.5*scale
        d=(d0+(d1-d0)*fraction)*.5*scale
        center=head+axis*length*fraction
        for sx,sy in ((-1,-1),(1,-1),(1,1),(-1,1)):
            verts.append(center+side*w*sx+front*d*sy)
    faces=[(3,2,1,0)]
    for j in range(3):
        for i in range(4):
            k=(i+1)%4
            faces.append((j*4+i,j*4+k,(j+1)*4+k,(j+1)*4+i))
    faces.append((12,13,14,15))
    return mesh_object(collection,name,verts,faces,mat,smooth=False)

def box_form(collection, name, center, scale, mat):
    """Axis-aligned chamfered block standing in for a rounded body form."""
    center=Vector(center)
    sx,sy,sz=(v*.86 for v in scale)
    verts=[]
    for z,k in ((-sz,.74),(-sz*.72,1),(sz*.72,1),(sz,.74)):
        for ax,ay in ((-1,-1),(1,-1),(1,1),(-1,1)):
            verts.append(center+Vector((sx*k*ax,sy*k*ay,z)))
    faces=[(3,2,1,0)]
    for j in range(3):
        for i in range(4):
            k=(i+1)%4
            faces.append((j*4+i,j*4+k,(j+1)*4+k,(j+1)*4+i))
    faces.append((12,13,14,15))
    return mesh_object(collection,name,verts,faces,mat,smooth=False)

def ellipsoid(collection, name, center, scale, mat, segments=16, rings=10):
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
    faces = []
    for i in range(segments):
        faces.append((0, 1+i, 1+(i+1) % segments))
    for j in range(rings-2):
        a, b = 1+j*segments, 1+(j+1)*segments
        for i in range(segments):
            k = (i+1) % segments
            faces.append((a+i, b+i, b+k, a+k))
    last = 1+(rings-2)*segments
    for i in range(segments):
        faces.append((bottom, last+(i+1) % segments, last+i))
    return mesh_object(collection, name, verts, faces, mat)

def segment(collection, name, head, tail, radius, mat):
    """Rounded, tapered links make the articulation readable in solid view."""
    head, tail = Vector(head), Vector(tail)
    axis = tail-head
    rotation = axis.to_track_quat("Z", "Y")
    n = 12
    verts = []
    for fraction, width in ((0.02, .65), (.12, 1), (.78, .74), (.98, .45)):
        center = head + axis*fraction
        for i in range(n):
            phi = math.tau*i/n
            offset = rotation @ Vector((math.cos(phi)*radius*width, math.sin(phi)*radius*width, 0))
            verts.append(center+offset)
    faces = [tuple(reversed(range(n)))]
    for j in range(3):
        for i in range(n):
            k=(i+1) % n
            faces.append((j*n+i, j*n+k, (j+1)*n+k, (j+1)*n+i))
    faces.append(tuple(range(3*n, 4*n)))
    return mesh_object(collection, name, verts, faces, mat)

def rigid_bind(obj, arm, bone):
    group = obj.vertex_groups.new(name=bone)
    group.add(list(range(len(obj.data.vertices))), 1.0, "REPLACE")
    obj.parent = arm
    modifier = obj.modifiers.new("Chimera Kit", "ARMATURE")
    modifier.object = arm
    obj["cs_preview"] = True

def shape(collection, name, kind, radius=1):
    if kind == "FOOT":
        verts = [(-.62, -.8, 0), (.62, -.8, 0), (.62, .8, 0), (-.62, .8, 0)]
    elif kind == "POLE":
        verts = [(1, 0, 0), (0, 1, 0), (-1, 0, 0), (0, -1, 0)]
    else:
        verts = [(math.cos(math.tau*i/32), math.sin(math.tau*i/32), 0) for i in range(32)]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([Vector(v)*radius for v in verts], [(i, (i+1) % len(verts)) for i in range(len(verts))], [])
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    obj.hide_render = True
    obj["cs_shape"] = True
    obj.hide_set(True)
    obj["cs_owned"] = True
    return obj
