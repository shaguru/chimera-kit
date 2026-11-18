"""Run with Blender --background --factory-startup --python-exit-code 1 --python tests/smoke_blender.py."""
import json
import math
from pathlib import Path
import sys
import bpy
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import character_studio_blender as cs
from character_studio_blender import rig, motion

cs.register()
p=bpy.context.scene.cs_settings
output=ROOT/"tests"/"output"
output.mkdir(exist_ok=True)
results=[]

def check(condition,message):
    if not condition: raise AssertionError(message)

for species,label,_ in cs.PRESETS:
    p.species=species
    p.cycle_frames=24
    p.cycles=2
    arm=rig.build(bpy.context,p)
    check(not rig.validate(arm),f"{species}: rig validation")
    limbs=json.loads(arm["cs_limbs"])
    bpy.context.view_layer.update()
    errors=[(arm.pose.bones[l["lower"]].tail-Vector(l["ankle"])).length for l in limbs]
    knee_errors=[(arm.pose.bones[l["lower"]].head-Vector(l["knee"])).length for l in limbs]
    check(max(errors,default=0)<.003,f"{species}: rest IK endpoints {errors}")
    check(max(knee_errors,default=0)<.025,f"{species}: rest knee orientation {knee_errors}")
    action=motion.generate(bpy.context,arm,p)
    check(list(motion.curves(action)),f"{species}: action has no curves")
    first={}
    bpy.context.scene.frame_set(1)
    for l in limbs: first[l["control"]]=arm.pose.bones[l["control"]].matrix.copy()
    bpy.context.scene.frame_set(25)
    check(max(((arm.pose.bones[n].matrix.translation-m.translation).length for n,m in first.items()),default=0)<.0001,
          f"{species}: discontinuous gait loop")
    for frame in range(1,49,3):
        bpy.context.scene.frame_set(frame)
        for bone in arm.pose.bones:
            check(all(math.isfinite(x) for row in bone.matrix for x in row),f"{species}: nonfinite pose")
    results.append({"species":species,"bones":len(arm.data.bones),"legs":len(limbs),
                    "rest_ik_error":max(errors,default=0),"rest_knee_error":max(knee_errors,default=0),"curves":len(list(motion.curves(action)))})
    for obj in arm.users_collection[0].all_objects:
        if obj is None: continue
        obj.hide_set(True)
        obj.hide_render=True

# Custom morphology and translated/rotated rigs must use local coordinates.
p.species="SPIDER"
p.leg_pairs=6
p.spine_links=8
p.tail_links=12
p.size=2.7
arm=rig.build(bpy.context,p)
check(len(json.loads(arm["cs_limbs"]))==12,"custom leg count")
arm.location=(2,1,.1)
arm.rotation_euler[2]=.35
p.travel=True
p.gait="TROT"
action=motion.generate(bpy.context,arm,p)
limb=json.loads(arm["cs_limbs"])[0]
positions=[]
for frame in (2,3,4,5,6):
    bpy.context.scene.frame_set(frame)
    positions.append(arm.matrix_world @ arm.pose.bones[limb["control"]].head)
check(max((point-positions[0]).length for point in positions)<.0001,"traveling stance foot slides")
root_start=arm.matrix_world @ arm.pose.bones["CTRL-root"].head
bpy.context.scene.frame_set(p.start_frame+p.cycle_frames*p.cycles)
root_end=arm.matrix_world @ arm.pose.bones["CTRL-root"].head
check((root_end-root_start).length>0.001,"traveling root did not advance")
motion.push_clip(arm)
check(arm.animation_data.action is None,"NLA push retains active action")
check(len(arm.animation_data.nla_tracks)==1,"NLA strip missing")
rig.reset(bpy.context,arm)
p.travel=False
motion.generate(bpy.context,arm,p)

# Export selection must exclude unrelated scene objects and other creatures.
p.io_path=str(output/"custom_spider.glb")
check(bpy.ops.character_studio.export(format="GLB")=={"FINISHED"},"GLB export failed")
check((output/"custom_spider.glb").stat().st_size>1000,"GLB empty")
import struct
payload=(output/"custom_spider.glb").read_bytes()
chunk_size=struct.unpack_from("<I",payload,12)[0]
gltf=json.loads(payload[20:20+chunk_size])
check(len(gltf.get("skins",[]))==1,"exported another creature skin")
check(gltf.get("animations"),"GLB contains no animation")
check(not any(n.get("name")=="Cube" for n in gltf.get("nodes",[])),"unrelated cube exported")
p.io_path=str(output/"custom_spider.fbx")
check(bpy.ops.character_studio.export(format="FBX")=={"FINISHED"},"FBX export failed")
check((output/"custom_spider.fbx").stat().st_size>1000,"FBX empty")
with open(output/"smoke_results.json","w",encoding="utf-8") as handle:
    json.dump(results,handle,indent=2)
print("CHARACTER_STUDIO_TESTS_PASSED",json.dumps(results))
cs.unregister()
