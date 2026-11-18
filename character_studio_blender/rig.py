"""Create editable Blender armatures from a shared anatomy blueprint."""
import json
import math
import uuid
import bpy
from mathutils import Vector
from .anatomy import blueprint
from . import geometry as geo

def active(context):
    obj=context.object
    if obj:
        candidate=obj if obj.type=="ARMATURE" else obj.parent
        if candidate and candidate.get("cs_rig"):
            return candidate
    candidate=context.scene.cs_settings.active_rig
    return candidate if candidate and candidate.get("cs_rig") else None

def object_mode(context):
    if context.object and context.object.mode!="OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")

def select(context, arm):
    object_mode(context)
    bpy.ops.object.select_all(action="DESELECT")
    arm.hide_set(False)
    arm.select_set(True)
    context.view_layer.objects.active=arm
    context.scene.cs_settings.active_rig=arm

def build(context, p):
    object_mode(context)
    plan=blueprint(p)
    name=p.character_name.strip() or p.species.title()
    collection=bpy.data.collections.new("CS · "+name)
    context.scene.collection.children.link(collection)
    collection["cs_id"]=uuid.uuid4().hex
    arm_data=bpy.data.armatures.new(name+" · Skeleton")
    arm=bpy.data.objects.new(name+" · Rig",arm_data)
    collection.objects.link(arm)
    arm["cs_rig"]=True
    arm["cs_version"]="1.2.0"
    arm["cs_id"]=collection["cs_id"]
    arm["cs_species"]=p.species
    arm["cs_size"]=p.size
    arm["cs_limbs"]=json.dumps(plan.limbs)
    arm["cs_settings"]=json.dumps({key:getattr(p,key) for key in
        ("species","size","body_length","body_width","leg_length","arm_length","head_size","leg_pairs","spine_links","tail_links",
         "fingers","finger_links","mannequin_style","wings","antennae","ponytail","neck_length","neck_links","mannequin","jaw","antenna_length","antenna_links","tail_length","wing_span","wing_links","eyes","eye_size","chest_size","belly_size","hip_size")})
    boxes=p.mannequin and p.mannequin_style=="BOX"
    arm.show_in_front=p.show_rig and not boxes
    # Thin sticks sit inside the box figure; octahedra read better on their own.
    arm_data.display_type="STICK" if boxes else "OCTAHEDRAL"
    select(context,arm)
    bpy.ops.object.mode_set(mode="EDIT")
    for spec in plan.bones:
        bone=arm_data.edit_bones.new(spec["name"])
        bone.head=spec["head"]
        bone.tail=spec["tail"]
        bone.use_deform=spec["deform"]
        if spec["parent"]:
            bone.parent=arm_data.edit_bones[spec["parent"]]
        bone.head_radius=p.size*.025
        bone.tail_radius=p.size*.016
    bpy.ops.object.mode_set(mode="OBJECT")
    groups={}
    for spec in plan.bones:
        group=groups.get(spec["group"])
        if not group:
            group=arm_data.collections.new(spec["group"])
            groups[spec["group"]]=group
        bone=arm_data.bones[spec["name"]]
        group.assign(bone)
        if hasattr(bone,"color"):
            bone.color.palette="THEME04" if not spec["deform"] else "THEME03"
        arm.pose.bones[bone.name].rotation_mode="XYZ"
    shapes=bpy.data.collections.new("CS · Control Shapes")
    collection.children.link(shapes)
    shapes.hide_render=True
    shapes["cs_id"]=collection["cs_id"]
    root_shape=geo.shape(shapes,"CS root ring","RING",p.size*.30)
    body_shape=geo.shape(shapes,"CS body ring","RING",p.size*.19)
    foot_shape=geo.shape(shapes,"CS foot control","FOOT",p.size*.06)
    pole_shape=geo.shape(shapes,"CS knee control","POLE",p.size*.035)
    for bone in arm.pose.bones:
        if bone.name.startswith("CTRL-") or bone.name.startswith("POLE-"):
            bone.custom_shape=root_shape if bone.name=="CTRL-root" else body_shape if bone.name=="CTRL-body" else pole_shape if bone.name.startswith("POLE-") else foot_shape
            bone.use_custom_shape_bone_size=False
            # Mesh ring lies in its own XY plane; align it to world ground.
            bone.custom_shape_rotation_euler=bone.bone.matrix_local.to_3x3().inverted().to_euler()
    for limb in plan.limbs:
        lower=arm.pose.bones[limb["lower"]]
        ik=lower.constraints.new("IK")
        ik.name="CS · Foot IK"
        ik.target=arm
        ik.subtarget=limb["control"]
        ik.pole_target=arm
        ik.pole_subtarget=limb["pole"]
        ik.chain_count=2
        ik.use_stretch=False
        arm.pose.bones[limb["upper"]].ik_stretch=0
        lower.ik_stretch=0
        # Calibrate pole angle from the rest knee rather than relying on a
        # fixed angle for legs facing different directions.
        target=Vector(limb["knee"])
        def error(angle):
            ik.pole_angle=angle
            context.view_layer.update()
            return (lower.head-target).length_squared
        candidates=[(-math.pi+i*math.tau/16) for i in range(16)]
        best=min(candidates,key=error)
        for step in (math.pi/16,math.pi/32,math.pi/64,math.pi/128,math.pi/256,math.pi/512,math.pi/1024):
            best=min((best-step,best,best+step),key=error)
        ik.pole_angle=best
        foot=arm.pose.bones[limb["foot"]]
        c=foot.constraints.new("COPY_ROTATION")
        c.name="CS · Foot orientation"
        c.target=arm
        c.subtarget=limb["control"]
    context.view_layer.update()
    ensure_motion_controls(arm)
    if p.mannequin and p.mannequin_style=="BOX":
        colors=geo.PALETTES.get(p.species, geo.PALETTES["HUMAN"])
        shell=geo.material("CS · "+p.species+" shell",colors[0])
        def mat_for(bone_name):
            sided=bone_name.endswith((".L",".R")) or ".L." in bone_name or ".R." in bone_name
            if p.species in {"FISH","SHARK","DOLPHIN","WHALE","TADPOLE","SNAKE","WORM"}:
                return shell   # one skin colour reads better than left/right coding on a swimmer
            return geo.side_material(bone_name) if sided or p.species=="BIPED" else shell
        for spec in plan.bones:
            box=spec.get("box")
            if not box and spec["radius"]:
                r=spec["radius"]*1.9
                box=(r,r,r*.78,r*.78)
            if box:
                obj=geo.box_segment(collection,name+" · "+spec["name"],spec["head"],spec["tail"],box,mat_for(spec["name"]))
                geo.rigid_bind(obj,arm,spec["name"])
        for i,form in enumerate(plan.forms):
            sx,sy,sz=form["scale"]
            if form.get("ball"):
                continue   # drawn below, in every style
            # Joint balls and eyes belong to the rounded style only.
            if form["color"]==2 or (abs(sx-sy)<1e-9 and abs(sy-sz)<1e-9):
                continue
            obj=geo.box_form(collection,name+f" · form {i+1:02d}",form["center"],form["scale"],mat_for(form["bone"]))
            geo.rigid_bind(obj,arm,form["bone"])
    elif p.mannequin:
        colors=geo.PALETTES.get(p.species, geo.PALETTES["HUMAN"])
        mats=[geo.material("CS · "+p.species+" shell",colors[0]),
              geo.material("CS · "+p.species+" joints",colors[1],.30),
              geo.material("CS · luminous eyes",(.10,.80,.73),.25,.18)]
        for spec in plan.bones:
            if spec["radius"]:
                obj=geo.segment(collection,name+" · "+spec["name"],spec["head"],spec["tail"],spec["radius"],mats[0])
                geo.rigid_bind(obj,arm,spec["name"])
        for i,form in enumerate(plan.forms):
            if form.get("ball"):
                continue
            obj=geo.ellipsoid(collection,name+f" · form {i+1:02d}",form["center"],form["scale"],mats[form["color"]])
            geo.rigid_bind(obj,arm,form["bone"])
    if p.mannequin:
        balls={"eye_white":((.93,.93,.90),.25),"eye_pupil":((.02,.02,.025),.2)}
        for i,form in enumerate(plan.forms):
            if form.get("ball"):
                color,rough=balls[form["ball"]]
                obj=geo.ellipsoid(collection,name+f" · {form['ball']} {i+1:02d}",form["center"],form["scale"],
                                  geo.material("CS · "+form["ball"],color,.0,rough))
                geo.rigid_bind(obj,arm,form["bone"])
    if p.mannequin and "wingtip.L" in arm_data.bones:
        membrane=geo.material("CS · "+p.species+" joints",geo.PALETTES.get(p.species,geo.PALETTES["HUMAN"])[1],.30)
        def panel(corners):
            """corners: (point, bone) pairs. Each corner follows its own bone, so
            the membrane closes like a fan when the wing folds."""
            obj=geo.mesh_object(collection,name+" · wing membrane",[c[0] for c in corners],[tuple(range(len(corners)))],membrane)
            for vertex,(_,bone_name) in enumerate(corners):
                group=obj.vertex_groups.get(bone_name) or obj.vertex_groups.new(name=bone_name)
                group.add([vertex],1.0,"REPLACE")
            obj.parent=arm
            obj.modifiers.new("Character Studio","ARMATURE").object=arm
            obj["cs_preview"]=True
        for side in ("L","R"):
            bones=arm_data.bones
            mids=sorted((b for b in bones if b.name.startswith("wingmid.") and b.name.endswith(side)),
                        key=lambda b:int(b.name.split(".")[1]))
            edge=[bones["wing."+side]]+mids+[bones["wingtip."+side]]
            fingers=[bones[f"wingfinger.{i}.{side}"] for i in (1,2,3)]
            # Trailing corner at each joint: its rib, or the first finger at the last joint.
            trailing={}
            for index,bone in enumerate(edge[1:],1):
                rib=bones.get(f"wingrib.{index}.{side}")
                trailing[index]=(rib.tail_local,rib.name) if rib else (fingers[0].tail_local,fingers[0].name)
            if len(edge)>2:
                panel([(edge[0].head_local,edge[0].name),(edge[1].head_local,edge[1].name),trailing[1]])
            for index in range(1,len(edge)-1):
                panel([(edge[index].head_local,edge[index].name),(edge[index+1].head_local,edge[index+1].name),
                       trailing[index+1],trailing[index]])
            base=(edge[-1].head_local,edge[-1].name)
            for i in range(2):
                panel([base,(fingers[i].tail_local,fingers[i].name),(fingers[i+1].tail_local,fingers[i+1].name)])
    select(context,arm)
    return arm

def ensure_motion_controls(arm):
    """Upgrade an existing rig with editable per-limb controls without rebuilding."""
    for limb in json.loads(arm.get("cs_limbs","[]")):
        control=arm.pose.bones.get(limb["control"])
        if not control:
            continue
        for key,value,low,high,description in (
            ("cs_phase",0.0,-1.0,1.0,"Offset this limb's gait timing in cycles"),
            ("cs_lift",1.0,0.0,3.0,"Multiply this limb's foot lift"),
            ("cs_ik_weight",1.0,0.0,1.0,"IK influence: 1 for foot control, 0 for FK bones")):
            if key not in control:
                control[key]=value
            control.id_properties_ui(key).update(min=low,max=high,soft_min=low,soft_max=high,
                default=value,description=description)
        for name in (limb["lower"],limb["foot"]):
            for constraint in arm.pose.bones[name].constraints:
                if constraint.name not in {"CS · Foot IK","CS · Foot orientation"}:
                    continue
                fc=constraint.driver_add("influence")
                driver=fc.driver
                while driver.variables:
                    driver.variables.remove(driver.variables[0])
                variable=driver.variables.new()
                variable.name="weight"
                variable.type="SINGLE_PROP"
                variable.targets[0].id=arm
                variable.targets[0].data_path=control.path_from_id('["cs_ik_weight"]')
                driver.expression="weight"
    arm["cs_version"]="1.2.0"

def reset(context,arm):
    select(context,arm)
    if arm.animation_data:
        if arm.animation_data.action:
            arm.animation_data.action.use_fake_user=True
        arm.animation_data.action=None
        for track in arm.animation_data.nla_tracks:
            track.mute=True
    for bone in arm.pose.bones:
        bone.location=(0,0,0)
        bone.rotation_euler=(0,0,0)
        bone.rotation_quaternion=(1,0,0,0)
        bone.scale=(1,1,1)
    context.view_layer.update()

def fit(context,arm):
    reset(context,arm)
    arm.data.pose_position="REST"
    bpy.ops.object.mode_set(mode="EDIT")

def finish_fit(context,arm):
    object_mode(context)
    arm.data.pose_position="POSE"
    limbs=json.loads(arm["cs_limbs"])
    bpy.ops.object.mode_set(mode="EDIT")
    for limb in limbs:
        lower=arm.data.edit_bones[limb["lower"]]
        control=arm.data.edit_bones[limb["control"]]
        foot=arm.data.edit_bones[limb["foot"]]
        control.head=lower.tail
        control.tail=lower.tail+(foot.tail-foot.head)
    bpy.ops.object.mode_set(mode="OBJECT")
    for limb in limbs:
        limb["ankle"]=list(arm.data.bones[limb["control"]].head_local)
        limb["knee"]=list(arm.data.bones[limb["lower"]].head_local)
        limb["reach"]=(arm.data.bones[limb["upper"]].head_local-arm.data.bones[limb["lower"]].tail_local).length
        lower=arm.pose.bones[limb["lower"]]
        ik=next((c for c in lower.constraints if c.type=="IK"),None)
        if ik:
            target=Vector(limb["knee"])
            def error(angle):
                ik.pole_angle=angle
                context.view_layer.update()
                return (lower.head-target).length_squared
            best=min((-math.pi+i*math.tau/32 for i in range(32)),key=error)
            for step in (math.pi/32,math.pi/64,math.pi/128,math.pi/256,math.pi/512,math.pi/1024):
                best=min((best-step,best,best+step),key=error)
            ik.pole_angle=best
    arm["cs_limbs"]=json.dumps(limbs)
    # Hand-fitted bones would be lost by a parametric rebuild.
    arm["cs_fitted"]=True
    context.view_layer.update()

BUILD_KEYS=("species","size","body_length","body_width","leg_length","arm_length","head_size","neck_length","neck_links",
    "leg_pairs","spine_links","tail_links","fingers","finger_links","mannequin_style","wings","antennae","ponytail","mannequin",
    "jaw","antenna_length","antenna_links","tail_length","wing_span","wing_links","eyes","eye_size",
    "chest_size","belly_size","hip_size")

def stored_settings(arm):
    try:
        return json.loads(arm.get("cs_settings","{}"))
    except ValueError:
        return {}

def differs(arm,p):
    """Body sliders that no longer match the creature as built."""
    stored=stored_settings(arm)
    changed=[]
    for key in BUILD_KEYS:
        if key not in stored:
            continue
        a,b=stored[key],getattr(p,key)
        if (abs(a-b)>1e-6) if isinstance(a,float) or isinstance(b,float) else a!=b:
            changed.append(key)
    return changed

def load_settings(arm,p):
    """Point the body sliders at an existing creature."""
    from . import motion
    stored=stored_settings(arm)
    motion.SYNCING=True
    try:
        for key in BUILD_KEYS:
            if key in stored:
                try: setattr(p,key,stored[key])
                except (TypeError,ValueError): pass
    finally:
        motion.SYNCING=False

def locked(arm):
    """Why a creature cannot be rebuilt parametrically, or ''."""
    if arm.get("cs_fitted"):
        return "fitted by hand"
    if json.loads(arm.get("cs_modules","[]")):
        return "has appended structures"
    return ""

def rebuild(context,arm,p):
    """Build the creature again from the current sliders and swap it in:
    same name, place, identity, animation, layers, limb settings, bound
    meshes and footsteps. Returns the new armature."""
    from . import motion
    object_mode(context)
    old_collection=arm.users_collection[0]
    base=arm.name[:-len(" · Rig")] if arm.name.endswith(" · Rig") else arm.name
    was_active=context.view_layer.objects.active==arm
    rig_id=arm["cs_id"]
    world=arm.matrix_world.copy()
    front=arm.show_in_front
    arm.name="~"+arm.name
    arm.data.name="~"+arm.data.name
    old_collection.name="~"+old_collection.name
    for child in old_collection.children:
        if not child.get("cs_footprints"): child.name="~"+child.name
    for obj in old_collection.all_objects:
        if obj.get("cs_owned") and not obj.get("cs_footprint") and obj!=arm: obj.name="~"+obj.name
    keep_name=p.character_name
    p.character_name=base
    try:
        new=build(context,p)
    finally:
        p.character_name=keep_name
    new_collection=new.users_collection[0]
    new["cs_id"]=rig_id
    new_collection["cs_id"]=rig_id
    for child in new_collection.children: child["cs_id"]=rig_id
    new.matrix_world=world
    new.show_in_front=front
    for key in arm.keys():
        if key.startswith("cs_pose_") or key in {"cs_footprint_signature","cs_last_action"}:
            new[key]=arm[key]
    for bone in arm.pose.bones:
        target=new.pose.bones.get(bone.name)
        if target:
            for key in ("cs_phase","cs_lift","cs_ik_weight"):
                if key in bone: target[key]=bone[key]
    # Animation: the active cycle and every layer.
    source=arm.animation_data
    if source:
        new.animation_data_create()
        data=new.animation_data
        data.use_nla=source.use_nla
        if source.action:
            data.action=source.action
            if hasattr(data,"action_slot") and source.action_slot:
                try: data.action_slot=source.action_slot
                except (TypeError,RuntimeError,ValueError): pass
        for track in source.nla_tracks:
            copy=data.nla_tracks.new()
            copy.name,copy.mute=track.name,track.mute
            for strip in track.strips:
                if not strip.action: continue
                clip=copy.strips.new(strip.name,int(strip.frame_start),strip.action)
                clip.name=strip.name
                clip.blend_type,clip.extrapolation,clip.influence=strip.blend_type,strip.extrapolation,strip.influence
                if hasattr(clip,"action_slot") and strip.action_slot:
                    try: clip.action_slot=strip.action_slot
                    except (TypeError,RuntimeError,ValueError): pass
            copy.is_solo=track.is_solo
        for entry in arm.cs_layers:
            item=new.cs_layers.add()
            item.strip_name=entry.strip_name
            for key in ("label","weight","fade_in","fade_out"):
                setattr(item,key,getattr(entry,key))
        for item in new.cs_layers:
            motion.update_layer_controls(item)
    # The artist's own meshes follow the new skeleton.
    for obj in bpy.data.objects:
        if obj.get("cs_owned") or obj==arm or obj==new:
            continue
        for modifier in getattr(obj,"modifiers",[]):
            if modifier.type=="ARMATURE" and modifier.object==arm:
                modifier.object=new
        if obj.parent==arm:
            matrix=obj.matrix_world.copy()
            obj.parent=new
            obj.matrix_world=matrix
    for child in list(old_collection.children):
        if child.get("cs_footprints"):
            new_collection.children.link(child)
            old_collection.children.unlink(child)
    settings=context.scene.cs_settings
    for key in ("rt_source","rt_target"):
        if getattr(settings,key)==arm:
            items=[{k:getattr(i,k) for k in ("slot","label","kind","source","target","ref")} for i in settings.rt_items]
            setattr(settings,key,new)
            for row in items:
                item=settings.rt_items.add()
                for k,v in row.items(): setattr(item,k,v)
    for obj in list(old_collection.all_objects):
        if obj==arm or obj.get("cs_owned"):
            bpy.data.objects.remove(obj,do_unlink=True)
        else:
            if obj.name not in new_collection.objects: new_collection.objects.link(obj)
    for child in list(old_collection.children):
        bpy.data.collections.remove(child)
    bpy.data.collections.remove(old_collection)
    for data in list(bpy.data.armatures):
        if data.users==0 and data.name.startswith("~"): bpy.data.armatures.remove(data)
    settings.active_rig=new
    if was_active:
        select(context,new)
    context.view_layer.update()
    return new

def validate(arm):
    issues=[]
    if not arm or not arm.get("cs_rig"):
        return ["Select a Character Studio rig"]
    for name in ("CTRL-root","CTRL-body","pelvis","head"):
        if not arm.data.bones.get(name):
            issues.append("Missing bone: "+name)
    for limb in json.loads(arm.get("cs_limbs","[]")):
        for key in ("upper","lower","foot","control","pole"):
            if not arm.data.bones.get(limb[key]):
                issues.append("Missing bone: "+limb[key])
        lower=arm.pose.bones.get(limb["lower"])
        if lower and not any(c.type=="IK" and c.target==arm for c in lower.constraints):
            issues.append("Missing IK: "+lower.name)
    return issues
