"""Run with Blender --background --factory-startup --python-exit-code 1 --python tests/cycles_blender.py."""
import json
import math
import struct
from pathlib import Path
import sys
import bpy
from mathutils import Vector, Matrix
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import character_studio_blender as cs
from character_studio_blender import rig, motion
cs.register()
scene=bpy.context.scene
p=scene.cs_settings
output=ROOT/"tests"/"output"
output.mkdir(exist_ok=True)
def check(condition,message):
    if not condition: raise AssertionError(message)
def world(arm,name,tail=False):
    bone=arm.pose.bones[name]
    return arm.matrix_world @ (bone.tail if tail else bone.head)
def sample(arm,name,frames,tail=False):
    out=[]
    for frame in frames:
        scene.frame_set(frame)
        out.append(world(arm,name,tail).copy())
    return out

p.species="BIPED"
p.cycle_frames=40
p.cycles=2
biped=rig.build(bpy.context,p)
frames=range(1,41)
left,right="CTRL-leg.01.L","CTRL-leg.01.R"

# Idle: feet never move, the body breathes, and the action loops.
p.motion_type="IDLE"
idle=motion.generate(bpy.context,biped,p)
check(idle.name.endswith("Idle"),"idle action name: "+idle.name)
feet=sample(biped,left,frames)
check(max((v-feet[0]).length for v in feet)<1e-6,"idle feet move")
chest=sample(biped,"spine.03",frames,True)
check(max((v-chest[0]).length for v in chest)>.002,"idle body is frozen")
scene.frame_set(1); a=world(biped,"head",True).copy(); scene.frame_set(41); b=world(biped,"head",True)
check((a-b).length<1e-5,"idle does not loop")

# Jump: crouch first, then both feet leave the ground and come back.
p.motion_type="JUMP"
p.jump_height=.8
jump=motion.generate(bpy.context,biped,p)
rest=biped.data.bones["pelvis"].head_local.z
hips=[v.z for v in sample(biped,"pelvis",frames)]
feet=[v.z for v in sample(biped,left,frames)]
check(min(hips[:10])<hips[0]-.08,"no crouch before the jump")
check(max(hips)>rest+.3,"hips do not rise")
check(max(feet)-feet[0]>.4 and abs(feet[-1]-feet[0])<.02,"feet do not leave the ground and return")
check(hips.index(min(hips[:12]))<feet.index(max(feet)),"crouch must come before the flight")
p.jump_height=1.6
motion.generate(bpy.context,biped,p,live=True)
check(max(v.z for v in sample(biped,left,frames))-feet[0]>.9,"jump height slider has no effect")
p.travel=True
motion.generate(bpy.context,biped,p,live=True)
track=sample(biped,"CTRL-root",range(1,81))
check(abs((track[0]-track[-1]).y)>1.5,"travelling jump does not cover ground")
check((track[0]-track[8]).length<1e-6,"root slides during the crouch")
p.travel=False

# Punch: the fist travels forward to about shoulder height; the other side stays back.
p.motion_type="PUNCH"
p.strike_side="R"
motion.generate(bpy.context,biped,p)
fist=sample(biped,"hand.R",frames,True)
other=sample(biped,"hand.L",frames,True)
shoulder=biped.data.bones["arm.R"].head_local
reach=min(v.y for v in fist)
check(reach<fist[0].y-.35,"punching fist does not extend forward")
check(min(v.y for v in other)>reach+.15,"guard hand travels as far as the punch")
strike=min(fist,key=lambda v:v.y)
check(abs(strike.z-shoulder.z)<.25,f"punch height {strike.z:.2f} vs shoulder {shoulder.z:.2f}")
p.strike_side="ALT"
motion.generate(bpy.context,biped,p,live=True)
first=min(v.y for v in sample(biped,"hand.L",range(1,41),True))
second=min(v.y for v in sample(biped,"hand.R",range(41,81),True))
check(first<fist[0].y-.35 and second<fist[0].y-.35,"alternate does not switch sides")

# Kick: one foot swings forward and up, the other stays planted.
p.motion_type="KICK"
p.strike_side="L"
motion.generate(bpy.context,biped,p)
kick=sample(biped,left,frames)
support=sample(biped,right,frames)
check(min(v.y for v in kick)<kick[0].y-.5 and max(v.z for v in kick)>kick[0].z+.4,"kicking foot does not strike")
check(max((v-support[0]).length for v in support)<1e-6,"support foot moves")
ankle=sample(biped,"leg.01.L.foot",frames)
check(max((a-b).length for a,b in zip(ankle,kick))<.03,"kick is out of the leg's reach")

# Run style leans forward and lengthens the stride.
p.motion_type="WALK"
p.tuning_preset="RUN"
check(bpy.ops.character_studio.motion_style()=={"FINISHED"},"run style")
check(p.body_lean>.1 and p.stride>.8 and p.cycle_frames<24,"run style values")
motion.generate(bpy.context,biped,p)
scene.frame_set(3)
up=biped.pose.bones["pelvis"].matrix.to_3x3() @ biped.data.bones["pelvis"].matrix_local.to_3x3().inverted() @ Vector((0,0,1))
check(up.y<-.1,"run does not lean forward")
p.tuning_preset="NEUTRAL"
bpy.ops.character_studio.motion_style()

# Every generated cycle exports as its own clip.
p.io_path=str(output/"biped_cycles.glb")
check(bpy.ops.character_studio.export(format="GLB")=={"FINISHED"},"GLB export")
payload=(output/"biped_cycles.glb").read_bytes()
gltf=json.loads(payload[20:20+struct.unpack_from("<I",payload,12)[0]])
names={a.get("name") for a in gltf.get("animations",[])}
check({"Idle","Jump","Punch","Kick"}<=names,"cycles missing from GLB: "+str(names))
check(not biped.animation_data.nla_tracks,"temporary export tracks left behind")
check(biped.animation_data.action is not None,"active action lost by export")
p.io_path=str(output/"biped_cycles.fbx")
check(bpy.ops.character_studio.export(format="FBX")=={"FINISHED"},"FBX export")

# Swimmers: no legs, the body waves, and travel moves them forward.
for species,axis in (("SHARK",0),("DOLPHIN",2)):
    p.species=species
    p.cycle_frames=32
    arm=rig.build(bpy.context,p)
    check(json.loads(arm["cs_limbs"])==[] and not rig.validate(arm),species+": should be legless and valid")
    p.travel=True
    action=motion.generate(bpy.context,arm,p)
    tail=sample(arm,"caudal",range(1,33),True)
    root=sample(arm,"CTRL-root",range(1,33))
    sweep=max(v[axis]-root[i][axis] for i,v in enumerate(tail))-min(v[axis]-root[i][axis] for i,v in enumerate(tail))
    other=2-axis
    cross=max(v[other]-root[i][other] for i,v in enumerate(tail))-min(v[other]-root[i][other] for i,v in enumerate(tail))
    check(sweep>.15 and sweep>cross*2,f"{species}: tail beat {sweep:.2f} across {cross:.2f}")
    check(abs(root[-1].y-root[0].y)>.3,species+": does not swim forward")
    p.travel=False
    p.motion_type="IDLE"
    motion.generate(bpy.context,arm,p)
    p.motion_type="WALK"

# Footsteps steer the walk: turn the later steps and the body follows; raise them and it climbs.
p.species="BIPED"
p.cycle_frames=24
p.cycles=6
p.travel=True
walker=rig.build(bpy.context,p)
motion.generate(bpy.context,walker,p)
check(bpy.ops.character_studio.footprints(operation="CREATE")=={"FINISHED"},"create footsteps")
markers=sorted(motion.footprint_objects(walker),key=lambda o:o["cs_contact_frame"])
straight=motion.generate(bpy.context,walker,p,live=True)
end=p.start_frame+p.cycle_frames*p.cycles-2
scene.frame_set(end); baseline=world(walker,"pelvis").copy()
check(abs(baseline.x)<.02,"unedited footsteps should walk straight")
pivot=markers[len(markers)//2]
bpy.context.view_layer.objects.active=pivot
pivot.select_set(True)
check(bpy.ops.character_studio.footprints(operation="SELECT_AFTER")=={"FINISHED"},"select onward")
later=[o for o in markers if o.select_get()]
check(len(markers)//3<len(later)<len(markers),"select onward chose the wrong steps")
centre=pivot.matrix_world.translation.copy()
turn=Matrix.Translation(centre) @ Matrix.Rotation(math.radians(60),4,"Z") @ Matrix.Translation(-centre)
lift=0.0
for index,obj in enumerate(later):
    obj.matrix_world=Matrix.Translation((0,0,.05*index)) @ turn @ obj.matrix_world
bpy.context.view_layer.update()
motion.generate(bpy.context,walker,p,live=True)
scene.frame_set(end)
turned=world(walker,"pelvis").copy()
check(abs(turned.x-baseline.x)>.5,"body did not follow the turned footsteps")
check(turned.z>baseline.z+.15,"body did not climb with the raised footsteps")
forward=walker.pose.bones["CTRL-root"].matrix.to_3x3() @ walker.data.bones["CTRL-root"].matrix_local.to_3x3().inverted() @ Vector((0,-1,0))
heading=math.degrees(math.atan2(forward.x,-forward.y))
check(abs(abs(heading)-60)<8,f"heading {heading:.1f}° after a 60° turn")
# Feet still land on their markers.
last=later[-3]
scene.frame_set(int(round(last["cs_contact_frame"]))+2)
foot=world(walker,last["cs_limb"])
check((foot-last.matrix_world.translation).length<.02,"foot misses its edited footstep")
print("CHARACTER_STUDIO_CYCLES_PASSED")
cs.unregister()
