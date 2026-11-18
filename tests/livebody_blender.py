"""Run with Blender --background --factory-startup --python-exit-code 1 --python tests/livebody_blender.py.

Background Blender runs no timers, so the live tick is called directly."""
import json
import time
from pathlib import Path
import sys
import bpy
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import chimera_kit as cs
from chimera_kit import rig, motion
cs.register()
scene=bpy.context.scene
p=scene.cs_settings
def check(condition,message):
    if not condition: raise AssertionError(message)
def settle():
    """Two ticks either side of the settle time, as a released slider would see."""
    motion.live_tick()
    time.sleep(motion.LIVE_SETTLE+.05)
    motion.live_tick()
    check("error" not in motion._live,"live tick raised: "+str(motion._live.get("error")))
    return rig.active(bpy.context)
def height(arm,name): return (arm.matrix_world @ arm.data.bones[name].head_local).z

p.species="BIPED"
p.live_on_release=False
arm=rig.build(bpy.context,p)
arm.location=(2,1,0)
bpy.context.view_layer.update()
motion.generate(bpy.context,arm,p)
motion.push_clip(arm,p)
action=motion.generate(bpy.context,arm,p)
arm.pose.bones["CTRL-leg.01.L"]["cs_lift"]=1.7
arm["cs_pose_test"]="{}"
cube=bpy.data.objects["Cube"] if "Cube" in bpy.data.objects else None
if cube:
    modifier=cube.modifiers.new("Skin","ARMATURE"); modifier.object=arm
motion.live_tick()
rig_id,name=arm["cs_id"],arm.name
bones,hips=len(arm.data.bones),height(arm,"pelvis")

# Proportions: longer legs raise the hips; identity, place, animation and settings survive.
p.leg_length=2.5
motion.live_tick()
check(rig.active(bpy.context)==arm,"rebuilt before the slider settled")
new=settle()
check(new!=arm and new.name==name and new["cs_id"]==rig_id,"rebuilt creature lost its name or identity")
check(name in bpy.data.objects and not any(o.name.startswith("~") for o in bpy.data.objects),"old creature left behind")
check(not any(c.name.startswith("~") for c in bpy.data.collections),"old collection left behind")
check(height(new,"pelvis")>hips*1.6,"leg length slider did not reshape the creature")
check(abs(new.matrix_world.translation.x-2)<1e-6,"creature moved")
check(new.animation_data.action==action and len(new.animation_data.nla_tracks)==1 and len(new.cs_layers)==1,"animation or layers lost")
check(abs(new.pose.bones["CTRL-leg.01.L"]["cs_lift"]-1.7)<1e-6 and "cs_pose_test" in new,"limb settings or poses lost")
check(p.active_rig==new,"active creature not updated")
if cube: check(cube.modifiers["Skin"].object==new,"bound mesh still points at the old skeleton")
scene.frame_set(5)
foot=new.pose.bones["CTRL-leg.01.L"].matrix.translation.copy()
scene.frame_set(13)
check((new.pose.bones["CTRL-leg.01.L"].matrix.translation-foot).length>.05,"cycle does not play on the rebuilt creature")
check(json.loads(action["cs_parameters"])["stride"]==p.stride,"cycle was not regenerated for the new legs")
arm=new

# Link counts and the neck.
p.spine_links=7
p.neck_links=6
p.neck_length=6
p.tail_links=5
arm=settle()
names=[b.name for b in arm.data.bones]
check("spine.07" in names and "neck.06" in names and "tail.05" in names,"link counts not applied")
check(height(arm,"head")-height(arm,"neck")>.5,"neck length not applied")
check(not rig.validate(arm),"rebuilt creature invalid")
# Extreme values build and animate.
p.body_length=8; p.body_width=5; p.arm_length=6; p.head_size=4; p.size=20
arm=settle()
check(not rig.validate(arm) and arm["cs_id"]==rig_id,"extreme proportions failed")
p.body_length=1; p.body_width=1; p.arm_length=1; p.head_size=1; p.size=1.8; p.leg_length=1
arm=settle()

# Choosing another preset sets up a new creature; it must not reshape this one.
p.species="HORSE"
same=settle()
check(same==arm and same["cs_species"]=="BIPED","changing the preset reshaped the active creature")
check(bpy.ops.chimera_kit.sync_settings()=={"FINISHED"} and p.species=="BIPED" and p.neck_links==6,"sync back failed")
# Selecting another creature loads its values instead of rebuilding it.
p.species="GIRAFFE"
giraffe=rig.build(bpy.context,p)
check(abs(p.neck_length-3.4)<1e-6 and p.neck_links==5 and "neck.05" in giraffe.data.bones and "neck.06" not in giraffe.data.bones,"giraffe neck")
check(height(giraffe,"head")>height(giraffe,"pelvis")*1.5,"giraffe head is not high above its body")
motion.live_tick()
p.active_rig=arm
bpy.context.view_layer.objects.active=arm
motion.live_tick()
check(p.species=="BIPED" and p.neck_links==6 and abs(p.neck_length-6)<1e-6,"sliders did not load the selected creature")
check(rig.active(bpy.context)==arm and "neck.05" in giraffe.data.bones,"selecting a creature rebuilt something")
# Hand-fitted creatures are left alone; the switch turns it off.
arm["cs_fitted"]=True
p.leg_length=3
check(settle()==arm,"hand-fitted creature was rebuilt")
del arm["cs_fitted"]
p.live_build=False
check(settle()==arm,"live body ran while switched off")
p.live_build=True
check(settle()!=arm,"live body did not resume")
# Every family takes a long neck and extra links.
for species in ("HUMAN","HORSE","TREX","OSTRICH","MECH_TROOPER","CENTAUR","LIZARD"):
    p.species=species
    p.neck_length=4; p.neck_links=5; p.spine_links=9
    creature=rig.build(bpy.context,p)
    check(not rig.validate(creature),species+": long neck build invalid")
    check(sum(1 for b in creature.data.bones if b.name.startswith("neck"))>=5,species+": neck links")
    motion.generate(bpy.context,creature,p)
print("CHIMERA_KIT_LIVEBODY_PASSED")
cs.unregister()
