"""Render the pictures and loops shown in the README.

    blender --background --factory-startup --python scripts/render_showcase.py -- <job> <output folder>

Jobs: hero, walk, action, wings, fly, crawl, morph. Still frames are written as PNG;
turn a numbered sequence into a GIF or MP4 with ffmpeg.
"""
import math
from pathlib import Path
import sys
import bpy
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import chimera_kit as cs
from chimera_kit import rig, motion

args=sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else sys.argv[1:]
job,out=args[0],Path(args[1])
out.mkdir(parents=True,exist_ok=True)
cs.register()
scene=bpy.context.scene
p=scene.cs_settings

def stage(width,depth=14):
    """A seamless studio sweep: floor curving up into a back wall."""
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj)
    profile=[(-depth*.45,0)]
    steps=14
    radius=3.0
    back=depth*.42
    for i in range(steps+1):
        angle=math.pi/2*i/steps
        profile.append((back+math.sin(angle)*radius,radius-math.cos(angle)*radius))
    profile.append((back+radius,radius+9))
    verts=[]
    for x in (-width,width):
        verts+=[(x,y,z) for y,z in profile]
    count=len(profile)
    faces=[(i,i+1,count+i+1,count+i) for i in range(count-1)]
    mesh=bpy.data.meshes.new("Sweep")
    mesh.from_pydata(verts,[],faces)
    for poly in mesh.polygons: poly.use_smooth=True
    sweep=bpy.data.objects.new("Sweep",mesh)
    scene.collection.objects.link(sweep)
    mat=bpy.data.materials.new("Sweep")
    mat.use_nodes=True
    bsdf=mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value=(.10,.115,.145,1)
    bsdf.inputs["Roughness"].default_value=.55
    mesh.materials.append(mat)
    world=bpy.data.worlds.new("Studio")
    world.use_nodes=True
    world.node_tree.nodes["Background"].inputs[0].default_value=(.03,.035,.045,1)
    scene.world=world

def light(name,location,target,energy,size,color=(1,1,1)):
    data=bpy.data.lights.new(name,"AREA")
    data.energy,data.size,data.color=energy,size,color
    obj=bpy.data.objects.new(name,data)
    scene.collection.objects.link(obj)
    obj.location=location
    obj.rotation_euler=(Vector(target)-obj.location).to_track_quat("-Z","Y").to_euler()

def camera(location,target,lens=70):
    data=bpy.data.cameras.new("Camera")
    data.lens=lens
    obj=bpy.data.objects.new("Camera",data)
    scene.collection.objects.link(obj)
    obj.location=location
    obj.rotation_euler=(Vector(target)-obj.location).to_track_quat("-Z","Y").to_euler()
    scene.camera=obj

def quality(width,height,samples):
    scene.render.engine="CYCLES"
    scene.cycles.device="CPU"
    scene.cycles.samples=samples
    scene.cycles.use_adaptive_sampling=True
    scene.cycles.max_bounces=3
    try:
        scene.cycles.use_denoising=True
        scene.cycles.denoiser="OPENIMAGEDENOISE"
    except TypeError:
        scene.cycles.use_denoising=False
        scene.cycles.samples=samples*3
    scene.render.resolution_x,scene.render.resolution_y=width,height
    scene.render.resolution_percentage=100
    scene.render.image_settings.file_format="PNG"
    scene.view_settings.view_transform="Standard"
    for look in ("Medium High Contrast","AgX - Medium High Contrast"):
        try:
            scene.view_settings.look=look
            break
        except TypeError:
            pass

def lights(center,spread):
    light("Key",(center[0]-spread*.5,-spread*.9,spread*.9),center,spread*spread*15,spread*.7,(1,.96,.90))
    light("Fill",(center[0]+spread*.9,-spread*.6,spread*.35),center,spread*spread*5,spread*.9,(.80,.88,1))
    light("Rim",(center[0]+spread*.2,spread*.8,spread*.8),center,spread*spread*11,spread*.5,(.85,.92,1))

def creature(species,x,y=0.0,turn=35,z=0.0,**options):
    """Build one preset, apply options, give it a cycle and place it."""
    p.species=species
    p.size=1.8
    p.motion_type="WALK"
    p.jaw_chance,p.jaw_open=.5,.3
    for key,value in options.items():
        setattr(p,key,value)
    p.show_rig=False
    arm=rig.build(bpy.context,p)
    motion.generate(bpy.context,arm,p)
    arm.location=(x,y,z)
    arm.rotation_euler[2]=math.radians(turn)
    # Controls and bones are for animators, not for the picture.
    arm.hide_render=True
    for obj in arm.users_collection[0].all_objects:
        if obj.type!="MESH" or not obj.get("cs_preview"):
            obj.hide_render=True
    return arm

def reset_cycle():
    p.motion_type="WALK"
    p.cycle_frames=32
    p.cycles=1
    p.travel=False
    p.exaggeration=1.0

def frames(count,name):
    scene.frame_start,scene.frame_end=1,count
    for frame in range(1,count+1):
        scene.frame_set(frame)
        scene.render.filepath=str(out/f"{name}_{frame:03d}.png")
        bpy.ops.render.render(write_still=True)

reset_cycle()
if job=="hero":
    stage(30,depth=32)
    quality(2000,1000,int(args[2]) if len(args)>2 else 64)
    front=[("BIPED",-7.4,{}),("ALIEN",-5.9,dict(antenna_length=1.6)),("MECH_TROOPER",-4.4,{}),("GORILLA",-2.8,{}),
           ("FROG",-1.0,{}),("SPIDER",1.5,{}),("OSTRICH",3.5,{}),("MECH_POD",5.2,{}),("ANGEL",7.2,dict(wing_style="GLIDE",wing_fold=.35))]
    for species,x,options in front:
        creature(species,x,-3.0,35,**options)
    back=[("TREX",-7.4,dict(jaw_chance=1.0,jaw_open=.55)),("HORSE",-4.3,{}),("GIRAFFE",-1.7,{}),("DRAGON",1.5,dict(wing_flap=.5,wing_links=4)),
          ("CENTAUR",4.6,{}),("ALLOSAUR",7.6,dict(jaw_chance=1.0))]
    for species,x,options in back:
        creature(species,x,3.4,40,**options)
    creature("SNAKE",-.2,-5.6,75)
    creature("SHARK",-5.2,6.5,55,z=2.9)
    creature("DOLPHIN",5.4,6.5,50,z=3.0)
    creature("EAGLE",0.2,6.5,35,z=3.2,wing_style="FLAP",wing_flap=.6)
    lights((0,0,1.5),11)
    camera((0,-38,14),(0,1.0,1.5),lens=74)
    scene.frame_set(11)
    scene.render.filepath=str(out/"hero.png")
    bpy.ops.render.render(write_still=True)
elif job=="walk":
    stage(16)
    quality(1200,380,20)
    for species,x in (("BIPED",-5.5),("TREX",-3.1),("HORSE",-.4),("LIZARD",1.9),("OSTRICH",3.8),("SPIDER",5.3)):
        creature(species,x,0,55)
    lights((0,0,1),7)
    camera((0,-21,3.4),(0,0,1.3),lens=60)
    frames(32,"walk")
elif job=="action":
    stage(16)
    quality(1200,380,20)
    p.cycle_frames=40
    creature("BIPED",-4.4,0,60,motion_type="IDLE")
    creature("BIPED",-2.8,0,60,motion_type="JUMP",jump_height=.7)
    creature("BIPED",-1.1,0,60,motion_type="PUNCH",strike_side="R")
    creature("BIPED",.7,0,60,motion_type="KICK",strike_side="L")
    creature("HORSE",3.3,0,60,motion_type="JUMP",jump_height=.5)
    lights((0,0,1),7)
    camera((0,-21,3.4),(0,0,1.3),lens=72)
    frames(40,"action")
elif job=="wings":
    stage(16)
    quality(1200,380,20)
    creature("DRAGON",-4.7,0,50,wing_style="FLAP",wing_flap=.7,wing_links=4)
    creature("EAGLE",-2.0,0,50,z=.8,wing_style="HOVER",wing_flap=.6)
    creature("ANGEL",.1,0,50,wing_style="GLIDE")
    creature("SHARK",2.6,0,60,z=.1)
    creature("DOLPHIN",4.7,.6,60,z=.85)
    lights((0,0,1),7)
    camera((0,-21,3.4),(0,0,1.3),lens=60)
    frames(32,"wings")
elif job=="fly":
    # The Fly cycle: legs tucked, body riding the beat. Glide in Wings makes it soar.
    stage(16)
    quality(1200,380,20)
    creature("EAGLE",-4.6,0,50,motion_type="FLY",wing_style="GLIDE",fly_height=1.6)
    creature("BIRD",-2.2,0,50,motion_type="FLY",wing_style="HOVER",wing_flap=.7,fly_height=3.0)
    creature("DRAGON",.4,.8,50,motion_type="FLY",wing_style="FLAP",wing_flap=.7,wing_links=4,fly_height=.9)
    creature("ANGEL",3.1,0,50,motion_type="FLY",wing_style="FLAP",wing_flap=.5,fly_height=.5)
    creature("MECH_FLYER",5.2,.4,50,motion_type="FLY",wing_style="GLIDE",fly_height=.5)
    lights((0,0,1.6),7)
    camera((0,-22,3.6),(0,0,1.9),lens=58)
    frames(int(args[2]) if len(args)>2 else 32,"fly")
elif job=="crawl":
    stage(16)
    quality(1200,380,20)
    p.cycle_frames=24
    creature("FROG",-4.6,0,55)
    creature("GECKO",-2.4,0,55)
    creature("SNAKE",.3,0,70,size=1.4)
    creature("WORM",2.9,0,60)
    creature("TADPOLE",4.5,0,60,z=-.55)
    lights((0,0,.6),7)
    camera((0,-21,3.0),(0,0,.7),lens=68)
    frames(24,"crawl")
elif job=="morph":
    # One creature reshaped by its body sliders while it keeps walking.
    quality(720,560,20)
    count=44
    def blend(a,b,t):
        t=max(0.0,min(1.0,t))
        t=t*t*(3-2*t)
        return a+(b-a)*t
    for frame in range(1,count+1):
        stage(10)
        t=(frame-1)/count
        wave=lambda start,length:math.sin(math.pi*max(0.0,min(1.0,(t-start)/length)))**2
        if frame==1: p.species="HUMAN"
        p.species="BIPED"
        p.leg_length=1+1.1*wave(0,.3)
        p.neck_length=1+7*wave(.22,.3)
        p.neck_links=1+int(round(6*wave(.22,.3)))
        p.body_width=1+1.2*wave(.46,.26)
        p.arm_length=1+1.3*wave(.46,.26)
        p.head_size=1+1.3*wave(.68,.3)
        p.antennae=wave(.68,.3)>.15
        p.eyes=wave(.68,.3)>.15
        p.eye_size=1+wave(.68,.3)
        p.show_rig=False
        arm=rig.build(bpy.context,p)
        motion.generate(bpy.context,arm,p)
        arm.location=(0,0,0)
        arm.rotation_euler[2]=math.radians(50)
        arm.hide_render=True
        for obj in arm.users_collection[0].all_objects:
            if obj.type!="MESH" or not obj.get("cs_preview"):
                obj.hide_render=True
        scene.frame_set((frame-1)%32+1)
        lights((0,0,1.4),6)
        camera((0,-17,3.4),(0,0,1.8),lens=125)
        scene.render.filepath=str(out/f"morph_{frame:03d}.png")
        bpy.ops.render.render(write_still=True)
else:
    raise SystemExit("Unknown job: "+job)
