"""Generate the ready-to-open demo and a studio preview using Blender itself."""
from pathlib import Path
import sys
import bpy
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import chimera_kit as cs
from chimera_kit import rig, motion, geometry as geo
cs.register()
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
p=bpy.context.scene.cs_settings
p.species="DRAGON"
p.cycle_frames=36
p.cycles=4
p.stride=.42
p.gait="WALK"
p.bounce=.018
p.tail_swing=.22
arm=rig.build(bpy.context,p)
motion.generate(bpy.context,arm,p)
p.layer_name="Base walk"
motion.push_clip(arm,p)
p.motion_scope="TAIL"
p.tail_swing=.13
p.tail_phase=.20
p.layer_name="Tail accent"
p.layer_blend="ADD"
p.layer_weight=.45
motion.generate(bpy.context,arm,p)
motion.push_clip(arm,p)
bpy.ops.chimera_kit.layer(operation="UNMUTE")
p.motion_scope="ALL"
p.layer_blend="REPLACE"
p.layer_weight=1
scene=bpy.context.scene
scene.frame_set(9)
stage=bpy.data.collections.new("Studio · presentation")
scene.collection.children.link(stage)
mat=geo.material("Studio · graphite",(.018,.025,.042),.22,.4)
geo.mesh_object(stage,"Studio · ground",[(-200,-200,-.012),(200,-200,-.012),(200,200,-.012),(-200,200,-.012)],[(0,1,2,3)],mat)
camera_data=bpy.data.cameras.new("Studio camera")
camera=bpy.data.objects.new("Studio camera",camera_data)
stage.objects.link(camera)
camera.location=(3.8,-5.2,3.2)
target=Vector((0,.25,.62))
camera.rotation_euler=(target-camera.location).to_track_quat("-Z","Y").to_euler()
camera_data.type="ORTHO"
camera_data.ortho_scale=4.55
scene.camera=camera
def light(name,position,power,color,size):
    data=bpy.data.lights.new(name,"AREA")
    obj=bpy.data.objects.new(name,data)
    stage.objects.link(obj)
    obj.location=position
    obj.rotation_euler=(Vector((0,0,.6))-obj.location).to_track_quat("-Z","Y").to_euler()
    data.energy=power
    data.color=color
    data.shape="DISK"
    data.size=size
light("Key · softbox",(1,-3,4),650,(.83,.90,1),4)
light("Rim · warm",(-3,2,3),900,(1,.46,.22),3)
light("Fill · mint",(3,2,2.5),450,(.27,.85,.85),3)
scene.world.color=(.16,.16,.16)
scene.render.engine="CYCLES"
scene.cycles.samples=32
scene.cycles.use_denoising=True
scene.render.resolution_x=1280
scene.render.resolution_y=900
scene.render.resolution_percentage=100
scene.render.image_settings.file_format="PNG"
scene.render.filepath=str(ROOT/"preview.png")
scene.render.fps=24
scene.view_settings.view_transform="AgX"
rig.select(bpy.context,arm)
arm.show_in_front=False
p.status="Version 1.7.0 · Dragon · 2 animation layers. Space to play; open Motion tuning or Animation layer manager below."
for screen in bpy.data.screens:
    for area in screen.areas:
        if area.type=="VIEW_3D":
            space=area.spaces.active
            space.show_region_ui=True
            space.shading.type="MATERIAL"
            space.overlay.show_extras=False
            space.region_3d.view_distance=4.8
            space.region_3d.view_location=(0,.1,.70)
            space.region_3d.view_rotation=camera.rotation_euler.to_quaternion()
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/"Character_Studio_Demo.blend"))
bpy.ops.render.render(write_still=True)
print("DEMO_CREATED",ROOT/"Character_Studio_Demo.blend")
