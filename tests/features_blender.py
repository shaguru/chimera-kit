"""Focused checks for the CAT-inspired feature additions in Chimera Kit 1.1."""
from pathlib import Path
import json
import sys
import math
import bpy
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import chimera_kit as cs
from chimera_kit import rig, motion
cs.register()
assert len(cs.PRESETS)==36,"Creature library changed without an audited implementation"
p=bpy.context.scene.cs_settings
p.species="HORSE"
p.travel=True
p.cycles=2
p.cycle_frames=20
arm=rig.build(bpy.context,p)
p.tuning_preset="CARTOON"
assert bpy.ops.chimera_kit.motion_style()=={"FINISHED"}
assert p.exaggeration>1 and p.tail_swing>.3
assert bpy.ops.chimera_kit.limb_controls(operation="INIT")=={"FINISHED"}
limb=json.loads(arm["cs_limbs"])[0]
control=arm.pose.bones[limb["control"]]
control["cs_phase"]=.12
control["cs_lift"]=1.4
assert bpy.ops.chimera_kit.footprints(operation="CREATE")=={"FINISHED"}
markers=motion.footprint_objects(arm)
assert len(markers)>=len(json.loads(arm["cs_limbs"]))
before=markers[0].matrix_world.copy()
markers[0].location.x += .3
assert bpy.ops.chimera_kit.footprints(operation="RESET")=={"FINISHED"}
assert (markers[0].matrix_world.translation-before.translation).length<1e-5
assert bpy.ops.chimera_kit.footprints(operation="CREATE")=={"FINISHED"}
markers=motion.footprint_objects(arm)
markers[0].location.x += .08
assert bpy.ops.chimera_kit.generate_motion()=={"FINISHED"}
phase=motion.limb_phase(arm,limb,motion.motion_plan(bpy.context,arm,p),p)
frame=p.start_frame+max(1,int((p.stance*.5-phase)*p.cycle_frames))
bpy.context.scene.frame_set(frame)
assert (arm.matrix_world @ arm.pose.bones[limb["control"]].head-markers[0].matrix_world.translation).length<1e-4,"Footprint edit did not move the stance target"
assert arm.animation_data and arm.animation_data.action
assert bpy.ops.chimera_kit.push_clip()=={"FINISHED"}
assert len(arm.animation_data.nla_tracks)==1
p.layer_name="Tail detail"
p.motion_scope="TAIL"
p.tail_swing=.7
assert bpy.ops.chimera_kit.generate_motion()=={"FINISHED"}
assert bpy.ops.chimera_kit.push_clip()=={"FINISHED"}
assert len(arm.animation_data.nla_tracks)==2
strip=arm.animation_data.nla_tracks[-1].strips[0]
assert strip.influence==p.layer_weight
assert bpy.ops.chimera_kit.layer(operation="PLAY")=={"FINISHED"}
p.module_type="TAIL"; p.module_parent="pelvis"; p.module_links=3
assert bpy.ops.chimera_kit.add_module()=={"FINISHED"}
assert len([b for b in arm.data.bones if b.name.startswith("tail.")])>=3
p.module_type="LEGS"; p.module_parent="pelvis"; p.module_length=.35
assert bpy.ops.chimera_kit.add_module()=={"FINISHED"}
assert len(json.loads(arm["cs_limbs"]))==6
assert not rig.validate(arm)
for kind in ("HUB","SPINE","ARMS"):
    p.module_type=kind
    assert bpy.ops.chimera_kit.add_module()=={"FINISHED"}
assert not rig.validate(arm)
p.use_footprints=False
p.motion_scope="ALL"
p.travel=False
motion.generate(bpy.context,arm,p)
bpy.context.scene.frame_set(11)
assert all(math.isfinite(value) for b in arm.pose.bones for row in b.matrix for value in row)

# Curved travel must preserve stance positions even when the root turns.
p.species="HUMAN"
arm=rig.build(bpy.context,p)
arm.location=(2,1,.2)
arm.rotation_euler[2]=.3
arm.scale=(1.2,1.2,1.2)
bpy.context.view_layer.update()
p.travel=True
p.cycle_frames=40
p.cycles=2
p.stride=.25
p.stance=.8
curve=bpy.data.curves.new("Turning path","CURVE")
curve.dimensions="3D"
spline=curve.splines.new("POLY")
spline.points.add(2)
for point,co in zip(spline.points,((2,1,.2,1),(2,.9,.2,1),(3.5,.1,.2,1))):
    point.co=co
obj=bpy.data.objects.new("Turning path",curve)
bpy.context.scene.collection.objects.link(obj)
p.path_object=obj
motion.generate(bpy.context,arm,p)
positions=[]
for frame in range(2,29):
    bpy.context.scene.frame_set(frame)
    positions.append((arm.matrix_world @ arm.pose.bones["CTRL-leg.01.L"].head).copy())
assert max((v-positions[0]).length for v in positions)<1e-4,"Stance target slid on turning path"
print("CHIMERA_KIT_FEATURES_PASSED",len(markers),len(arm.data.bones),len(arm.animation_data.nla_tracks))
cs.unregister()
