"""Retarget motion between armatures: Chimera Kit rigs, Mixamo skeletons,
CloudRig / Rigify-style control rigs and plain FK skeletons.

The source is sampled in world space on every frame. Each mapped target bone
receives the source bone's world rotation change, corrected for any difference
between the two rest poses. Hips and IK feet also receive scaled world
translation. Temporary world-space constraints drive the target controls while
the result is keyed, so the target's own parenting never has to be understood.
"""
import json
import math
import re
import bpy
from mathutils import Matrix, Quaternion, Vector

SIDES=("L","R")
FINGERS=("thumb","index","middle","ring","pinky")
LIMB_SLOTS=("shoulder","upper_arm","forearm","hand","thigh","shin","foot","toe")
# Slot whose head gives each slot its rest direction.
CHILD={"shoulder":"upper_arm","upper_arm":"forearm","forearm":"hand","thigh":"shin","shin":"foot","foot":"toe"}
# Leaf slots without a mapped child reuse the correction of this slot.
INHERIT={"hand":"forearm","toe":"foot"}

SYNONYMS={
    "hips":{"hips","hip","pelvis"},
    "neck":{"neck"},
    "head":{"head"},
    "shoulder":{"shoulder","clavicle","collar","collarbone"},
    "upper_arm":{"upperarm","arm","uparm","armupper","bicep"},
    "forearm":{"forearm","lowerarm","armlower","lowarm","elbow"},
    "hand":{"hand","wrist"},
    "thigh":{"thigh","upleg","upperleg","legupper"},
    "shin":{"shin","calf","lowerleg","leglower","lowleg","leg","knee"},
    "foot":{"foot","ankle"},
    "toe":{"toe","toes","toebase","ball"},
}
SPINE_WORDS=("spine","chest","ribcage","abdomen","waist","belly","stomach","upperchest")
FINGER_WORDS={"thumb":("thumb",),"index":("index","pointer"),"middle":("middle","mid"),
              "ring":("ring",),"pinky":("pinky","little","pinkie")}
PREFIXES=("DEF","ORG","MCH","STR","TGT","FK","IK","CTRL","POLE","MSTR","ROOT","TWK","VIS","P","WGT","CON","SKH","PSX")

def parse(name):
    """Split a bone name into rig-layer classes, a letters-only core, a side and a number."""
    text=name.split(":")[-1]
    classes=[]
    while True:
        match=re.match(r"^([A-Za-z]+)[-_]",text)
        if match and match.group(1).upper() in PREFIXES:
            classes.append(match.group(1).upper())
            text=text[match.end():]
        else:
            break
    for suffix,cls in (("_fk","FK"),(".fk","FK"),("_ik","IK"),(".ik","IK")):
        found=re.search(re.escape(suffix)+r"(?=$|[._\- ])",text,re.I)
        if found:
            classes.append(cls)
            text=text[:found.start()]+text[found.end():]
    side=""
    match=re.search(r"[._\- ]([LlRr])(?=$|[._\- ]\d+$|\.)",text)
    if match:
        side=match.group(1).upper()
        text=text[:match.start()]+text[match.end():]
    else:
        match=re.match(r"^(left|right)",text,re.I) or re.search(r"(left|right)$",text,re.I) \
            or re.match(r"^([lr])[_\-. ]",text,re.I)
        if match:
            side=match.group(1)[0].upper()
            text=text[:match.start()]+text[match.end():]
    digits=re.findall(r"\d+",text)
    core=re.sub(r"[^a-z]","",text.lower())
    return dict(name=name,classes=tuple(classes),core=core,side=side,number=int(digits[-1]) if digits else 0)

def depth(bone):
    count=0
    while bone.parent:
        bone=bone.parent
        count+=1
    return count

def finger_of(core):
    for finger,words in FINGER_WORDS.items():
        for word in words:
            if core in {word,"hand"+word,"f"+word,word+"finger","finger"+word}:
                return finger
    return None

def empty_layout():
    layout={"hips":"","spine":[],"neck":"","head":"","ik_foot":{},"pole_leg":{},"fingers":{}}
    for slot in LIMB_SLOTS:
        layout[slot]={}
    return layout

def match_layer(arm,wanted):
    """Find humanoid slots among bones of one rig layer ('' means unprefixed)."""
    layout=empty_layout()
    spine=[]
    best={}
    def offer(key,bone,info):
        score=(info["number"],depth(bone),len(bone.name))
        if key not in best or score<best[key][0]:
            best[key]=(score,bone.name)
    for bone in arm.data.bones:
        info=parse(bone.name)
        layer=info["classes"][0] if info["classes"] else ""
        if layer!=wanted or len(info["classes"])>1:
            continue
        core,side=info["core"],info["side"]
        if not side:
            if core in SYNONYMS["hips"]: offer(("hips",),bone,info)
            elif core in SYNONYMS["head"]: offer(("head",),bone,info)
            elif core.startswith("neck"): offer(("neck",),bone,info)
            elif core.startswith(SPINE_WORDS): spine.append(bone)
            continue
        finger=finger_of(core)
        if finger:
            layout["fingers"].setdefault((finger,side),[]).append(bone)
            continue
        for slot in LIMB_SLOTS:
            if core in SYNONYMS[slot]:
                offer((slot,side),bone,info)
                break
    for key,(_,name) in best.items():
        if len(key)==1: layout[key[0]]=name
        else: layout[key[0]][key[1]]=name
    # A chain's order is its height in the rest pose, whatever it is called.
    spine.sort(key=lambda b:(arm.matrix_world @ b.head_local).z)
    layout["spine"]=[b.name for b in spine]
    layout["fingers"]={key:[b.name for b in sorted(bones,key=depth)][:3]
                       for key,bones in layout["fingers"].items()}
    return layout

def score(layout):
    total=bool(layout["hips"])+bool(layout["head"])+bool(layout["neck"])+min(len(layout["spine"]),2)
    return total+sum(len(layout[slot]) for slot in LIMB_SLOTS)

def cs_layout(arm):
    """Explicit layout of a Chimera Kit rig: (skeleton, controls)."""
    names=set(arm.data.bones.keys())
    skeleton=empty_layout()
    skeleton["hips"]="pelvis" if "pelvis" in names else ""
    skeleton["spine"]=sorted(n for n in names if re.fullmatch(r"spine\.\d+",n))
    skeleton["neck"]="neck" if "neck" in names else ""
    skeleton["head"]="head" if "head" in names else ""
    limbs=json.loads(arm.get("cs_limbs","[]"))
    controls=json.loads(json.dumps(skeleton))
    controls["fingers"]={}
    controls["hips"]="CTRL-body" if "CTRL-body" in names else ""
    for side in SIDES:
        for slot,name in (("shoulder",f"clavicle.{side}"),("upper_arm",f"arm.{side}"),
                          ("forearm",f"forearm.{side}"),("hand",f"hand.{side}"),("toe",f"toe.{side}")):
            if name in names:
                skeleton[slot][side]=controls[slot][side]=name
        # The walking legs of an upright rig are its first leg pair.
        limb=next((l for l in limbs if l["index"]==0 and l["side"]==(1 if side=="L" else -1)),None)
        if limb:
            skeleton["thigh"][side]=limb["upper"]
            skeleton["shin"][side]=limb["lower"]
            skeleton["foot"][side]=limb["foot"]
            controls["ik_foot"][side]=limb["control"]
            controls["pole_leg"][side]=limb["pole"]
        for finger in FINGERS:
            chain=sorted(n for n in names if re.fullmatch(finger+r"\.\d+\."+side,n))
            if chain:
                skeleton["fingers"][(finger,side)]=controls["fingers"][(finger,side)]=chain
    return skeleton,controls

def describe(arm):
    """Return (kind, skeleton layout, control layout) for any armature.

    The skeleton layout names bones that carry the final pose and give rest
    geometry. The control layout names what an animator keys."""
    if arm.get("cs_rig"):
        skeleton,controls=cs_layout(arm)
        return "Chimera Kit rig",skeleton,controls
    layers={layer:match_layer(arm,layer) for layer in ("","ORG","DEF","FK")}
    fk=layers["FK"]
    if score(fk)>=6:
        # A control rig: key FK controls, plus IK feet and a torso master.
        skeleton=max((layers["ORG"],layers["DEF"],fk),key=score)
        if score(layers["ORG"])>=score(skeleton)-1 and score(layers["ORG"])>=6:
            skeleton=layers["ORG"]
        controls=json.loads(json.dumps({k:v for k,v in fk.items() if k!="fingers"}))
        controls["fingers"]=dict(fk["fingers"])
        torso=[]
        feet={}
        poles={}
        for bone in arm.data.bones:
            info=parse(bone.name)
            classes=info["classes"]
            if {"DEF","ORG","MCH","STR","TGT","VIS","WGT","TWK","CON","SKH","PSX","P"} & set(classes):
                continue
            core,side=info["core"],info["side"]
            if not side and ("torso" in core or core in {"cog","com"}):
                torso.append((len(bone.name),bone.name))
            if side and "IK" in classes and "foot" in core and "POLE" not in classes and "pole" not in core \
                    and "roll" not in core and "heel" not in core:
                # Prefer a master control over the bare IK target.
                rank=(0 if "MSTR" in classes else 1,len(bone.name))
                if side not in feet or rank<feet[side][0]:
                    feet[side]=(rank,bone.name)
            if side and ("POLE" in classes or "pole" in core) and any(w in core for w in ("leg","knee","thigh","shin","foot")):
                rank=len(bone.name)
                if side not in poles or rank<poles[side][0]:
                    poles[side]=(rank,bone.name)
        if torso:
            controls["hips"]=min(torso)[1]
        elif not controls["hips"]:
            plain=layers[""]
            controls["hips"]=plain["hips"] or skeleton["hips"]
        if not skeleton["hips"]:
            skeleton["hips"]=controls["hips"]
        controls["ik_foot"]={side:value[1] for side,value in feet.items()}
        controls["pole_leg"]={side:value[1] for side,value in poles.items()}
        kind="CloudRig-style control rig" if any(b.name.startswith("FK-") for b in arm.data.bones) else "Control rig"
        return kind,skeleton,controls
    skeleton=max((layers[""],layers["ORG"],layers["DEF"]),key=score)
    mixamo=any("mixamorig" in b.name.lower() for b in arm.data.bones)
    return ("Mixamo skeleton" if mixamo else "Skeleton"),skeleton,skeleton

def spread(source_chain,target_chain):
    """Pair every target chain bone with the source bone at the same relative height."""
    pairs=[]
    ns,nt=len(source_chain),len(target_chain)
    if not ns or not nt:
        return pairs
    for j,name in enumerate(target_chain):
        index=round(j*(ns-1)/(nt-1)) if nt>1 else ns-1
        pairs.append((source_chain[index],name))
    return pairs

def automap(source,target):
    """Build mapping rows: dict(slot,label,kind,source,target,ref)."""
    source_kind,src,_=describe(source)
    target_kind,ref,ctl=describe(target)
    rows=[]
    def row(slot,label,kind,source_bone,target_bone,ref_bone=""):
        if source_bone or target_bone:
            rows.append(dict(slot=slot,label=label,kind=kind,source=source_bone or "",
                             target=target_bone or "",ref=ref_bone or target_bone or ""))
    row("hips","Hips","HIPS",src["hips"],ctl["hips"],ref["hips"])
    ref_spine=spread(ref["spine"],ctl["spine"])
    for index,(source_bone,target_bone) in enumerate(spread(src["spine"],ctl["spine"])):
        row(f"spine.{index+1}",f"Spine {index+1}","ROT",source_bone,target_bone,
            ref_spine[index][0] if index<len(ref_spine) else target_bone)
    row("neck","Neck","ROT",src["neck"],ctl["neck"],ref["neck"])
    row("head","Head","ROT",src["head"],ctl["head"],ref["head"])
    labels={"shoulder":"Clavicle","upper_arm":"Upper arm","forearm":"Forearm","hand":"Hand",
            "thigh":"Thigh","shin":"Calf","foot":"Foot","toe":"Toe"}
    for side in SIDES:
        for slot in LIMB_SLOTS:
            row(f"{slot}.{side}",f"{labels[slot]} {side}","ROT",src[slot].get(side),
                ctl[slot].get(side),ref[slot].get(side))
        if ctl["ik_foot"].get(side):
            row(f"ik_foot.{side}",f"IK foot {side}","IK_FOOT",src["foot"].get(side),
                ctl["ik_foot"][side],ref["foot"].get(side))
        if ctl["pole_leg"].get(side):
            row(f"pole_leg.{side}",f"Knee pole {side}","POLE",src["shin"].get(side),
                ctl["pole_leg"][side],ref["shin"].get(side))
    for side in SIDES:
        for finger in FINGERS:
            source_chain=src["fingers"].get((finger,side),[])
            target_chain=ctl["fingers"].get((finger,side),[])
            ref_chain=ref["fingers"].get((finger,side),target_chain)
            for index in range(min(len(source_chain),len(target_chain))):
                row(f"{finger}.{index+1}.{side}",f"{finger.title()} {index+1} {side}","ROT",
                    source_chain[index],target_chain[index],
                    ref_chain[index] if index<len(ref_chain) else target_chain[index])
    return source_kind,target_kind,rows

def slot_base(slot):
    parts=slot.split(".")
    side=parts[-1] if parts[-1] in SIDES else ""
    return parts[0],side

def rest_matrix(arm,name):
    return arm.matrix_world @ arm.data.bones[name].matrix_local

def rotation_of(matrix):
    return matrix.to_3x3().normalized().to_quaternion()

def leg_length(arm,layout_rows,which):
    """Average hip-to-ankle chain length in world units, or 0."""
    lengths=[]
    for side in SIDES:
        names=[layout_rows.get(f"{slot}.{side}",{}).get(which) for slot in ("thigh","shin","foot")]
        if all(names) and all(n in arm.data.bones for n in names):
            a,b,c=(rest_matrix(arm,n).translation for n in names)
            lengths.append((b-a).length+(c-b).length)
    return sum(lengths)/len(lengths) if lengths else 0

def action_range(arm):
    data=arm.animation_data
    if data and data.action:
        start,end=data.action.frame_range
        return int(math.floor(start)),int(math.ceil(end))
    if data and data.nla_tracks:
        strips=[s for t in data.nla_tracks if not t.mute for s in t.strips]
        if strips:
            return int(min(s.frame_start for s in strips)),int(max(s.frame_end for s in strips))
    return None

def ensure_fcurve(action,obj,path,index,group):
    if hasattr(action,"fcurve_ensure_for_datablock"):
        return action.fcurve_ensure_for_datablock(obj,path,index=index,group_name=group)
    curve=action.fcurves.find(path,index=index)
    return curve or action.fcurves.new(path,index=index,action_group=group)

def write_curve(action,obj,path,index,group,frames,values):
    curve=ensure_fcurve(action,obj,path,index,group)
    curve.keyframe_points.clear()
    curve.keyframe_points.add(len(frames))
    flat=[0.0]*(2*len(frames))
    flat[0::2]=[float(f) for f in frames]
    flat[1::2]=[float(v) for v in values]
    curve.keyframe_points.foreach_set("co",flat)
    for point in curve.keyframe_points:
        point.interpolation="LINEAR"
    curve.update()

HELPER_NAME="CK · Retarget helper"
CONSTRAINT_NAME="CK · Retarget"

def retarget(context,source,target,rows,frame_start,frame_end,align_rest=True,in_place=False,
             leg_mode="BOTH",height_offset=0.0,action_name=""):
    """Key `target` so that it performs `source`'s motion. Returns the new action."""
    if source==target:
        raise ValueError("Choose two different armatures")
    if frame_end<frame_start:
        raise ValueError("The frame range is empty")
    by_slot={}
    for r in rows:
        by_slot[r["slot"]]=r
    usable=[]
    for r in rows:
        if not r["source"] or not r["target"]:
            continue
        if r["source"] not in source.data.bones:
            raise ValueError("Source bone not found: "+r["source"])
        if r["target"] not in target.data.bones:
            raise ValueError("Target bone not found: "+r["target"])
        if not r.get("ref") or r["ref"] not in target.data.bones:
            r=dict(r,ref=r["target"])
        base,_=slot_base(r["slot"])
        if leg_mode=="IK" and base in {"thigh","shin","foot"} and by_slot.get("ik_foot."+r["slot"].split(".")[-1],{}).get("target"):
            continue
        if leg_mode=="FK" and r["kind"] in {"IK_FOOT","POLE"}:
            continue
        usable.append(r)
    if not usable:
        raise ValueError("No bones are mapped. Run Auto-map or fill in the table")
    lookup={r["slot"]:r for r in usable}

    # Rest geometry. A chain bone's direction runs to the next mapped joint.
    def direction(arm,which,r):
        base,side=slot_base(r["slot"])
        if base.startswith("spine"):
            index=int(r["slot"].split(".")[1])
            nxt=by_slot.get(f"spine.{index+1}") or by_slot.get("neck")
        elif base in FINGERS:
            index=int(r["slot"].split(".")[1])
            nxt=by_slot.get(f"{base}.{index+1}.{side}")
        elif base=="neck":
            nxt=by_slot.get("head")
        elif base in {"ik_foot"}:
            nxt=by_slot.get("toe."+side)
        elif base=="hand":
            nxt=by_slot.get(f"middle.1.{side}")
        else:
            nxt=by_slot.get(f"{CHILD[base]}.{side}") if base in CHILD else None
        mine=r[which] if which=="source" else r["ref"]
        other=(nxt or {}).get(which if which=="source" else "ref")
        if not other or other not in arm.data.bones or other==mine:
            return None
        vector=rest_matrix(arm,other).translation-rest_matrix(arm,mine).translation
        return vector.normalized() if vector.length>1e-6 else None

    align={}
    for r in usable:
        correction=Quaternion()
        if align_rest and r["kind"] in {"ROT","IK_FOOT"} and slot_base(r["slot"])[0]!="head":
            a=direction(source,"source",r)
            b=direction(target,"ref",r)
            if a and b:
                correction=b.rotation_difference(a)
            else:
                correction=None
        align[r["slot"]]=correction
    for r in usable:
        if align[r["slot"]] is None:
            base,side=slot_base(r["slot"])
            parent=INHERIT.get(base)
            if base in FINGERS:
                index=int(r["slot"].split(".")[1])
                inherited=align.get(f"{base}.{index-1}.{side}")
            else:
                inherited=align.get(f"{parent}.{side}") if parent else None
            align[r["slot"]]=inherited or Quaternion()

    source_rest={r["slot"]:rest_matrix(source,r["source"]) for r in usable}
    target_rest={r["slot"]:rest_matrix(target,r["target"]) for r in usable}
    ref_rest={r["slot"]:rest_matrix(target,r["ref"]) for r in usable}
    source_rest_rot={slot:rotation_of(m) for slot,m in source_rest.items()}
    target_rest_rot={slot:rotation_of(m) for slot,m in target_rest.items()}
    source_legs=leg_length(source,by_slot,"source")
    target_legs=leg_length(target,by_slot,"ref")
    if source_legs>1e-6 and target_legs>1e-6:
        scale=target_legs/source_legs
    else:
        hips=by_slot.get("hips")
        a=rest_matrix(source,hips["source"]).translation.z-source.matrix_world.translation.z if hips and hips["source"] in source.data.bones else 0
        b=rest_matrix(target,hips["ref"] if hips.get("ref") in target.data.bones else hips["target"]).translation.z-target.matrix_world.translation.z \
            if hips and hips["target"] in target.data.bones else 0
        scale=b/a if a>1e-6 and b>1e-6 else 1.0

    scene=context.scene
    view_layer=context.view_layer
    previous_frame=scene.frame_current
    if context.object and context.object.mode!="OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")

    # Helper armature: one free bone per driven control, posed in world space.
    data=bpy.data.armatures.new(HELPER_NAME)
    helper=bpy.data.objects.new(HELPER_NAME,data)
    scene.collection.objects.link(helper)
    helper["cs_owned"]=True
    view_layer.objects.active=helper
    bpy.ops.object.mode_set(mode="EDIT")
    helper_name={}
    for index,r in enumerate(usable):
        bone=data.edit_bones.new(f"H{index:03d}")
        bone.head=(0,0,0)
        bone.tail=(0,.1,0)
        helper_name[r["slot"]]=bone.name
    bpy.ops.object.mode_set(mode="OBJECT")
    helper_rest_inverse={slot:data.bones[name].matrix_local.inverted() for slot,name in helper_name.items()}
    for bone in helper.pose.bones:
        bone.rotation_mode="QUATERNION"

    added=[]
    def constrain(pose_bone,kind,subtarget):
        c=pose_bone.constraints.new(kind)
        c.name=CONSTRAINT_NAME
        c.target=helper
        c.subtarget=subtarget
        c.target_space=c.owner_space="WORLD"
        added.append((pose_bone,c))
    for r in usable:
        pose_bone=target.pose.bones[r["target"]]
        if r["kind"] in {"HIPS","IK_FOOT","POLE"}:
            constrain(pose_bone,"COPY_LOCATION",helper_name[r["slot"]])
        if r["kind"]!="POLE":
            constrain(pose_bone,"COPY_ROTATION",helper_name[r["slot"]])

    frames=list(range(frame_start,frame_end+1))
    samples={r["slot"]:{"loc":[],"rot":[]} for r in usable}
    source_inverse_rest={slot:q.inverted() for slot,q in source_rest_rot.items()}
    hips_row=lookup.get("hips")

    # Leg joints anchor all translation, so neither rest pose has to be a
    # neutral stand: hips and ankles are measured from the ground up.
    joints={}
    for side in SIDES:
        thigh,foot=by_slot.get("thigh."+side),by_slot.get("foot."+side)
        if thigh and foot and thigh["source"] in source.data.bones and foot["source"] in source.data.bones \
                and thigh.get("ref") in target.data.bones and foot.get("ref") in target.data.bones:
            joints[side]=(thigh,foot)
    grounded=len(joints)==2 and source_legs>1e-6 and target_legs>1e-6
    try:
        # Pass 1: sample the source in world space.
        track=[]
        for frame in frames:
            scene.frame_set(frame)
            world={r["slot"]:source.matrix_world @ source.pose.bones[r["source"]].matrix for r in usable}
            legs={side:((source.matrix_world @ source.pose.bones[thigh["source"]].matrix).translation,
                        (source.matrix_world @ source.pose.bones[foot["source"]].matrix).translation)
                  for side,(thigh,foot) in joints.items()}
            track.append((world,legs))
        if grounded:
            source_ground=min(ankle.z for _,legs in track for _,ankle in legs.values())
            source_origin=Vector((source.matrix_world.translation.x,source.matrix_world.translation.y,source_ground))
            hip_rest={side:rest_matrix(target,thigh["ref"]).translation for side,(thigh,foot) in joints.items()}
            ankle_rest={side:rest_matrix(target,foot["ref"]).translation for side,(thigh,foot) in joints.items()}
            target_middle=(hip_rest["L"]+hip_rest["R"])*.5
            target_origin=Vector((target_middle.x,target_middle.y,min(v.z for v in ankle_rest.values())))
        # Pass 2: pose the helper, let the constraints drive the controls, read them back.
        for frame,(world,legs) in zip(frames,track):
            scene.frame_set(frame)
            delta={slot:rotation_of(m) @ source_inverse_rest[slot] for slot,m in world.items()}
            travel=Vector((0,0,0))
            if grounded:
                middle=(legs["L"][0]+legs["R"][0])*.5
                if in_place:
                    travel=Vector((middle.x-source_origin.x,middle.y-source_origin.y,0))
                def place(point):
                    return target_origin+(point-travel-source_origin)*scale
                ankles={side:place(legs[side][1]) for side in SIDES}
            elif in_place and hips_row:
                travel=world["hips"].translation-source_rest["hips"].translation
                travel.z=0
            desired={}
            for r in usable:
                slot=r["slot"]
                swing=delta[slot] @ align[slot]
                rotation=swing @ target_rest_rot[slot]
                location=target_rest[slot].translation.copy()
                side=slot_base(slot)[1]
                if r["kind"]=="HIPS":
                    if grounded:
                        # Carry the control rigidly with the hip joints.
                        location=place(middle)+swing @ (target_rest[slot].translation-target_middle)
                    else:
                        location=location+(world[slot].translation-source_rest[slot].translation-travel)*scale
                    location.z+=height_offset
                elif r["kind"]=="IK_FOOT":
                    if grounded:
                        ankle=ankles[side]
                    else:
                        ankle=ref_rest[slot].translation+(world[slot].translation-source_rest[slot].translation-travel)*scale
                    # The control may pivot away from the ankle, e.g. at the heel.
                    location=ankle+swing @ (target_rest[slot].translation-ref_rest[slot].translation)
                elif r["kind"]=="POLE" and side in legs:
                    hip,ankle=legs[side]
                    knee=world[slot].translation
                    line=ankle-hip
                    bend=(knee-hip)-line*((knee-hip).dot(line)/max(line.length_squared,1e-9))
                    if bend.length<1e-4*max(line.length,1e-9):
                        # A straight leg has no bend plane; aim where the knee faces.
                        bend=rotation_of(world[slot]) @ source_inverse_rest[slot] @ Vector((0,-1,0))
                    target_ankle=ankles[side] if grounded else ref_rest[slot].translation
                    location=target_ankle-line*.5*scale+bend.normalized()*max(target_legs,line.length*scale)*.75
                desired[slot]=(location,rotation)
            for slot,(location,rotation) in desired.items():
                matrix=Matrix.Translation(location) @ rotation.to_matrix().to_4x4()
                helper.pose.bones[helper_name[slot]].matrix_basis=helper_rest_inverse[slot] @ matrix
            helper.update_tag()
            view_layer.update()
            for r in usable:
                pose_bone=target.pose.bones[r["target"]]
                local=target.convert_space(pose_bone=pose_bone,matrix=pose_bone.matrix,
                                           from_space="POSE",to_space="LOCAL")
                samples[r["slot"]]["loc"].append(local.to_translation())
                samples[r["slot"]]["rot"].append(local.to_quaternion())
    finally:
        for pose_bone,constraint in added:
            pose_bone.constraints.remove(constraint)
        bpy.data.objects.remove(helper,do_unlink=True)
        bpy.data.armatures.remove(data)

    target.animation_data_create()
    animation=target.animation_data
    if animation.action:
        animation.action.use_fake_user=True
    action=bpy.data.actions.new(action_name or f"{target.name} · from {source.name}")
    action.use_fake_user=True
    action["cs_retarget"]=True
    action["cs_retarget_source"]=source.name
    animation.action=action
    for r in usable:
        pose_bone=target.pose.bones[r["target"]]
        group=r["target"]
        data_samples=samples[r["slot"]]
        base=pose_bone.path_from_id()
        if r["kind"] in {"HIPS","IK_FOOT","POLE"}:
            for axis in range(3):
                write_curve(action,target,base+".location",axis,group,frames,[v[axis] for v in data_samples["loc"]])
        if r["kind"]=="POLE":
            continue
        mode=pose_bone.rotation_mode
        if mode=="QUATERNION":
            previous=None
            values=[]
            for q in data_samples["rot"]:
                if previous is not None:
                    q.make_compatible(previous)
                previous=q
                values.append(q)
            for axis in range(4):
                write_curve(action,target,base+".rotation_quaternion",axis,group,frames,[q[axis] for q in values])
        elif mode=="AXIS_ANGLE":
            values=[]
            for q in data_samples["rot"]:
                axis_vector,angle=q.to_axis_angle()
                values.append((angle,axis_vector.x,axis_vector.y,axis_vector.z))
            for axis in range(4):
                write_curve(action,target,base+".rotation_axis_angle",axis,group,frames,[v[axis] for v in values])
        else:
            previous=None
            values=[]
            for q in data_samples["rot"]:
                euler=q.to_euler(mode,previous) if previous is not None else q.to_euler(mode)
                previous=euler
                values.append(euler)
            for axis in range(3):
                write_curve(action,target,base+".rotation_euler",axis,group,frames,[e[axis] for e in values])
    target.update_tag()
    scene.frame_set(previous_frame)
    return action,len(usable),scale

def import_fbx(context,filepath):
    """Import an FBX and return its armature. Mixamo files need no special options."""
    before=set(bpy.data.objects)
    if context.object and context.object.mode!="OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.import_scene.fbx(filepath=filepath,ignore_leaf_bones=False,automatic_bone_orientation=False)
    created=[obj for obj in bpy.data.objects if obj not in before]
    armatures=[obj for obj in created if obj.type=="ARMATURE"]
    if not armatures:
        raise ValueError("The file contains no skeleton")
    return max(armatures,key=lambda obj:len(obj.data.bones)),created
