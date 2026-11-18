"""Run with Blender --background --factory-startup --python-exit-code 1 --python tests/parts_blender.py."""
import json
import math
from pathlib import Path
import sys
import bpy
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import chimera_kit as cs
from chimera_kit import rig, motion
cs.register()
scene=bpy.context.scene
p=scene.cs_settings
def check(condition,message):
    if not condition: raise AssertionError(message)
def tip(arm,name):
    return arm.matrix_world @ arm.pose.bones[name].tail
def track(arm,name,frames):
    out=[]
    for frame in frames:
        scene.frame_set(frame)
        out.append(tip(arm,name).copy())
    return out
def head_top(arm):
    """Highest point of any mannequin piece bound to the head."""
    top=-1e9
    for obj in arm.children:
        if obj.type=="MESH" and obj.vertex_groups and obj.vertex_groups[0].name=="head":
            top=max(top,max((obj.matrix_world @ v.co).z for v in obj.data.vertices))
    return top

# Antennae start on the surface of the head at any head size, in both mannequin styles.
for species in ("ALIEN","BIPED","HORSE","TREX","PANTHER"):
    for style in ("BOX","ROUND"):
        for size in (1.0,4.0):
            p.species=species
            p.mannequin_style=style
            p.head_size=size
            p.antennae=True
            arm=rig.build(bpy.context,p)
            base=(arm.matrix_world @ arm.data.bones["antenna.01.L"].head_local).z
            end=(arm.matrix_world @ arm.data.bones["antenna.03.L"].tail_local).z
            top=head_top(arm)
            check(base>top-.06*p.size*size,f"{species} {style} head {size}: antenna starts {top-base:.3f} m inside the head")
            check(end>top+.1,f"{species} {style} head {size}: antenna does not clear the head")
p.mannequin_style="BOX"
p.head_size=1.0
# Antenna length and links.
p.species="ALIEN"
p.antenna_length=4
p.antenna_links=9
arm=rig.build(bpy.context,p)
check("antenna.09.R" in arm.data.bones and "antenna.10.R" not in arm.data.bones,"antenna links")
length=sum(arm.data.bones[f"antenna.{k:02d}.L"].length for k in range(1,10))
check(abs(length-.22*p.size*4)<1e-4,f"antenna length {length:.3f}")
p.cycle_frames=32
motion.generate(bpy.context,arm,p)
swing=track(arm,"antenna.09.L",range(1,33))
moved=max((v-swing[0]).length for v in swing)
check(.05<moved<length,"nine-link antenna sway out of range: %.3f"%moved)
p.antenna_length,p.antenna_links=1,3

# Jaw: opens on some cycles only, by the chosen amount; closed at every cycle boundary.
p.species="TREX"
p.cycles=8
p.jaw_open=.5
p.jaw_chance=.5
rex=rig.build(bpy.context,p)
check(p.jaw and "jaw" in rex.data.bones,"t-rex should have a jaw by default")
motion.generate(bpy.context,rex,p)
def gape(frame):
    scene.frame_set(frame)
    jaw=rex.pose.bones["jaw"]
    rest=rex.pose.bones["head"].matrix.to_3x3() @ rex.data.bones["head"].matrix_local.to_3x3().inverted() @ (rex.data.bones["jaw"].tail_local-rex.data.bones["jaw"].head_local)
    return rest.angle(jaw.tail-jaw.head)
peaks=[max(gape(1+c*32+k) for k in range(32)) for c in range(8)]
opened=sum(1 for v in peaks if v>.4)
check(0<opened<8,f"jaw should open on some cycles, not {opened} of 8")
check(all(v<.01 or abs(v-.5)<.02 for v in peaks),"jaw opening does not match the slider: "+str([round(v,2) for v in peaks]))
check(all(gape(1+c*32)<1e-4 for c in range(8)),"jaw is not closed at cycle boundaries")
scene.frame_set(1+peaks.index(max(peaks))*32+16)
check(rex.pose.bones["jaw"].tail.z<rex.pose.bones["jaw"].head.z-.02,"jaw opens upward")
p.jaw_chance=1
motion.generate(bpy.context,rex,p,live=True)
check(all(max(gape(1+c*32+k) for k in range(32))>.4 for c in range(8)),"jaw chance 1 should open every cycle")
p.jaw_chance=0
motion.generate(bpy.context,rex,p,live=True)
check(max(gape(f) for f in range(1,257,3))<1e-4,"jaw chance 0 should keep the mouth shut")
p.jaw_chance=.5
# A jaw on creatures that have no built-in one, and none when switched off.
for species in ("HORSE","BIPED","SHARK","ALIEN"):
    p.species=species
    p.jaw=True
    arm=rig.build(bpy.context,p)
    jaw,head=arm.data.bones["jaw"],arm.data.bones["head"]
    check(jaw.parent==head and jaw.tail_local.y<jaw.head_local.y,species+": jaw should hang from the head and point forward")
    motion.generate(bpy.context,arm,p)
p.species="TREX"
p.jaw=False
check("jaw" not in rig.build(bpy.context,p).data.bones,"jaw switch off ignored")
p.cycles=4

# Wings: every style moves differently.
p.species="DRAGON"
p.cycle_frames=32
dragon=rig.build(bpy.context,p)
check(p.wing_style=="FLAP" and p.wing_flap>.3,"dragon wing defaults")
frames=range(1,33)
def wing_run(style,**options):
    p.wing_style=style
    for key,value in options.items(): setattr(p,key,value)
    motion.generate(bpy.context,dragon,p)
    # Measured relative to the chest the wings hang from, so body motion does not count.
    path=[]
    for frame in frames:
        scene.frame_set(frame)
        wing=dragon.pose.bones["wing.L"]
        parent=wing.parent
        carried=parent.matrix.to_3x3() @ parent.bone.matrix_local.to_3x3().inverted()
        path.append(carried.inverted() @ (dragon.pose.bones["wingtip.L"].tail-wing.head))
    span=sum(abs(v.x) for v in path)/len(path)
    def crossings(axis):
        values=[v[axis] for v in path]
        mean=sum(values)/len(values)
        return sum(1 for a,b in zip(values,values[1:]+values[:1]) if (a-mean)*(b-mean)<0)
    rise=max(v.z for v in path)-min(v.z for v in path)
    fore=max(v.y for v in path)-min(v.y for v in path)
    return dict(span=span,rise=rise,fore=fore,beats=crossings(2)/2)
flap=wing_run("FLAP",wing_frequency=1,wing_fold=0)
check(flap["rise"]>.5 and abs(flap["beats"]-1)<.6,"flap: "+str(flap))
# Both wings beat together: their local rotations are mirror images. (The tips
# themselves differ in world space because the chest they hang from twists.)
for frame in (5,13,22):
    scene.frame_set(frame)
    a,b=dragon.pose.bones["wing.L"].rotation_euler,dragon.pose.bones["wing.R"].rotation_euler
    check(abs(a.x-b.x)<1e-5 and abs(a.y+b.y)<1e-5 and abs(a.z+b.z)<1e-5,"wings do not beat together")
double=wing_run("FLAP",wing_frequency=3)
check(abs(double["beats"]-3)<.6,"beats per cycle ignored: "+str(double))
glide=wing_run("GLIDE",wing_frequency=1)
check(glide["rise"]<flap["rise"]*.25 and glide["span"]>flap["span"]*.9,"glide should hold the wings out: "+str(glide))
hover=wing_run("HOVER")
check(hover["beats"]>=2.4 and hover["fore"]>flap["fore"]*1.5,"hover should beat fast and sweep: "+str(hover))
flutter=wing_run("FLUTTER")
check(flutter["beats"]>=5 and flutter["rise"]<flap["rise"]*.7,"flutter should be quick and small: "+str(flutter))
folded=wing_run("FOLDED")
check(folded["span"]<flap["span"]*.6 and folded["rise"]<.1,"folded wings should sit close to the body: "+str(folded))
half=wing_run("FLAP",wing_fold=.5)
check(folded["span"]<half["span"]<flap["span"],"wing fold slider should tuck the wings part way: "+str(half))
p.wing_fold=0
# Birds walk with folded wings by default.
p.species="EAGLE"
check(p.wing_style=="FLAP" and p.wing_flap>.2,"eagle should flap by default")
eagle=rig.build(bpy.context,p)
motion.generate(bpy.context,eagle,p)
angles=[]
for frame in range(1,33):
    scene.frame_set(frame)
    angles.append(eagle.pose.bones["wing.L"].matrix_basis.to_quaternion().angle)
check(max(angles)-min(angles)>.2,"eagle wings should beat during the default walk")
scene.frame_set(1)
check(abs((eagle.matrix_world @ eagle.pose.bones["wingtip.L"].tail).x)>.8,"eagle wings should be spread during the default walk")

# Very long bodies and necks.
p.species="BRONTO"
bronto=rig.build(bpy.context,p)
check(not rig.validate(bronto) and len(json.loads(bronto["cs_limbs"]))==4,"brontosaurus")
front=min(b.head_local.y for b in bronto.data.bones if b.name.startswith("leg.01"))
check(bronto.data.bones["head"].head_local.y<front-1.0,"brontosaurus neck does not reach well past the front legs")
check(sum(1 for b in bronto.data.bones if b.name.startswith("tail."))==14,"brontosaurus tail")
motion.generate(bpy.context,bronto,p)
p.species="LIZARD"
p.body_length=40
p.spine_links=40
p.leg_pairs=3
p.neck_length=80
p.neck_links=20
eel=rig.build(bpy.context,p)
check(not rig.validate(eel),"40x body with an 80x neck failed to build")
spine=[b for b in eel.data.bones if b.name.startswith("spine.")]
check(len(spine)==40 and abs(spine[0].head_local.y-spine[-1].tail_local.y)>20,"body length 40 not applied")
motion.generate(bpy.context,eel,p)
# Wingspan and wing joints.
p.species="DRAGON"
p.body_length,p.spine_links,p.leg_pairs,p.neck_length,p.neck_links=1.35,5,2,1,1
base=rig.build(bpy.context,p)
span=abs(base.data.bones["wingtip.L"].tail_local.x)
p.wing_span=2.0
p.wing_links=5
wide=rig.build(bpy.context,p)
check(abs(abs(wide.data.bones["wingtip.L"].tail_local.x)/span-2)<.15,"wingspan 2 should double the reach")
names=[b.name for b in wide.data.bones]
check(all(n in names for n in ("wing.L","wingmid.1.L","wingmid.3.L","wingtip.L","wingrib.2.R")) and "wingmid.4.L" not in names,"five wing joints")
check(sum(1 for o in wide.children if o.name.endswith("wing membrane") or "wing membrane" in o.name)>=10,"membrane panels for a five-joint wing")
p.wing_style="FLAP"
motion.generate(bpy.context,wide,p)
# The tip trails the shoulder: their beats peak on different frames.
def peak(name):
    values=[]
    for frame in range(1,33):
        scene.frame_set(frame)
        values.append(abs(wide.pose.bones[name].matrix_basis.to_quaternion().angle))
    return values.index(max(values))
check(peak("wing.L")!=peak("wingtip.L"),"outer wing joints should lag the inner")
p.wing_style="FOLDED"
motion.generate(bpy.context,wide,p)
scene.frame_set(4)
check(abs((wide.matrix_world @ wide.pose.bones["wingtip.L"].tail).x)<span*1.2,"a five-joint wing should still fold in")
p.wing_span,p.wing_links=1.0,2
# Tail length.
p.species="PANTHER"
short=rig.build(bpy.context,p)
reach=lambda arm:max(b.tail_local.y for b in arm.data.bones if b.name.startswith("tail."))-min(b.head_local.y for b in arm.data.bones if b.name.startswith("tail."))
p.tail_length=3
check(abs(reach(rig.build(bpy.context,p))/reach(short)-3)<.05,"tail length 3 should triple the tail")
p.tail_length=1
# Trunk profile: default animals have a deeper chest than waist; sliders reshape it.
p.species="TREX"
rex=rig.build(bpy.context,p)
def girths(arm):
    out={}
    for obj in arm.children:
        if obj.type=="MESH" and obj.vertex_groups and obj.vertex_groups[0].name.startswith(("spine.","pelvis")):
            xs=[(obj.matrix_world @ v.co).x for v in obj.data.vertices]
            out[obj.vertex_groups[0].name]=max(xs)-min(xs)
    return out
g=girths(rex)
check(g["pelvis"]>g["spine.02"] and g["spine.04"]>g["spine.02"],"default trunk should narrow at the waist: "+str({k:round(v,2) for k,v in g.items()}))
pelvis=rex.data.bones["pelvis"]
check(abs(pelvis.tail_local.y-pelvis.head_local.y)>abs(pelvis.tail_local.z-pelvis.head_local.z)*3,"theropod pelvis should lie along the body")
p.belly_size=2.2
check(girths(rig.build(bpy.context,p))["spine.02"]>g["spine.02"]*1.8,"belly slider ignored")
p.species="HORSE"
horse=rig.build(bpy.context,p)
pelvis=horse.data.bones["pelvis"]
check(abs(pelvis.tail_local.y-pelvis.head_local.y)>.1 and abs(pelvis.tail_local.z-pelvis.head_local.z)<.02,"horse pelvis should lie along the body")
check(abs(pelvis.tail_local.y-horse.data.bones["leg.02.L.upper"].head_local.y)<.25,"horse pelvis should sit over the hind legs")
# Eyeballs: drawn as balls in both mannequin styles and wobbling with the walk.
for style in ("BOX","ROUND"):
    p.species="BIPED"
    p.mannequin_style=style
    p.eyes=True
    arm=rig.build(bpy.context,p)
    balls=[o for o in arm.children if "eye_white" in o.name or "eye_pupil" in o.name]
    check(len(balls)==4 and "eye.01.L" in arm.data.bones,style+": eyeballs missing")
    check(min((o.matrix_world @ v.co).z for o in balls for v in o.data.vertices)>head_top(arm)-.08,style+": eyeballs sunk into the head")
p.mannequin_style="BOX"
motion.generate(bpy.context,arm,p)
wobble=track(arm,"eye.01.L",range(1,33))
head=track(arm,"head",range(1,33))
relative=[a-b for a,b in zip(wobble,head)]
check(max((v-relative[0]).length for v in relative)>.004,"eyeballs do not wobble")
# Eye follow-through: stiff at 0, bouncing further and later as it rises.
def eye_wobble(amount):
    p.eye_bounce=amount
    motion.generate(bpy.context,arm,p)
    values=[]
    for frame in range(1,33):
        scene.frame_set(frame)
        values.append(arm.pose.bones["eye.01.L"].matrix_basis.to_quaternion().angle)
    return max(values),values.index(max(values))
stiff,_=eye_wobble(0)
soft,soft_peak=eye_wobble(.3)
loose,loose_peak=eye_wobble(.9)
check(stiff<1e-5 and soft>.1 and loose>soft*2,"eye follow-through amount: %.3f %.3f %.3f"%(stiff,soft,loose))
check(soft_peak!=loose_peak,"more eye follow-through should also change the delay")
p.eye_bounce=.25
p.eyes=False
# Frog, snake, worm and tadpole.
p.species="FROG"
frog=rig.build(bpy.context,p)
check(p.eyes and "eye.01.L" in frog.data.bones and len(json.loads(frog["cs_limbs"]))==4,"frog should have four legs and eyes")
hind=frog.data.bones["leg.02.L.upper"].length+frog.data.bones["leg.02.L.lower"].length
fore=frog.data.bones["leg.01.L.upper"].length+frog.data.bones["leg.01.L.lower"].length
check(hind>fore*1.4,"frog hind legs should be much longer than its front legs")
motion.generate(bpy.context,frog,p)
for species in ("SNAKE","WORM","TADPOLE"):
    p.species=species
    arm=rig.build(bpy.context,p)
    check(json.loads(arm["cs_limbs"])==[] and not rig.validate(arm),species+": should be legless and valid")
    check(not any(b.name.startswith("fin.") or b.name=="dorsal" for b in arm.data.bones) or species=="TADPOLE",species+": should have no fins")
    motion.generate(bpy.context,arm,p)
p.species="SNAKE"
snake=rig.build(bpy.context,p)
check(snake.data.bones["pelvis"].head_local.z<.1,"snake should lie on the ground")
motion.generate(bpy.context,snake,p)
# A travelling wave: neighbouring parts of the body peak at different times, and both sides bend.
def side_peak(name):
    xs=[]
    for frame in range(1,33):
        scene.frame_set(frame)
        xs.append((snake.matrix_world @ snake.pose.bones[name].tail).x)
    return xs.index(max(xs)),max(xs)-min(xs)
front,front_range=side_peak("spine.09")
middle,middle_range=side_peak("spine.04")
back,back_range=side_peak("tail.08")
check(len({front,middle,back})==3,"snake body should move as a travelling wave, not as one bend")
check(front_range>.1 and back_range>.1,"snake should bend along its whole length")
p.species="WORM"
worm=rig.build(bpy.context,p)
motion.generate(bpy.context,worm,p)
heights=[]
for frame in range(1,33):
    scene.frame_set(frame)
    heights.append(max((worm.matrix_world @ worm.pose.bones[n].tail).z for n in ("spine.03","spine.05","tail.02")))
check(max(heights)-min(heights)>.03,"worm should arch its back as it moves")
# Colour coding: left red, right green, blue body, yellow head.
p.species="BIPED"
p.eyes=False
biped=rig.build(bpy.context,p)
def colour(bone):
    obj=next(o for o in biped.children if o.type=="MESH" and o.vertex_groups and o.vertex_groups[0].name==bone)
    return tuple(obj.data.materials[0].diffuse_color[:3])
left,right,body,head=colour("arm.L"),colour("arm.R"),colour("spine.02"),colour("head")
check(left[0]>left[1]*3 and left[0]>left[2]*3,"left side should be red: "+str(left))
check(right[1]>right[0]*3 and right[1]>right[2],"right side should be green: "+str(right))
check(body[2]>body[0]*3 and body[2]>body[1]*2,"body should be blue: "+str(body))
check(head[0]>.6 and head[1]>.5 and head[2]<.2,"head should be yellow: "+str(head))
# Eye placement.
def eyes(**options):
    p.species="BIPED"
    p.eyes=True
    p.eye_spacing,p.eye_height,p.eye_forward=.48,0,.45
    for key,value in options.items(): setattr(p,key,value)
    arm=rig.build(bpy.context,p)
    a,b=arm.data.bones["eye.01.L"].tail_local,arm.data.bones["eye.01.R"].tail_local
    return a,b,arm
a,b,arm=eyes()
gap,height,front=a.x-b.x,a.z,a.y
a,b,_=eyes(eye_spacing=1.6)
check(a.x-b.x>gap*1.5,"eye spacing should move the eyes apart")
a,b,_=eyes(eye_spacing=0)
check(0<a.x-b.x<=gap+1e-6,"eye spacing 0 should bring the eyes together without overlapping")
a,b,_=eyes(eye_height=3)
check(a.z>height+.2,"eye height should raise the eyes")
a,b,arm=eyes(eye_height=-.5)
top=head_top(arm)
check(a.z<top-.03 and a.x>arm.data.bones["head"].head_local.x+.04,"negative eye height should put the eyes on the sides of the head")
a,b,_=eyes(eye_forward=1.2)
check(a.y<front-.02,"eye forward should move the eyes toward the face")
p.eyes=False
# Front and hind leg heights.
p.species="HORSE"
level=rig.build(bpy.context,p)
def heights(arm):
    return arm.data.bones["leg.01.L.upper"].head_local.z,arm.data.bones["leg.02.L.upper"].head_local.z
f0,h0=heights(level)
p.front_legs,p.hind_legs=1.5,.7
sloped=rig.build(bpy.context,p)
f1,h1=heights(sloped)
check(abs(f1/f0-1.5)<.02 and abs(h1/h0-.7)<.02,"front and hind leg heights not applied")
check(not rig.validate(sloped),"sloped horse invalid")
spine=[b for b in sloped.data.bones if b.name.startswith("spine.")]
check(spine[-1].tail_local.z>spine[0].head_local.z+.2,"back should slope up to the taller shoulders")
check(sloped.data.bones["head"].head_local.z>level.data.bones["head"].head_local.z+.2,"head should rise with the shoulders")
for name in ("leg.01.L.foot","leg.02.L.foot"):
    check(abs(sloped.data.bones[f"toe.0{name[5]}.L"].tail_local.z-level.data.bones[f"toe.0{name[5]}.L"].tail_local.z)<.03,"feet should stay on the floor")
motion.generate(bpy.context,sloped,p)
limb=json.loads(sloped["cs_limbs"])[0]
worst=0
for frame in range(1,33):
    scene.frame_set(frame)
    worst=max(worst,(sloped.pose.bones[limb["foot"]].head-sloped.pose.bones[limb["control"]].head).length)
check(worst<.01,"sloped horse cannot reach its foot targets: %.3f"%worst)
# Gorilla: taller in front, on knuckles and flat feet, no tail.
p.species="GORILLA"
gorilla=rig.build(bpy.context,p)
f,hd=heights(gorilla)
check(len(json.loads(gorilla["cs_limbs"]))==4 and f>hd*1.3,"gorilla should stand taller on its arms than its legs")
check(not any(b.name.startswith("tail.") for b in gorilla.data.bones) and "toe.01.L" not in gorilla.data.bones,"gorilla tail or hooves")
check(not rig.validate(gorilla),"gorilla invalid")
motion.generate(bpy.context,gorilla,p)
p.species="HORSE"
check(p.front_legs==1 and p.hind_legs==1,"leg heights should reset with the preset")
# Crawlers stay on the ground: no part of the snake or worm dips below it at any frame.
for species in ("SNAKE","WORM"):
    p.species=species
    crawler=rig.build(bpy.context,p)
    motion.generate(bpy.context,crawler,p)
    lowest=1e9
    highest=-1e9
    meshes=[o for o in crawler.children if o.type=="MESH" and o.get("cs_preview")]
    for frame in range(1,33,2):
        scene.frame_set(frame)
        graph=bpy.context.evaluated_depsgraph_get()
        for obj in meshes:
            evaluated=obj.evaluated_get(graph)
            for corner in evaluated.bound_box:
                z=(evaluated.matrix_world @ Vector(corner)).z
                lowest=min(lowest,z)
                highest=max(highest,z)
    check(lowest>-.012,f"{species} dips {-lowest:.3f} m below the ground")
    check(lowest<.03,f"{species} floats {lowest:.3f} m above the ground")
    if species=="WORM":
        check(highest>.2,"worm should hump up as it moves")
print("CHIMERA_KIT_PARTS_PASSED")
cs.unregister()
