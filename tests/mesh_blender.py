"""Run with Blender --background --factory-startup --python-exit-code 1 --python tests/mesh_blender.py.

Dog and Cat, hand and foot size, wing angle and height, the natural curve,
the shaped head, the T-pose arm rest and Build mesh from skeleton."""
import json
import math
from pathlib import Path
import sys
import time
import bpy
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import chimera_kit as cs
from chimera_kit import rig, motion, skin
cs.register()
scene=bpy.context.scene
p=scene.cs_settings
def check(condition,message):
    if not condition: raise AssertionError(message)
def head(arm,name): return arm.data.bones[name].head_local.copy()
def tail(arm,name): return arm.data.bones[name].tail_local.copy()
def length(arm,name): return arm.data.bones[name].length
def lowest(arm,flag="cs_preview"):
    graph=bpy.context.evaluated_depsgraph_get()
    low=1e9
    for obj in arm.children:
        if obj.type=="MESH" and obj.get(flag):
            evaluated=obj.evaluated_get(graph)
            low=min(low,min((evaluated.matrix_world @ Vector(c)).z for c in evaluated.bound_box))
    return low
def pose_point(arm,name,frames,end="tail"):
    out=[]
    for frame in frames:
        scene.frame_set(frame)
        out.append((arm.matrix_world @ getattr(arm.pose.bones[name],end)).copy())
    return out

# Dog and cat: both build, walk, and carry the tails that tell them apart.
p.species="DOG"
check(p.jaw and p.tail_frequency==2,"dog defaults: jaw and a quick wag")
dog=rig.build(bpy.context,p)
motion.generate(bpy.context,dog,p)
dog_tip=pose_point(dog,"tail.05",range(1,33))
p.species="CAT"
check(p.tail_frequency==1,"tail frequency should reset with the preset")
cat=rig.build(bpy.context,p)
motion.generate(bpy.context,cat,p)
cat_tip=pose_point(cat,"tail.08",range(1,33))
wag=lambda points:max(v.x for v in points)-min(v.x for v in points)
dog_tail=sum(length(dog,f"tail.{i:02d}") for i in range(1,6))
cat_tail=sum(length(cat,f"tail.{i:02d}") for i in range(1,9))
check(cat_tail>dog_tail*1.3,"a cat's tail should be longer than a dog's")
check(wag(dog_tip)/dog_tail>wag(cat_tip)/cat_tail*1.5,"a dog should wag its tail harder than a cat")
check(head(dog,"spine.01").z>head(cat,"spine.01").z,"a dog should stand taller than a cat")
for arm in (dog,cat):
    arm.animation_data.action=None
    for bone in arm.pose.bones:
        bone.location=(0,0,0); bone.rotation_euler=(0,0,0)
    bpy.context.view_layer.update()
    check(-.01<lowest(arm)<.03,f"{arm.name} should stand on the ground: {lowest(arm):.3f}")

# Hand and foot size.
p.species="BIPED"
plain=rig.build(bpy.context,p)
p.hand_size,p.foot_length,p.foot_thickness=2.0,2.0,2.0
big=rig.build(bpy.context,p)
check(abs(length(big,"hand.L")/length(plain,"hand.L")-2)<.01,"hand should double")
check(abs(length(big,"index.01.L")/length(plain,"index.01.L")-2)<.01,"fingers should grow with the hand")
check((head(big,"hand.L")-head(plain,"hand.L")).length<1e-6,"the wrist should stay put")
check(abs(length(big,"toe.L")/length(plain,"toe.L")-2)<.01,"toes should double")
check(head(big,"leg.01.L.foot").z>head(plain,"leg.01.L.foot").z*1.9,"a bigger flat foot should raise the ankle")
check((tail(big,"leg.01.L.lower")-head(big,"leg.01.L.foot")).length<1e-6,"shin should still meet the ankle")
check(lowest(big)>-.005,"giant feet should not sink into the floor")
check(json.loads(big["cs_limbs"])[0]["reach"]<json.loads(plain["cs_limbs"])[0]["reach"],"leg reach should follow the raised ankle")
motion.generate(bpy.context,big,p)
ankles=pose_point(big,"leg.01.L.foot",range(1,33),"head")
check(min(v.z for v in ankles)>head(big,"leg.01.L.foot").z-.02,"a giant-footed walk should keep its feet above the floor")
p.hand_size,p.foot_length,p.foot_thickness=1.0,1.0,1.0
# Foot length and thickness are separate: a long foot stays low, a thick foot stays short.
p.foot_length=2.0
long_foot=rig.build(bpy.context,p)
check(abs(length(long_foot,"toe.L")/length(plain,"toe.L")-2)<.01,"foot length should double the toes")
check(abs(head(long_foot,"leg.01.L.foot").z-head(plain,"leg.01.L.foot").z)<1e-4,"a longer foot should not raise the ankle")
check(abs(long_foot.data.bones["toe.L"]["cs_box"][0]-plain.data.bones["toe.L"]["cs_box"][0])<1e-4,"a longer foot should not get wider")
p.foot_length,p.foot_thickness=1.0,2.0
thick_foot=rig.build(bpy.context,p)
check(abs(length(thick_foot,"toe.L")-length(plain,"toe.L"))<.01,"a thicker foot should not get longer")
check(thick_foot.data.bones["toe.L"]["cs_box"][0]>plain.data.bones["toe.L"]["cs_box"][0]*1.9,"a thicker foot should get wider")
check(head(thick_foot,"leg.01.L.foot").z>head(plain,"leg.01.L.foot").z*1.5,"a thicker flat foot should raise the ankle")
p.foot_thickness=1.0
p.species="HORSE"
horse=rig.build(bpy.context,p)
p.foot_length=p.foot_thickness=2.5
hoofed=rig.build(bpy.context,p)
check(length(hoofed,"toe.01.L")>length(horse,"toe.01.L")*2.4,"an animal on its toes should grow its toes")
check((head(hoofed,"leg.01.L.foot")-head(horse,"leg.01.L.foot")).length<1e-6,"its hock should stay where it was")
check(lowest(hoofed)>-.01,"big hooves should stay on the floor")
p.foot_length=p.foot_thickness=1.0

# Wing angle and height.
p.species="EAGLE"
flat=rig.build(bpy.context,p)
p.wing_angle=.8
raised=rig.build(bpy.context,p)
check(tail(raised,"wingtip.L").z>tail(flat,"wingtip.L").z+.4,"wing angle should lift the wingtips")
check(abs(tail(raised,"wingtip.L").z-tail(raised,"wingtip.R").z)<1e-5 and
      abs(tail(raised,"wingtip.L").x+tail(raised,"wingtip.R").x)<1e-5,"both wings should tilt alike")
check((head(raised,"wing.L")-head(flat,"wing.L")).length<1e-6,"the wing should tilt about its root")
check(abs(length(raised,"wing.L")-length(flat,"wing.L"))<1e-5,"tilting should not stretch the wing")
p.wing_angle,p.wing_height=0.0,1.0
high=rig.build(bpy.context,p)
check(head(high,"wing.L").z>head(flat,"wing.L").z+.2,"wing height should move the roots up")
p.wing_height=0.0
p.wing_angle=.8
motion.generate(bpy.context,raised,p)
tips=pose_point(raised,"wingtip.L",range(1,33))
check(max(v.z for v in tips)-min(v.z for v in tips)>.1,"angled wings should still beat")
p.wing_angle=0.0

# Natural curve: joints inside a chain move, its two ends do not.
p.species="BIPED"
p.curve=0.0
straight=rig.build(bpy.context,p)
p.curve=1.0
curved=rig.build(bpy.context,p)
check(all(abs(head(straight,f"spine.{i:02d}").y)<1e-6 for i in (1,2,3)),"curve 0 should be a straight spine")
check(head(curved,"spine.02").y<-.008 and head(curved,"spine.03").y>.008,"the back should hollow low and round high")
for name in ("spine.01","head","arm.L","leg.01.L.upper"):
    check((head(curved,name)-head(straight,name)).length<1e-6,name+" should not move with the curve")
check((tail(curved,"spine.03")-tail(straight,"spine.03")).length<1e-6,"the top of the spine should stay put")
p.species="GIRAFFE"
p.curve=0.0
stiff=rig.build(bpy.context,p)
p.curve=1.0
supple=rig.build(bpy.context,p)
check((head(supple,"head")-head(stiff,"head")).length<1e-6,"the head should stay where the neck ends")
check(max((head(supple,f"neck.{i:02d}")-head(stiff,f"neck.{i:02d}")).length for i in (2,3,4,5))>.02,"a long neck should take an S")
check((tail(supple,"tail.03")-tail(stiff,"tail.03")).length>.01,"the tail should curve")
check(p.curve==1.0,"curve should default to 1 after choosing a preset")

# Shaped head.
p.species="BIPED"
check(p.head_shape==1.0,"people should get the shaped head")
shaped=rig.build(bpy.context,p)
skulls=[o for o in shaped.children if "skull" in o.name]
check(len(skulls)==1,"biped should draw one skull")
xs=sorted(v.co.z for v in skulls[0].data.vertices)
by_height={}
for v in skulls[0].data.vertices: by_height.setdefault(round(v.co.z,4),[]).append(v.co)
rows=[by_height[z] for z in sorted(by_height)]
width=lambda row:max(c.x for c in row)-min(c.x for c in row)
middle=lambda row:sum(c.y for c in row)/len(row)
check(width(rows[0])<width(rows[4])*.5,"the chin should be much narrower than the cranium")
check(middle(rows[0])<middle(rows[4])-.02,"the chin should sit forward of the back of the skull")
p.head_shape=0.0
blocky=rig.build(bpy.context,p)
check(not [o for o in blocky.children if "skull" in o.name],"head shape 0 should be the plain block")
check("cs_box" in blocky.data.bones["head"].keys(),"a block head keeps its box")
p.head_shape=1.0
p.species="HORSE"
check(p.head_shape==0.0,"animals keep their own heads")

# Arm rest pose: T-pose at rest, arms at the sides in a cycle.
p.species="BIPED"
p.arm_raise=0.0
relaxed=rig.build(bpy.context,p)
p.arm_raise=1.0
tee=rig.build(bpy.context,p)
check(abs(tail(tee,"forearm.L").z-head(tee,"arm.L").z)<.01,"T-pose arms should be level")
check(tail(tee,"forearm.L").x>head(tee,"arm.L").x+.4,"T-pose arms should reach out sideways")
check(abs(tail(tee,"forearm.L").x+tail(tee,"forearm.R").x)<1e-5,"both arms should lift alike")
check(abs(length(tee,"forearm.L")-length(relaxed,"forearm.L"))<1e-5,"lifting should not stretch the arm")
check(tail(tee,"index.03.L").x>tail(tee,"hand.L").x,"fingers should follow the arm out")
motion.generate(bpy.context,relaxed,p)
motion.generate(bpy.context,tee,p)
frames=range(1,33)
a=pose_point(relaxed,"forearm.L",frames)
b=pose_point(tee,"forearm.L",frames)
check(max((u-relaxed.matrix_world.translation-(v-tee.matrix_world.translation)).length for u,v in zip(a,b))<.02,
      "a T-posed biped should walk with its arms exactly where a relaxed one carries them")
p.motion_type="PUNCH"
motion.generate(bpy.context,relaxed,p)
motion.generate(bpy.context,tee,p)
a=pose_point(relaxed,"forearm.R",range(1,41))
b=pose_point(tee,"forearm.R",range(1,41))
check(max((u-relaxed.matrix_world.translation-(v-tee.matrix_world.translation)).length for u,v in zip(a,b))<.03,
      "a punch should land the same from a T-pose rest")
p.motion_type="WALK"
p.arm_raise=0.0

# Build mesh from skeleton: every preset.
report=[]
gaps=[]
for item in cs.PRESETS:
    species=item[0]
    p.species=species
    arm=rig.build(bpy.context,p)
    started=time.time()
    obj=skin.build(bpy.context,arm,p)
    took=time.time()-started
    mesh=obj.data
    deform={b.name for b in arm.data.bones if b.use_deform}
    names=[g.name for g in obj.vertex_groups]
    check(set(names)<=deform,f"{species}: mesh groups must be deform bones: {set(names)-deform}")
    check(not any(n.startswith("~") for n in names),species+": working groups left behind")
    for v in mesh.vertices:
        total=sum(g.weight for g in v.groups)
        check(abs(total-1)<1e-3,f"{species}: vertex {v.index} weights sum to {total:.3f}")
        check(all(math.isfinite(c) for c in v.co),species+": non-finite vertex")
    mechanical=species.startswith("MECH")
    check(obj["cs_skin_style"]==("JOINTED" if mechanical else "ORGANIC"),species+": wrong mesh style")
    quads=sum(1 for f in mesh.polygons if len(f.vertices)==4)
    check(quads>len(mesh.polygons)*.75,f"{species}: only {quads} of {len(mesh.polygons)} faces are quads")
    check(any(m.type=="ARMATURE" and m.object==arm for m in obj.modifiers),species+": not skinned to its rig")
    check(all(o.hide_get() for o in arm.children if o.get("cs_preview")),species+": mannequin should hide behind the mesh")
    low=lowest(arm,"cs_skin")
    check(low>-.02,f"{species}: built mesh dips {-low:.3f} m under the floor")
    # The mesh should be about the size of the mannequin it replaces.
    graph=bpy.context.evaluated_depsgraph_get()
    def bounds(flag):
        low_,high_=Vector((1e9,)*3),Vector((-1e9,)*3)
        for o in arm.children:
            if o.type=="MESH" and o.get(flag):
                for c in o.bound_box:
                    w=o.matrix_world @ Vector(c)
                    low_=Vector(map(min,low_,w)); high_=Vector(map(max,high_,w))
        return high_-low_
    size_mesh,size_figure=bounds("cs_skin"),bounds("cs_preview")
    for axis in range(3):
        ratio=size_mesh[axis]/max(size_figure[axis],1e-6)
        check(.6<ratio<1.45,f"{species}: mesh is {ratio:.2f}x the mannequin along axis {axis}")
    report.append((species,len(mesh.vertices),round(took,2)))
    if not mechanical:
        # One connected skin, apart from membranes and eyeballs.
        edges={}
        for f in mesh.polygons:
            for key in f.edge_keys: edges[key]=edges.get(key,0)+1
        open_edges=sum(1 for n in edges.values() if n==1)
        loose=len(geo_panels:=__import__("chimera_kit").geometry.wing_panels(arm.data.bones))
        gaps.append((species,open_edges-loose*4 if loose else open_edges))
check(all(count<=12 for _,count in gaps),"a skin should be closed but for a few edges at crowded branches: "+str([g for g in gaps if g[1]>12]))
check(max(t for _,_,t in report)<3.0,"a mesh should build in a moment: "+str(max(report,key=lambda r:r[2])))

# Three loops at a joint, and weights that blend across it.
p.species="BIPED"
p.arm_raise=1.0
biped=rig.build(bpy.context,p)
obj=skin.build(bpy.context,biped,p)
index={g.name:g.index for g in obj.vertex_groups}
def share(v,name):
    return next((g.weight for g in v.groups if g.group==index[name]),0.0)
upper,lower="leg.01.L.upper","leg.01.L.lower"
knee=head(biped,lower)
bands={}
for v in obj.data.vertices:
    a,b=share(v,upper),share(v,lower)
    if a>0 and b>0 and abs(a+b-1)<1e-3:
        bands.setdefault(round(a,2),[]).append(v.co.z)
check({.85,.5,.15}<=set(bands),"knee should carry three loops blending thigh into shin: "+str(sorted(bands)))
check(max(bands[.85])>knee.z>min(bands[.15]),"the three knee loops should straddle the joint")
check(all(len(bands[k])>=4 for k in (.85,.5,.15)),"each knee loop should be a full ring")
elbow_groups=sum(1 for v in obj.data.vertices if share(v,"arm.L")>0 and share(v,"forearm.L")>0)
check(elbow_groups>=12,"elbow should blend across three loops")
check("index.03.L" in index and "toe.L" in index and "head" in index,"fingers, toes and head should all be skinned")
# It follows the skeleton: arms come down in a walk, and the hand's vertices go with them.
motion.generate(bpy.context,biped,p)
hand=[v.index for v in obj.data.vertices if share(v,"hand.L")>.9]
check(hand,"hand should have its own vertices")
scene.frame_set(8)
graph=bpy.context.evaluated_depsgraph_get()
evaluated=obj.evaluated_get(graph)
moved=evaluated.matrix_world @ evaluated.data.vertices[hand[0]].co if len(evaluated.data.vertices)==len(obj.data.vertices) else None
obj.modifiers["Smooth"].show_viewport=False
graph=bpy.context.evaluated_depsgraph_get()
evaluated=obj.evaluated_get(graph)
moved=evaluated.matrix_world @ evaluated.data.vertices[hand[0]].co
rest=obj.matrix_world @ obj.data.vertices[hand[0]].co
check(moved.z<rest.z-.3,"the skinned hand should come down with the arm in a walk")
obj.modifiers["Smooth"].show_viewport=True

# The mesh follows the body sliders until it is handed over.
p.body_width=1.6
wider=rig.rebuild(bpy.context,biped,p)
followed=skin.find(wider)
check(followed is not None,"the mesh should be rebuilt with the body")
span=lambda o:max(v.co.x for v in o.data.vertices if abs(v.co.z-1.3)<.08 and abs(v.co.x)<.4)
check(sum(1 for o in bpy.data.objects if o.get("cs_skin") and o.parent==wider)==1,"the old mesh should be replaced, not left behind")
mine=skin.keep(wider)
check(not mine.get("cs_skin") and not mine.get("cs_owned") and skin.find(wider) is None,"kept mesh should belong to the artist")
count=len(mine.data.vertices)
p.body_width=1.0
again=rig.rebuild(bpy.context,wider,p)
check(mine.name in bpy.data.objects and len(mine.data.vertices)==count,"a kept mesh must survive a rebuild untouched")
check(any(m.type=="ARMATURE" and m.object==again for m in mine.modifiers),"a kept mesh should follow the new skeleton")
check(skin.find(again) is None,"a kept mesh should not be rebuilt")

# The operator: Arms A-pose (the default) sets the rest 45 degrees out.
p.species="BIPED"
p.arm_raise=0.0
biped=rig.build(bpy.context,p)
check(p.skin_pose=="A","A-pose should be the default arm rest for building a mesh")
check(bpy.ops.chimera_kit.skin(action="BUILD")=={"FINISHED"},"A-pose build failed")
biped=rig.active(bpy.context)
reach=tail(biped,"forearm.L")-head(biped,"arm.L")
check(abs(math.degrees(math.atan2(reach.x,-reach.z))-45)<1.5,"A-pose should hold the arms 45 degrees out: "+str(reach))
check(skin.layout_source(biped,p) is None,"an A-pose rig is meshed as it stands")

# The operator: T-pose, rebuild, hand over, delete.
p.species="HUMAN"
p.arm_raise=0.0
human=rig.build(bpy.context,p)
motion.generate(bpy.context,human,p)
p.skin_pose="T"
check(bpy.ops.chimera_kit.skin(action="BUILD")=={"FINISHED"},"build operator failed")
human=rig.active(bpy.context)
check(p.arm_raise==1.0 and rig.stored_settings(human)["arm_raise"]==1.0,"T-pose first should lift the arm rest pose")
check(abs(tail(human,"forearm.L").z-head(human,"arm.L").z)<.01,"the rebuilt rest pose should be a T")
check(skin.find(human) is not None and human.animation_data.action,"mesh built and cycle kept")
wrists=pose_point(human,"forearm.L",range(1,33))
check(max(v.z for v in wrists)<(human.matrix_world @ head(human,"arm.L")).z-.1,"the regenerated walk should carry the arms down")
p.skin_style="JOINTED"
check(bpy.ops.chimera_kit.skin(action="BUILD")=={"FINISHED"},"rebuild as hard parts failed")
hard=skin.find(human)
check(hard["cs_skin_style"]=="JOINTED" and all(len(v.groups)==1 for v in hard.data.vertices),"hard parts should be rigid, one bone each")
p.skin_style="AUTO"
check(bpy.ops.chimera_kit.skin(action="DELETE")=={"FINISHED"} and skin.find(human) is None,"delete operator failed")
check(not any(o.hide_get() for o in human.children if o.get("cs_preview")),"deleting the mesh should bring the mannequin back")
p.arm_raise=0.0

# Body length reaches upright creatures too.
p.species="HUMAN"
short=rig.build(bpy.context,p)
p.body_length=2.0
tall=rig.build(bpy.context,p)
grown=tail(tall,"spine.02").z-tail(short,"spine.02").z
check(grown>.3,"an upright trunk should grow with body length")
for name in ("arm.L","neck","head"):
    check(abs(head(tall,name).z-head(short,name).z-grown)<1e-4,name+" should ride up with a longer trunk")
check((head(tall,"leg.01.L.upper")-head(short,"leg.01.L.upper")).length<1e-6,"legs should not move with body length")
p.body_length=1.0

# Chest width and hip width: side to side only, and the limbs go with them.
p.species="BIPED"
base=rig.build(bpy.context,p)
p.chest_width,p.hip_width=1.5,1.0
broad=rig.build(bpy.context,p)
check(head(broad,"arm.L").x>head(base,"arm.L").x*1.25,"a wider chest should carry the shoulders out")
check(abs(head(broad,"arm.L").x+head(broad,"arm.R").x)<1e-5,"shoulders should stay symmetrical")
check(abs(length(broad,"arm.L")-length(base,"arm.L"))<1e-5 and (head(broad,"clavicle.L")-head(base,"clavicle.L")).length<1e-6,
      "the arm should move whole and the collarbone stretch from the chest")
check(broad.data.bones["spine.03"]["cs_box"][2]>base.data.bones["spine.03"]["cs_box"][2]*1.4,"the chest itself should widen")
check(abs(broad.data.bones["spine.03"]["cs_box"][3]-base.data.bones["spine.03"]["cs_box"][3])<1e-6,"chest depth should not change")
check((head(broad,"leg.01.L.upper")-head(base,"leg.01.L.upper")).length<1e-6,"chest width should leave the legs alone")
p.chest_width,p.hip_width=1.0,1.6
hippy=rig.build(bpy.context,p)
check(abs(head(hippy,"leg.01.L.upper").x/head(base,"leg.01.L.upper").x-1.6)<.01,"wider hips should carry the legs out")
shift=head(hippy,"leg.01.L.upper").x-head(base,"leg.01.L.upper").x
for name in ("leg.01.L.foot","CTRL-leg.01.L","POLE-leg.01.L","toe.L"):
    check(abs(head(hippy,name).x-head(base,name).x-shift)<1e-5,name+" should move with its leg")
check((head(hippy,"arm.L")-head(base,"arm.L")).length<1e-6,"hip width should leave the arms alone")
check(rig.validate(hippy)==[] if isinstance(rig.validate(hippy),list) else True,"wide-hipped rig should validate")
motion.generate(bpy.context,hippy,p)
knees=pose_point(hippy,"leg.01.L.lower",range(1,33),"head")
check(max(abs(v.x-knees[0].x) for v in knees)<.15,"wide hips should still walk with straight-tracking knees")
p.species="DOG"
p.chest_width=1.5
wide_dog=rig.build(bpy.context,p)
p.chest_width=1.0
plain_dog=rig.build(bpy.context,p)
check(head(wide_dog,"leg.01.L.upper").x>head(plain_dog,"leg.01.L.upper").x*1.3,"a dog's front legs should move out with its chest")
check((head(wide_dog,"leg.02.L.upper")-head(plain_dog,"leg.02.L.upper")).length<1e-6,"its hind legs should stay with the hips")
check(p.hip_width==1.0 and p.chest_width==1.0,"widths reset")

# The quad body: all quads, eight-sided limbs, muscle taper, loops gathered at the joints.
p.species="BIPED"
p.arm_raise=1.0
p.skin_smooth=0
p.skin_taper=1.0
model=rig.build(bpy.context,p)
cage=skin.build(bpy.context,model,p)
check(all(len(f.vertices)==4 for f in cage.data.polygons),"the biped's body should be quads only")
edges={}
for f in cage.data.polygons:
    for key in f.edge_keys: edges[key]=edges.get(key,0)+1
check(all(n==2 for n in edges.values()),"the biped's body should be one closed surface")
links={}
for a_,b_ in edges:
    links.setdefault(a_,set()).add(b_); links.setdefault(b_,set()).add(a_)
seen={0}; todo=[0]
while todo:
    for j in links[todo.pop()]:
        if j not in seen: seen.add(j); todo.append(j)
check(len(seen)==len(cage.data.vertices),"arms, legs and fingers should all be extruded from one body")
group={g.name:g.index for g in cage.vertex_groups}
def ring_at(bone_name,fraction,tolerance=.03):
    """Vertices of the loop around a bone at a fraction of its length."""
    bone=model.data.bones[bone_name]
    axis=(bone.tail_local-bone.head_local)
    found=[]
    for v in cage.data.vertices:
        if any(g.group==group[bone_name] and g.weight>.4 for g in v.groups):
            t=(v.co-bone.head_local).dot(axis)/axis.length_squared
            if abs(t-fraction)<tolerance:
                found.append((v.co-bone.head_local-axis*t).length)
    return found
belly=ring_at("leg.01.L.upper",.30)
knee_ring=ring_at("leg.01.L.upper",1.0)
check(len(belly)==8,f"a thigh loop should have eight sides, found {len(belly)}")
check(sum(belly)/len(belly)>1.2*sum(knee_ring)/max(1,len(knee_ring)),"the thigh should be fuller than the knee")
calf=ring_at("leg.01.L.lower",.28)
ankle=ring_at("leg.01.L.lower",1.0)
check(len(calf)==8 and sum(calf)/8>1.3*sum(ankle)/max(1,len(ankle)),"the calf should swell and the ankle narrow")
forearm=ring_at("forearm.L",.25)
wrist=ring_at("forearm.L",1.0)
check(len(forearm)==8 and sum(forearm)/8>1.12*sum(wrist)/max(1,len(wrist)),"the forearm should taper to the wrist")
def loops_along(bone_name):
    bone=model.data.bones[bone_name]
    axis=(bone.tail_local-bone.head_local)
    stops=set()
    for v in cage.data.vertices:
        if any(g.group==group[bone_name] and g.weight>.4 for g in v.groups):
            stops.add(round((v.co-bone.head_local).dot(axis)/axis.length_squared,2))
    return sorted(stops)
thigh_loops=loops_along("leg.01.L.upper")
middle=[t for t in thigh_loops if .15<t<.85]
check(1<=len(middle)<=2,"the length of the thigh should carry one or two loops: "+str(thigh_loops))
near_knee=[t for t in thigh_loops if t>=.85]
check(len(near_knee)>=2 and near_knee[-1]-near_knee[0]<.12,"the knee's loops should sit close together: "+str(thigh_loops))
check(len(ring_at("index.02.L",.5,.45))>=4,"fingers should be four-sided")
p.skin_taper=0.0
straight=skin.build(bpy.context,model,p)
cage=straight
group={g.name:g.index for g in cage.vertex_groups}
flat=ring_at("leg.01.L.upper",.30)
check(sum(flat)/len(flat)<sum(belly)/len(belly)*.93,"muscle taper 0 should take the swell out of the thigh")
p.skin_taper=1.0
p.skin_smooth=1
p.arm_raise=0.0
for species in ("DOG","HORSE","TREX","HUMAN"):
    p.species=species
    animal=rig.build(bpy.context,p)
    body=skin.build(bpy.context,animal,p)
    counts={}
    for f in body.data.polygons:
        for key in f.edge_keys: counts[key]=counts.get(key,0)+1
    check(all(len(f.vertices)==4 for f in body.data.polygons) and all(n==2 for n in counts.values()),
          species+": body should be a closed all-quad surface")

# Arms resting at the sides: the mesh is laid out in a T and lowered, so the shoulder
# rolls over into the arm and the hand still hangs at the end of the arm.
p.species="BIPED"
p.arm_raise=0.0
relaxed=rig.build(bpy.context,p)
check(skin.layout_source(relaxed,p) is not None,"a biped with relaxed arms should be meshed from an A-pose layout")
body=skin.build(bpy.context,relaxed,p)
counts={}
for f in body.data.polygons:
    for key in f.edge_keys: counts[key]=counts.get(key,0)+1
check(all(n==2 for n in counts.values()),"relaxed biped: body should be closed")
group={g.name:g.index for g in body.vertex_groups}
hand=[v.co for v in body.data.vertices if any(g.group==group["hand.L"] and g.weight>.9 for g in v.groups)]
wrist=relaxed.data.bones["hand.L"].head_local
check(hand and min((c-wrist).length for c in hand)<.08,"relaxed biped: the hand should be lowered with the arm")
shoulder=relaxed.data.bones["arm.L"].head_local
check(max(c.z for c in (v.co for v in body.data.vertices) if c.x>shoulder.x)<shoulder.z+.1,"relaxed biped: nothing should stand up over the shoulder")

# A ring with no hint of its own (an arm's collar) takes its frame from the next one that has
# one, so the bridge between them does not twist.
from mathutils import Vector as _V
from chimera_kit import quads as _quads
frames=_quads.frames_for([dict(pos=_V((0,0,0))),dict(pos=_V((1,0,-.4)),hint=_V((.3,.6,.75))),dict(pos=_V((2,0,-1)),hint=_V((.3,.6,.75)))],None)
check(abs(frames[0][1].dot(frames[1][1]))>.98,"a collar ring should share the arm's frame: "+str(frames[0][1])+" "+str(frames[1][1]))

# Human base models from the template: 01 Low and 02 Base, fitted, closed, all quads, skinned.
for species in ("BIPED","HUMAN"):
    p.species=species
    p.arm_raise=0.0
    body_rig=rig.build(bpy.context,p)
    for level,count in (("LOW",741),("BASE",1591)):
        p.skin_base=level
        obj=skin.build(bpy.context,body_rig,p)
        mesh=obj.data
        check(obj.get("cs_skin_base")==level,f"{species} {level}: the template should be used")
        check(len(mesh.vertices)==count,f"{species} {level}: {len(mesh.vertices)} vertices, expected {count}")
        check(all(len(f.vertices)==4 for f in mesh.polygons),f"{species} {level}: all faces should be quads")
        edges={}
        for f in mesh.polygons:
            for key in f.edge_keys: edges[key]=edges.get(key,0)+1
        check(all(n==2 for n in edges.values()),f"{species} {level}: the body should be closed (eyes and mouth filled)")
        check(abs(min(v.co.z for v in mesh.vertices))<.002,f"{species} {level}: the soles should rest on the ground")
        top=max(v.co.z for v in mesh.vertices)
        check(abs(top-body_rig.data.bones["head"].tail_local.z)<.2,f"{species} {level}: the head should reach the top of the head bone, {top}")
        hand=body_rig.data.bones["hand.L"].tail_local
        check(min((v.co-hand).length for v in mesh.vertices)<.08,f"{species} {level}: the hand should reach the hand bone")
        grouped={g.name for g in obj.vertex_groups}
        check(grouped<= {b.name for b in body_rig.data.bones if b.use_deform},f"{species} {level}: weights only on deform bones: {grouped}")
        check(all(len(v.groups)>0 for v in mesh.vertices),f"{species} {level}: every vertex should be weighted")
p.species="DOG"
dog=rig.build(bpy.context,p)
p.skin_base="LOW"
obj=skin.build(bpy.context,dog,p)
check(obj.get("cs_skin_base")=="PROCEDURAL","a dog cannot wear the human template and is built procedurally")
p.skin_base="PROCEDURAL"

# Recipes carry the new settings.
check({"hand_size","foot_length","foot_thickness","wing_angle","wing_height","curve","head_shape","arm_raise","chest_width","hip_width"}<=set(rig.BUILD_KEYS),"new sliders must be build keys")
print("CHIMERA_KIT_MESH_PASSED",json.dumps(sorted(report,key=lambda r:-r[1])[:4]))
