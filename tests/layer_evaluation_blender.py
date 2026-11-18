"""Verify that NLA weights and channel masks affect evaluated poses."""
from pathlib import Path
import sys
import bpy
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import character_studio_blender as cs
from character_studio_blender import rig,motion
cs.register()
p=bpy.context.scene.cs_settings
p.species="HORSE"
p.cycles=1
p.cycle_frames=24
p.tail_swing=.2
arm=rig.build(bpy.context,p)
motion.generate(bpy.context,arm,p)
base=motion.push_clip(arm,p)
bpy.context.scene.frame_set(8)
expected=arm.pose.bones["tail.01"].rotation_euler[2]
p.motion_scope="TAIL"
p.tail_swing=.7
motion.generate(bpy.context,arm,p)
detail=motion.push_clip(arm,p)
assert all('pose.bones["tail.' in fc.data_path for fc in motion.curves(detail.action))
base.id_data.animation_data.nla_tracks[0].mute=False
entry=motion.layer_entry(arm,detail)
entry.weight=.4
bpy.context.scene.frame_set(9)
bpy.context.scene.frame_set(8)
assert abs(detail.influence-.4)<1e-5,"Layer weight not retained by NLA evaluation"
assert abs(arm.pose.bones["tail.01"].rotation_euler[2]-expected*2)<1e-4,"NLA weight does not blend evaluated pose"
entry.fade_in=8
bpy.context.scene.frame_set(5)
assert abs(detail.influence-.2)<1e-5,"Fade-in envelope did not affect evaluated weight"
print("CHARACTER_STUDIO_LAYER_EVALUATION_PASSED")
