"""Run with Blender --background --factory-startup --python-exit-code 1 --python tests/live_blender.py.

Background Blender does not run timers, so the test calls the live tick directly."""
import json
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
check(bpy.app.timers.is_registered(motion.live_tick),"live timer not registered")
p.species="BIPED"
p.live_on_release=False
arm=rig.build(bpy.context,p)
motion.live_tick()
check(not arm.animation_data or not arm.animation_data.action,"live tick generated a walk on its own")
action=motion.generate(bpy.context,arm,p)
count=len(bpy.data.actions)
def height(frame):
    scene.frame_set(frame)
    return arm.pose.bones["CTRL-body"].matrix.translation.z
def lift():
    return max(arm.pose.bones["CTRL-leg.01.L"].matrix.translation.z for f in range(1,p.cycle_frames+1) if not scene.frame_set(f))
motion.live_tick()   # adopts the new action without rewriting it
before_height,before_lift=height(5),lift()
scene.frame_set(11)
p.body_height=-.25
p.lift=.35
motion.live_tick()
check(arm.animation_data.action==action and len(bpy.data.actions)==count,"live update made a new action")
check(scene.frame_current==11,"live update moved the playhead")
check(height(5)<before_height-.05,"body height slider did not reach the walk")
check(lift()>before_lift+.05,"foot lift slider did not reach the walk")
check(json.loads(action["cs_parameters"])["body_height"]==p.body_height,"stored controls not refreshed")
# Cycle length and count resize the action and the scene range.
p.cycle_frames=20
p.cycles=2
motion.live_tick()
check(scene.frame_end==40 and round(action.frame_range[1])==41,f"range {scene.frame_end} {tuple(action.frame_range)}")
# Per-limb custom properties have no callbacks; polling must see them.
control=arm.pose.bones["CTRL-leg.01.L"]
scene.frame_set(1); a=control.matrix.translation.copy()
control["cs_phase"]=.25
motion.live_tick()
scene.frame_set(1); b=control.matrix.translation.copy()
check((a-b).length>.01,"per-limb phase did not update live")
# Travel and footprints: moving a marker reshapes the walk.
p.travel=True
motion.live_tick()
check(bpy.ops.chimera_kit.footprints(operation="CREATE")=={"FINISHED"},"footprints")
motion.live_tick()
marker=next(o for o in motion.footprint_objects(arm) if o["cs_limb"]=="CTRL-leg.01.L" and o["cs_cycle"]==1)
frame=int(marker["cs_contact_frame"])+2
scene.frame_set(frame); a=(arm.matrix_world @ control.matrix.translation).copy()
marker.location.x+=.2
bpy.context.view_layer.update()
motion.live_tick()
scene.frame_set(frame); b=arm.matrix_world @ control.matrix.translation
check(abs((b.x-a.x)-.2)<.01,f"moved footprint not followed: {b.x-a.x:.3f}")
# A layer keeps its channels when the Channels menu changes.
p.use_footprints=False
p.travel=False
motion.live_tick()
paths=len(list(motion.curves(action)))
p.motion_scope="TAIL"
p.sway=.1
motion.live_tick()
check(len(list(motion.curves(action)))==paths,"changing Channels stripped the live walk")
check(abs(json.loads(action["cs_parameters"])["sway"]-.1)<1e-6,"live update stopped after Channels changed: "+p.status)
# On release: nothing happens while the value keeps changing, then one update once it settles.
import time
p.live_on_release=True
for value in (.11,.12,.13):
    p.sway=value
    motion.live_tick()
check(abs(json.loads(action["cs_parameters"])["sway"]-.1)<1e-6,"on-release mode updated during the drag")
time.sleep(motion.LIVE_SETTLE+.05)
motion.live_tick()
check(abs(json.loads(action["cs_parameters"])["sway"]-.13)<1e-6,"on-release mode did not update after the drag")
p.live_on_release=False
# The trunk is alive by default: chest turns against the hips, and the spine bends.
def yaw(name,frame):
    scene.frame_set(frame)
    side=arm.pose.bones[name].matrix.to_3x3() @ arm.pose.bones[name].bone.matrix_local.to_3x3().inverted() @ __import__("mathutils").Vector((1,0,0))
    return __import__("math").atan2(side.y,side.x)
hips,chest=yaw("pelvis",1),yaw("spine.03",1)
check(abs(hips)>.03 and hips*chest<0,f"chest does not counter-rotate the hips: {hips:.3f} {chest:.3f}")
bend=max(abs(arm.pose.bones["spine.02"].matrix_basis.to_euler()[i]) for i in range(3) for f in range(1,21) if not scene.frame_set(f))
check(bend>.01,"spine is rigid")
# Switching live off stops rewrites; errors pause instead of raising.
p.live_update=False
p.sway=.2
motion.live_tick()
check(json.loads(action["cs_parameters"])["sway"]!=p.sway,"live update ran while switched off")
p.live_update=True
arm.data.pose_position="REST"
check(motion.live_tick()==motion.LIVE_INTERVAL,"tick must keep running in fit mode")
arm.data.pose_position="POSE"
errors=dict(motion._live)
cs.unregister()
check(not bpy.app.timers.is_registered(motion.live_tick),"live timer left registered")
check("error" not in errors,"live tick raised: "+str(errors.get("error")))
print("CHIMERA_KIT_LIVE_PASSED")
