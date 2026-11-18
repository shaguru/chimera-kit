"""Append editable structures to a creature without replacing its armature."""
import json
import math
import bpy
from mathutils import Vector
from . import rig, geometry as geo

def add(context,arm,p):
    if arm.data.pose_position=="REST" or context.mode=="EDIT_ARMATURE":
        raise ValueError("Finish Fit mode before adding structures")
    if p.module_parent not in arm.data.bones:
        raise ValueError("Parent bone does not exist: "+p.module_parent)
    rig.reset(context,arm)
    size=float(arm["cs_size"])
    length=size*p.module_length
    anchor=arm.data.bones[p.module_parent].tail_local.copy()
    existing={b.name for b in arm.data.bones}
    specs=[]
    limbs=json.loads(arm["cs_limbs"])
    added_limbs=[]
    def unique(prefix):
        index=1
        while f"{prefix}.{index:02d}" in existing:
            index+=1
        name=f"{prefix}.{index:02d}"
        existing.add(name)
        return name
    def bone(name,head,tail,parent,deform=True,group="Details"):
        specs.append(dict(name=name,head=Vector(head),tail=Vector(tail),parent=parent,deform=deform,group=group))
        return name
    kind=p.module_type
    if kind in {"TAIL","SPINE"}:
        direction=Vector((0,1,0)) if kind=="TAIL" else Vector((0,-1,.15)).normalized()
        parent=p.module_parent
        for i in range(p.module_links):
            name=unique(kind.lower())
            parent=bone(name,anchor+direction*length*i/p.module_links,
                anchor+direction*length*(i+1)/p.module_links,parent,group=kind.title())
        if kind=="SPINE":
            point=anchor+direction*length
            bone(unique("hub"),point,point+Vector((0,0,size*.08)),parent,group="Body")
    elif kind=="HUB":
        bone(unique("hub"),anchor,anchor+Vector((0,0,size*.08)),p.module_parent,group="Body")
    elif kind=="ARMS":
        number=1
        while any(n.startswith(f"arm.{number:02d}.") for n in existing):
            number+=1
        for side,sign in (("L",1),("R",-1)):
            elbow=anchor+Vector((sign*length*.55,0,-length*.15))
            wrist=anchor+Vector((sign*length,0,-length*.4))
            name=bone(f"arm.{number:02d}.{side}",anchor,elbow,p.module_parent,group="Arms")
            bone(f"forearm.{number:02d}.{side}",elbow,wrist,name,group="Arms")
    else:
        index=max([l["index"] for l in limbs],default=-1)+1
        for side,sign in (("L",1),("R",-1)):
            prefix=f"leg.{index+1:02d}.{side}"
            hip=anchor+Vector((sign*size*.12,0,0))
            ankle=hip+Vector((sign*length*.22,0,-length))
            knee=(hip+ankle)*.5+Vector((0,-length*.18,0))
            toe=ankle+Vector((0,-size*.08,-size*.01))
            upper=bone(prefix+".upper",hip,knee,p.module_parent,group="Legs")
            lower=bone(prefix+".lower",knee,ankle,upper,group="Legs")
            foot=bone(prefix+".foot",ankle,toe,lower,group="Legs")
            control=bone("CTRL-"+prefix,ankle,toe,"CTRL-root",False,"Feet IK")
            pole_point=knee+Vector((0,-size*.25,0))
            pole=bone("POLE-"+prefix,pole_point,pole_point+Vector((0,0,size*.05)),"CTRL-root",False,"Poles")
            item=dict(upper=upper,lower=lower,foot=foot,control=control,pole=pole,
                ankle=list(ankle),knee=list(knee),index=index,side=sign,reach=(hip-ankle).length)
            limbs.append(item)
            added_limbs.append(item)
    bpy.ops.object.mode_set(mode="EDIT")
    for spec in specs:
        b=arm.data.edit_bones.new(spec["name"])
        b.head=spec["head"]
        b.tail=spec["tail"]
        b.parent=arm.data.edit_bones[spec["parent"]]
        b.use_deform=spec["deform"]
    bpy.ops.object.mode_set(mode="OBJECT")
    owner=arm.users_collection[0]
    foot_shape=next((b.custom_shape for b in arm.pose.bones if b.name.startswith("CTRL-leg") and b.custom_shape),None)
    pole_shape=next((b.custom_shape for b in arm.pose.bones if b.name.startswith("POLE-") and b.custom_shape),None)
    material=geo.material("CS · appended modules",(.22,.43,.52))
    for spec in specs:
        b=arm.data.bones[spec["name"]]
        group=arm.data.collections.get(spec["group"]) or arm.data.collections.new(spec["group"])
        group.assign(b)
        pose=arm.pose.bones[b.name]
        pose.rotation_mode="XYZ"
        if spec["deform"]:
            if p.mannequin:
                obj=geo.segment(owner,arm.name+" · "+b.name,spec["head"],spec["tail"],size*.022,material)
                geo.rigid_bind(obj,arm,b.name)
        else:
            pose.custom_shape=pole_shape if b.name.startswith("POLE-") else foot_shape
            pose.use_custom_shape_bone_size=False
            pose.custom_shape_rotation_euler=b.matrix_local.to_3x3().inverted().to_euler()
    for item in added_limbs:
        lower=arm.pose.bones[item["lower"]]
        ik=lower.constraints.new("IK")
        ik.name="CS · Foot IK"
        ik.target=ik.pole_target=arm
        ik.subtarget=item["control"]
        ik.pole_subtarget=item["pole"]
        ik.chain_count=2
        ik.use_stretch=False
        lower.ik_stretch=arm.pose.bones[item["upper"]].ik_stretch=0
        target=Vector(item["knee"])
        def error(angle):
            ik.pole_angle=angle
            context.view_layer.update()
            return (lower.head-target).length_squared
        best=min((-math.pi+i*math.tau/32 for i in range(32)),key=error)
        for step in (math.pi/32,math.pi/64,math.pi/128,math.pi/256,math.pi/512,math.pi/1024):
            best=min((best-step,best,best+step),key=error)
        ik.pole_angle=best
        c=arm.pose.bones[item["foot"]].constraints.new("COPY_ROTATION")
        c.name="CS · Foot orientation"
        c.target=arm
        c.subtarget=item["control"]
    arm["cs_limbs"]=json.dumps(limbs)
    rig.ensure_motion_controls(arm)
    history=json.loads(arm.get("cs_modules","[]"))
    history.append({"type":kind,"parent":p.module_parent,"bones":[s["name"] for s in specs]})
    arm["cs_modules"]=json.dumps(history)
    context.view_layer.update()
    return [s["name"] for s in specs]
