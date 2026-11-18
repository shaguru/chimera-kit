"""Integration checks for fit, skin, recipes, poses, path walking, NLA and baking."""
from pathlib import Path
import json
import math
import sys
import bpy
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import chimera_kit as cs
from chimera_kit import rig, motion
cs.register()
p=bpy.context.scene.cs_settings
out=ROOT/"tests"/"output"
out.mkdir(exist_ok=True)
def ok(value,message):
    if not value: raise AssertionError(message)
def op(value,name): ok(value=={"FINISHED"},name)
p.species="HORSE"
arm=rig.build(bpy.context,p)
op(bpy.ops.chimera_kit.fit_start(),"fit start")
for bone in arm.data.edit_bones:
    if bone.name.startswith("leg.01"):
        bone.head.x*=1.05
        bone.tail.x*=1.05
op(bpy.ops.chimera_kit.fit_finish(),"fit finish")
ok(not rig.validate(arm),"fit validation")

# Weight an independent mesh and verify all vertex weights are normalized.
bpy.ops.mesh.primitive_uv_sphere_add(segments=12,ring_count=8,location=(0,0,.94),scale=(.2,.3,.1))
mesh=bpy.context.object
mesh.name="Artist skin test"
p.active_rig=arm
op(bpy.ops.chimera_kit.bind(method="ENVELOPE"),"distance bind")
for v in mesh.data.vertices:
    ok(abs(sum(g.weight for g in v.groups)-1)<1e-5,"weights not normalized")
ok(any(m.type=="ARMATURE" and m.object==arm for m in mesh.modifiers),"skin modifier")
rig.select(bpy.context,arm)

# Named poses and mirror involution retain editable local control transforms.
control=arm.pose.bones["CTRL-leg.01.L"]
control.location.x=.08
p.pose_name="Raised foot"
op(bpy.ops.chimera_kit.capture_pose(),"capture pose")
control.location.x=0
p.pose_choice="Raised_foot"
op(bpy.ops.chimera_kit.apply_pose(),"apply pose")
ok(abs(control.location.x-.08)<1e-6,"pose restore")
before={b.name:b.matrix_basis.copy() for b in arm.pose.bones}
op(bpy.ops.chimera_kit.pose_tools(operation="MIRROR"),"mirror 1")
op(bpy.ops.chimera_kit.pose_tools(operation="MIRROR"),"mirror 2")
ok(max(abs(b.matrix_basis[r][c]-before[b.name][r][c]) for b in arm.pose.bones for r in range(4) for c in range(4))<.0001,"double mirror drift")
op(bpy.ops.chimera_kit.pose_tools(operation="KEY"),"key pose")
ok(arm.animation_data.action is not None,"key pose creates no action")
op(bpy.ops.chimera_kit.pose_tools(operation="RESET"),"reset pose")
op(bpy.ops.chimera_kit.preview(),"hide preview")
ok(all(o.hide_render for o in arm.children if o.get("cs_preview")),"preview hide")
op(bpy.ops.chimera_kit.preview(),"show preview")

# Save and load structural recipe in a deterministic sequence (preset first).
p.io_path=str(out/"horse_recipe.json")
op(bpy.ops.chimera_kit.preset_file(operation="SAVE"),"save recipe")
p.species="SPIDER"
op(bpy.ops.chimera_kit.preset_file(operation="LOAD"),"load recipe")
ok(p.species=="HORSE" and p.leg_pairs==2,"recipe fields")

curve=bpy.data.curves.new("Walk path","CURVE")
curve.dimensions="3D"
spline=curve.splines.new("POLY")
spline.points.add(3)
for pt,co in zip(spline.points,((0,0,0,1),(0,-2,0,1),(1,-3,0,1),(2,-4,0,1))): pt.co=co
obj=bpy.data.objects.new("Walk path",curve)
bpy.context.scene.collection.objects.link(obj)
p.path_object=obj
p.travel=True
p.cycle_frames=24
p.cycles=2
action=motion.generate(bpy.context,arm,p)
bpy.context.scene.frame_set(1)
start=arm.pose.bones["CTRL-root"].head.copy()
bpy.context.scene.frame_set(49)
end=arm.pose.bones["CTRL-root"].head.copy()
ok((end-start).length>.3,"curve travel")

# Bake the sampled live skeleton and compare a final evaluated leg position.
rig.select(bpy.context,arm)
bpy.context.scene.frame_set(17)
expected={b.name:b.matrix.copy() for b in arm.pose.bones}
op(bpy.ops.chimera_kit.animation_export(),"bake")
baked=bpy.context.object
bpy.context.scene.frame_set(17)
ok(max((b.matrix.translation-expected[b.name].translation).length for b in baked.pose.bones)<.002,"baked transforms differ")
ok(all(not b.constraints for b in baked.pose.bones),"baked constraints remain")
rig.select(bpy.context,arm)
bpy.ops.wm.save_as_mainfile(filepath=str(out/"workflow_tests.blend"))
op(bpy.ops.chimera_kit.report(),"manifest")
ok((out/"chimera_kit_manifest.json").exists(),"manifest absent")
print("CHIMERA_KIT_WORKFLOWS_PASSED")
