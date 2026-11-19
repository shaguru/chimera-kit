"""Run with Blender --background --factory-startup --python-exit-code 1 --python tests/retarget_blender.py.

Builds a Mixamo-named skeleton and a CloudRig-style control rig from scratch, so
the test needs neither a download nor the CloudRig add-on."""
import json
import math
from pathlib import Path
import sys
import bpy
from mathutils import Vector, Matrix

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import chimera_kit as cs
from chimera_kit import rig, motion, retarget

cs.register()
scene=bpy.context.scene
p=scene.cs_settings
output=ROOT/"tests"/"output"
output.mkdir(exist_ok=True)

def check(condition,message):
    if not condition: raise AssertionError(message)

def make_armature(name,bones,location=(0,0,0)):
    """bones: (name, head, tail, parent)."""
    data=bpy.data.armatures.new(name)
    obj=bpy.data.objects.new(name,data)
    scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active=obj
    bpy.ops.object.mode_set(mode="EDIT")
    for bone_name,head,tail,parent in bones:
        bone=data.edit_bones.new(bone_name)
        bone.head,bone.tail=head,tail
        if parent: bone.parent=data.edit_bones[parent]
    bpy.ops.object.mode_set(mode="OBJECT")
    obj.location=location
    return obj

def humanoid(height,arms,prefix=lambda n:n,names=None):
    """Joint positions for a figure of the given height. arms: 'T' or 'A'."""
    h=height
    joints={"hips":(0,0,.53*h),"spine":(0,0,.60*h),"spine1":(0,0,.68*h),"spine2":(0,0,.75*h),
            "neck":(0,0,.82*h),"head":(0,0,.88*h),"top":(0,0,h)}
    for side,s in (("L",1),("R",-1)):
        shoulder=Vector((s*.10*h,0,.80*h))
        out=Vector((s,0,0)) if arms=="T" else Vector((s*.6,0,-.8)).normalized()
        joints["clav"+side]=(s*.02*h,0,.80*h)
        joints["arm"+side]=tuple(shoulder)
        joints["fore"+side]=tuple(shoulder+out*.16*h)
        joints["hand"+side]=tuple(shoulder+out*.31*h)
        joints["tip"+side]=tuple(shoulder+out*.38*h)
        joints["thigh"+side]=(s*.055*h,0,.50*h)
        joints["shin"+side]=(s*.058*h,-.012*h,.27*h)
        joints["foot"+side]=(s*.06*h,.01*h,.05*h)
        joints["toe"+side]=(s*.06*h,-.09*h,.012*h)
        joints["toetip"+side]=(s*.06*h,-.14*h,.012*h)
    return joints

def mixamo(height=170.0):
    j=humanoid(height,"T")
    m="mixamorig:"
    bones=[(m+"Hips",j["hips"],j["spine"],None),(m+"Spine",j["spine"],j["spine1"],m+"Hips"),
           (m+"Spine1",j["spine1"],j["spine2"],m+"Spine"),(m+"Spine2",j["spine2"],j["neck"],m+"Spine1"),
           (m+"Neck",j["neck"],j["head"],m+"Spine2"),(m+"Head",j["head"],j["top"],m+"Neck")]
    for side,word in (("L","Left"),("R","Right")):
        bones+=[(m+word+"Shoulder",j["clav"+side],j["arm"+side],m+"Spine2"),
                (m+word+"Arm",j["arm"+side],j["fore"+side],m+word+"Shoulder"),
                (m+word+"ForeArm",j["fore"+side],j["hand"+side],m+word+"Arm"),
                (m+word+"Hand",j["hand"+side],j["tip"+side],m+word+"ForeArm"),
                (m+word+"UpLeg",j["thigh"+side],j["shin"+side],m+"Hips"),
                (m+word+"Leg",j["shin"+side],j["foot"+side],m+word+"UpLeg"),
                (m+word+"Foot",j["foot"+side],j["toe"+side],m+word+"Leg"),
                (m+word+"ToeBase",j["toe"+side],j["toetip"+side],m+word+"Foot")]
    arm=make_armature("Armature",bones)
    arm.scale=(.01,.01,.01)   # Mixamo files are authored in centimetres.
    return arm

def animate_mixamo(arm,frames=40):
    """A stepping, arm-swinging, travelling loop keyed in bone space."""
    m="mixamorig:"
    for bone in arm.pose.bones: bone.rotation_mode="XYZ"
    def world_x(name,angle):
        bone=arm.pose.bones[name]
        basis=bone.bone.matrix_local.to_3x3()
        bone.rotation_euler=(basis.inverted() @ Matrix.Rotation(angle,3,"X") @ basis).to_euler("XYZ")
        bone.keyframe_insert("rotation_euler",frame=frame)
    def world_y(name,angle):
        bone=arm.pose.bones[name]
        basis=bone.bone.matrix_local.to_3x3()
        bone.rotation_euler=(basis.inverted() @ Matrix.Rotation(angle,3,"Y") @ basis).to_euler("XYZ")
        bone.keyframe_insert("rotation_euler",frame=frame)
    for frame in range(1,frames+1):
        t=math.tau*(frame-1)/frames
        hips=arm.pose.bones[m+"Hips"]
        basis=hips.bone.matrix_local.to_3x3()
        hips.location=basis.inverted() @ Vector((0,-3.0*frame,3*math.cos(2*t)-4))
        hips.keyframe_insert("location",frame=frame)
        world_x(m+"Hips",.08*math.sin(t))
        world_x(m+"Spine1",.12*math.sin(t))
        world_x(m+"LeftUpLeg",.5*math.sin(t)); world_x(m+"RightUpLeg",-.5*math.sin(t))
        world_x(m+"LeftLeg",.3+.35*(1-math.cos(t))); world_x(m+"RightLeg",.3+.35*(1+math.cos(t)))
        world_x(m+"LeftFoot",.2*math.sin(t)); world_x(m+"RightFoot",-.2*math.sin(t))
        # Arms brought down from the T-pose and swung.
        world_y(m+"LeftArm",1.1+.3*math.sin(t)); world_y(m+"RightArm",-1.1+.3*math.sin(t))
        world_y(m+"LeftForeArm",.4); world_y(m+"RightForeArm",-.4)

def cloud_rig(height=1.55,location=(1.5,0,0)):
    """A control rig laid out the CloudRig way: FK- controls on helper parents,
    IK feet, poles, a torso master and an ORG- skeleton that follows them."""
    j=humanoid(height,"A")
    up=lambda point,d=.05*height:(point[0],point[1],point[2]+d)
    bones=[("ROOT",(0,0,0),(0,.2,0),None),
           ("MSTR-Spine_Torso",j["hips"],up(j["hips"],.1),"ROOT"),
           ("MSTR-Spine_Hips",j["hips"],up(j["hips"],-.08),"MSTR-Spine_Torso"),
           ("FK-Spine",j["spine"],j["spine2"],"MSTR-Spine_Torso"),
           ("FK-Chest",j["spine2"],j["neck"],"FK-Spine"),
           ("FK-Neck",j["neck"],j["head"],"FK-Chest"),
           ("FK-Head",j["head"],j["top"],"FK-Neck")]
    chains={"UpperArm":("arm","fore"),"Forearm":("fore","hand"),"Hand":("hand","tip"),
            "Thigh":("thigh","shin"),"Shin":("shin","foot"),"Foot":("foot","toe"),"Toes":("toe","toetip")}
    for side in ("L","R"):
        bones.append((f"FK-Shoulder.{side}",j["clav"+side],j["arm"+side],"FK-Chest"))
        parent=f"FK-Shoulder.{side}"
        for name in ("UpperArm","Forearm","Hand"):
            a,b=chains[name]
            # A helper parent between controls, as generated rigs have.
            bones.append((f"P-FK-{name}.{side}",j[a+side],up(j[a+side]),parent))
            bones.append((f"FK-{name}.{side}",j[a+side],j[b+side],f"P-FK-{name}.{side}"))
            parent=f"FK-{name}.{side}"
        parent="MSTR-Spine_Hips"
        for name in ("Thigh","Shin","Foot","Toes"):
            a,b=chains[name]
            bones.append((f"FK-{name}.{side}",j[a+side],j[b+side],parent))
            parent=f"FK-{name}.{side}"
        heel=(j["foot"+side][0],j["foot"+side][1]+.03*height,0)
        bones.append((f"IK-MSTR-Foot.{side}",heel,(heel[0],heel[1]-.12*height,0),"ROOT"))
        bones.append((f"IK-Foot.{side}",j["foot"+side],j["toe"+side],f"IK-MSTR-Foot.{side}"))
        knee=j["shin"+side]
        bones.append((f"IK-POLE-Leg.{side}",(knee[0],knee[1]-.4*height,knee[2]),(knee[0],knee[1]-.45*height,knee[2]),"ROOT"))
    org=[]
    for name,head,tail,parent in bones:
        if name.startswith("FK-"):
            org.append(("ORG-"+name[3:],head,tail,None))
            org.append(("DEF-"+name[3:]+"1" if "Arm" in name else "DEF-"+name[3:],head,tail,None))
    arm=make_armature("RIG-Character",bones+org,location)
    for bone in arm.pose.bones:
        if bone.name.startswith(("ORG-","DEF-")):
            stem=bone.name[4:]
            control="FK-"+(stem[:-1] if stem.endswith("1") and "Arm" in stem else stem)
            c=bone.constraints.new("COPY_TRANSFORMS")
            c.target,c.subtarget=arm,control
        if bone.name.startswith("FK-"):
            bone.rotation_mode="XYZ" if "Arm" in bone.name else "QUATERNION"
    return arm

def joint_direction(arm,a,b):
    start=arm.matrix_world @ arm.pose.bones[a].matrix.translation
    end=arm.matrix_world @ arm.pose.bones[b].matrix.translation
    return (end-start).normalized()

def compare(source,target,pairs,frames,limit,label):
    """Largest angle between matching limb directions over the frames."""
    worst=0
    detail={}
    for frame in frames:
        scene.frame_set(frame)
        for (sa,sb),(ta,tb) in pairs:
            angle=joint_direction(source,sa,sb).angle(joint_direction(target,ta,tb))
            worst=max(worst,angle)
            detail[ta]=max(detail.get(ta,0),round(math.degrees(angle),2))
    if worst>=limit: print("DETAIL",label,detail)
    check(worst<limit,f"{label}: limb directions differ by {math.degrees(worst):.2f}°")
    return math.degrees(worst)

MX="mixamorig:"
def mixamo_pairs(target_names):
    pairs=[]
    for side,word in (("L","Left"),("R","Right")):
        for (a,b),key in ((("Arm","ForeArm"),"upper_arm"),(("ForeArm","Hand"),"forearm"),
                          (("UpLeg","Leg"),"thigh"),(("Leg","Foot"),"shin"),(("Foot","ToeBase"),"foot")):
            pairs.append(((MX+word+a,MX+word+b),target_names(key,side)))
    return pairs

results={}

# 1 · Name recognition ---------------------------------------------------------
source=mixamo()
animate_mixamo(source)
kind,skeleton,_=retarget.describe(source)
check(kind=="Mixamo skeleton","Mixamo skeleton not recognised: "+kind)
check(skeleton["hips"]==MX+"Hips" and skeleton["spine"]==[MX+"Spine",MX+"Spine1",MX+"Spine2"],"Mixamo torso")
check(skeleton["upper_arm"]=={"L":MX+"LeftArm","R":MX+"RightArm"},"Mixamo upper arms")
check(skeleton["shin"]=={"L":MX+"LeftLeg","R":MX+"RightLeg"},"Mixamo calves")
check(skeleton["toe"]["L"]==MX+"LeftToeBase","Mixamo toe")

cloud=cloud_rig()
kind,cloud_skeleton,cloud_controls=retarget.describe(cloud)
check(kind=="CloudRig-style control rig","control rig not recognised: "+kind)
check(cloud_controls["hips"]=="MSTR-Spine_Torso","torso master: "+cloud_controls["hips"])
check(cloud_controls["upper_arm"]["L"]=="FK-UpperArm.L","FK upper arm")
check(cloud_controls["ik_foot"]=={"L":"IK-MSTR-Foot.L","R":"IK-MSTR-Foot.R"},"IK feet: "+str(cloud_controls["ik_foot"]))
check(cloud_controls["pole_leg"]["R"]=="IK-POLE-Leg.R","knee pole")
check(cloud_skeleton["thigh"]["L"]=="ORG-Thigh.L","ORG skeleton: "+str(cloud_skeleton["thigh"]))
check(cloud_controls["spine"]==["FK-Spine","FK-Chest"],"FK spine: "+str(cloud_controls["spine"]))

# 2 · Mixamo FBX round trip → biped ---------------------------------------------
path=str(output/"mixamo_like.fbx")
bpy.ops.object.select_all(action="DESELECT")
source.select_set(True)
bpy.context.view_layer.objects.active=source
bpy.ops.export_scene.fbx(filepath=path,use_selection=True,object_types={"ARMATURE"},add_leaf_bones=False,
    bake_anim=True,bake_anim_use_all_actions=False,bake_anim_use_nla_strips=False)
p.species="BIPED"
biped=rig.build(bpy.context,p)
check(not rig.validate(biped),"biped validation")
check(len(biped.data.bones)==58,f"biped bone count {len(biped.data.bones)}")
for name in ("clavicle.L","toe.R","index.03.L","thumb.01.R"):
    check(name in biped.data.bones,"biped is missing "+name)
check(bpy.ops.chimera_kit.import_mixamo(filepath=path)=={"FINISHED"},"FBX import")
imported=p.rt_source
check(imported and imported!=source and imported.get("cs_motion_source"),"imported armature not selected as source")
check(p.rt_target==biped,"active creature not chosen as target")
check(sum(1 for i in p.rt_items if i.source and i.target)>=17,"too few bones mapped to biped")
check(bpy.ops.chimera_kit.retarget_run()=={"FINISHED"},"retarget to biped")
action=biped.animation_data.action
check(action and action.get("cs_retarget"),"no retarget action on biped")
frames=range(p.rt_frame_start,p.rt_frame_end+1,3)
def biped_names(key,side):
    return {"upper_arm":(f"arm.{side}",f"forearm.{side}"),"forearm":(f"forearm.{side}",f"hand.{side}"),
            "thigh":(f"leg.01.{side}.upper",f"leg.01.{side}.lower"),"shin":(f"leg.01.{side}.lower",f"leg.01.{side}.foot"),
            "foot":(f"leg.01.{side}.foot",f"toe.{side}")}[key]
arm_pairs=[pair for pair in mixamo_pairs(biped_names) if "Arm" in pair[0][0]]
leg_pairs=[pair for pair in mixamo_pairs(biped_names) if "Arm" not in pair[0][0]]
results["mixamo_to_biped_arms_deg"]=compare(imported,biped,arm_pairs,frames,math.radians(.5),"Mixamo → biped arms")
# IK legs reproduce foot placement first; a different thigh/calf ratio shifts the knee.
results["mixamo_to_biped_legs_deg"]=compare(imported,biped,leg_pairs,frames,math.radians(9),"Mixamo → biped legs")
ratio=retarget.leg_length(biped,{r.slot:{"ref":r.ref} for r in p.rt_items},"ref")/ \
      retarget.leg_length(imported,{r.slot:{"source":r.source} for r in p.rt_items},"source")
def hip_middle(arm,left,right):
    return ((arm.matrix_world @ arm.pose.bones[left].matrix.translation)+(arm.matrix_world @ arm.pose.bones[right].matrix.translation))*.5
scene.frame_set(p.rt_frame_start)
a_src=hip_middle(imported,MX+"LeftUpLeg",MX+"RightUpLeg")
a_tgt=hip_middle(biped,"leg.01.L.upper","leg.01.R.upper")
scene.frame_set(p.rt_frame_start+30)
b_src=hip_middle(imported,MX+"LeftUpLeg",MX+"RightUpLeg")
b_tgt=hip_middle(biped,"leg.01.L.upper","leg.01.R.upper")
check(((b_tgt-a_tgt)-(b_src-a_src)*ratio).length<.002,"hips travel is not scaled by leg length")
check((b_tgt-a_tgt).length>.5,"biped did not travel")
results["size_ratio"]=ratio

# 3 · In place -----------------------------------------------------------------
p.rt_in_place=True
check(bpy.ops.chimera_kit.retarget_run()=={"FINISHED"},"in-place retarget")
scene.frame_set(p.rt_frame_start); a=hip_middle(biped,"leg.01.L.upper","leg.01.R.upper")
scene.frame_set(p.rt_frame_start+30); b=hip_middle(biped,"leg.01.L.upper","leg.01.R.upper")
check(abs(b.x-a.x)<1e-4 and abs(b.y-a.y)<1e-4,"in-place hips still travel")
p.rt_in_place=False

# 4 · Mixamo → CloudRig-style rig ----------------------------------------------
p.rt_source,p.rt_target=imported,cloud
check(bpy.ops.chimera_kit.retarget_automap()=={"FINISHED"},"automap to control rig")
check(bpy.ops.chimera_kit.retarget_run()=={"FINISHED"},"retarget to control rig")
def cloud_names(key,side):
    return {"upper_arm":(f"ORG-UpperArm.{side}",f"ORG-Forearm.{side}"),"forearm":(f"ORG-Forearm.{side}",f"ORG-Hand.{side}"),
            "thigh":(f"ORG-Thigh.{side}",f"ORG-Shin.{side}"),"shin":(f"ORG-Shin.{side}",f"ORG-Foot.{side}"),
            "foot":(f"ORG-Foot.{side}",f"ORG-Toes.{side}")}[key]
results["mixamo_to_control_rig_deg"]=compare(imported,cloud,mixamo_pairs(cloud_names),frames,math.radians(.5),"Mixamo → control rig")
paths={fc.data_path for fc in motion.curves(cloud.animation_data.action)}
for name in ("FK-UpperArm.L","FK-Thigh.R","IK-MSTR-Foot.L","IK-POLE-Leg.L","MSTR-Spine_Torso"):
    check(any(f'["{name}"]' in path for path in paths),"no keys on "+name)
check(not any('["ORG-' in path or '["P-FK' in path or '["IK-Foot.' in path for path in paths),"helper bones were keyed")
check(not any(c.name==retarget.CONSTRAINT_NAME for b in cloud.pose.bones for c in b.constraints),"temporary constraints left behind")
check(retarget.HELPER_NAME not in bpy.data.objects,"helper armature left behind")
# The IK foot control must track the ankle, including its heel pivot offset.
scale=retarget.leg_length(cloud,{r.slot:{"ref":r.ref} for r in p.rt_items},"ref")/ \
      retarget.leg_length(imported,{r.slot:{"source":r.source} for r in p.rt_items},"source")
ground=min((imported.matrix_world @ imported.pose.bones[MX+word+"Foot"].matrix.translation).z
           for frame in range(p.rt_frame_start,p.rt_frame_end+1) if not scene.frame_set(frame) for word in ("Left","Right"))
origin_src=Vector((imported.matrix_world.translation.x,imported.matrix_world.translation.y,ground))
middle=(cloud.matrix_world @ cloud.data.bones["ORG-Thigh.L"].head_local+cloud.matrix_world @ cloud.data.bones["ORG-Thigh.R"].head_local)*.5
origin_tgt=Vector((middle.x,middle.y,(cloud.matrix_world @ cloud.data.bones["ORG-Foot.L"].head_local).z))
worst=0
for frame in frames:
    scene.frame_set(frame)
    ankle=imported.matrix_world @ imported.pose.bones[MX+"LeftFoot"].matrix.translation
    expected=origin_tgt+(ankle-origin_src)*scale
    ik=cloud.matrix_world @ cloud.pose.bones["IK-Foot.L"].matrix.translation
    worst=max(worst,(ik-expected).length)
check(worst<.002,f"IK foot is {worst:.4f} m from the scaled ankle path")
results["ik_foot_error_m"]=worst

# 5 · Generated walk with layers → CloudRig-style rig --------------------------
p.rt_leg_mode="BOTH"
p.species="BIPED"
p.cycle_frames=24
p.cycles=3
p.travel=True
p.gait="WALK"
walker=rig.build(bpy.context,p)
walker.location=(-1.5,0,0)
motion.generate(bpy.context,walker,p)
p.rt_source,p.rt_target=walker,cloud
check(bpy.ops.chimera_kit.retarget_run()=={"FINISHED"},"creature → control rig")
check(p.rt_source_kind=="Chimera Kit rig","creature not recognised as source")
frames=range(scene.frame_start,scene.frame_end+1,2)
def walker_pairs():
    pairs=[]
    for side in ("L","R"):
        for key in ("upper_arm","forearm","thigh","shin","foot"):
            pairs.append((biped_names(key,side),cloud_names(key,side)))
    return pairs
results["creature_to_control_rig_deg"]=compare(walker,cloud,walker_pairs(),frames,math.radians(.5),"creature → control rig")
# A planted creature foot must give a planted IK control: no sliding.
limb=json.loads(walker["cs_limbs"])[0]
positions=[]
source_positions=[]
for frame in range(scene.frame_start+1,scene.frame_start+8):
    scene.frame_set(frame)
    source_positions.append(walker.matrix_world @ walker.pose.bones[limb["control"]].matrix.translation)
    positions.append(cloud.matrix_world @ cloud.pose.bones["IK-MSTR-Foot.L"].matrix.translation)
check(max((v-source_positions[0]).length for v in source_positions)<1e-4,"source stance foot is not planted")
check(max((v-positions[0]).length for v in positions)<1e-3,"planted foot slides on the control rig")

# 6 · Control rig → plain skeleton, and a saved bone map ------------------------
p.rt_source,p.rt_target=cloud,source
check(bpy.ops.chimera_kit.retarget_run()=={"FINISHED"},"control rig → Mixamo skeleton")
check(p.rt_source_kind=="CloudRig-style control rig" and p.rt_target_kind=="Mixamo skeleton","pair kinds")
pairs=[(b,a) for a,b in mixamo_pairs(cloud_names)]
results["control_rig_to_mixamo_deg"]=compare(cloud,source,pairs,frames,math.radians(.5),"control rig → skeleton")
p.io_path=str(output/"bone_map.json")
count=len(p.rt_items)
check(bpy.ops.chimera_kit.retarget_map_file(operation="SAVE")=={"FINISHED"},"save bone map")
p.rt_items.clear()
check(bpy.ops.chimera_kit.retarget_map_file(operation="LOAD")=={"FINISHED"},"load bone map")
check(len(p.rt_items)==count,"bone map round trip")

# 7 · Panel properties ----------------------------------------------------------
for name in ("rt_source","rt_target","rt_leg_mode","rt_align_rest","rt_in_place","rt_height_offset","mannequin_style","fingers"):
    check(name in p.bl_rna.properties,"missing property "+name)
print("CHIMERA_KIT_RETARGET_PASSED",json.dumps(results))
cs.unregister()
