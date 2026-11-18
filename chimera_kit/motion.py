"""Stance/swing locomotion baked to native Blender actions. One optional timer drives live updates."""
import json
import hashlib
import math
import uuid
import bpy
from mathutils import Vector, Matrix, Euler

MOTION_KEYS=("gait","start_frame","cycle_frames","cycles","stride","lift","stance","foot_planting",
    "exaggeration","body_height","bounce","bounce_frequency","sway","body_roll","body_pitch","body_twist",
    "motion_phase","tail_swing","tail_lift","tail_frequency","tail_stiffness","tail_phase","spine_bend",
    "spine_twist","spine_flex","head_bob","arm_swing","wing_flap","secondary","foot_roll","travel","motion_scope",
    "wing_style","wing_frequency","wing_fold","jaw_open","jaw_chance","jaw_rate","eye_bounce","body_wave",
    "fly_height","motion_type","jump_height","jump_distance","jump_crouch","strike_side","strike_height","body_lean")

def foot_offset(phase, stance, stride, lift):
    """Constant-speed planted stance, smooth lifted return. Forward is -Y."""
    phase=phase % 1.0
    if phase < stance:
        return (-stride*.5+stride*phase/stance,0.0)
    t=(phase-stance)/(1-stance)
    ease=t*t*(3-2*t)
    return (stride*.5-stride*ease,lift*math.sin(math.pi*t)**2)

def phase_for(limb, count, gait):
    i=limb["index"]
    side=0 if limb["side"]==1 else 1
    if gait=="PACE":
        return side*.5
    if gait=="BOUND":
        return (i % 2)*.5
    if gait=="TROT":
        return ((i+side) % 2)*.5
    if count==1:
        return side*.5
    return (side*.5+i*.75/max(1,count-1)) % 1

def limb_setting(arm, control, key, default):
    bone=arm.pose.bones.get(control)
    try:
        return float(bone.get(key, default)) if bone else default
    except (TypeError,ValueError):
        return default

def footprint_objects(arm):
    collection=arm.users_collection[0] if arm and arm.users_collection else None
    if not collection:
        return []
    return [obj for obj in collection.all_objects if obj.get("cs_footprint") and obj.get("cs_id")==arm.get("cs_id")]

def curves(action):
    """Blender 4.2 legacy and 4.4+/5.x layered action APIs."""
    if hasattr(action,"fcurves"):
        yield from action.fcurves
        return
    for layer in action.layers:
        for strip in layer.strips:
            if hasattr(strip,"channelbags"):
                for bag in strip.channelbags:
                    yield from bag.fcurves

def set_delta(arm,name,delta):
    bone=arm.pose.bones[name]
    # Control bones share a root parent. Rotation maps desired armature-space
    # motion into each control's local basis, including hand-edited rigs.
    bone.location=bone.bone.matrix_local.to_3x3().inverted() @ Vector(delta)
    return bone

def remove_curve(action,curve):
    if hasattr(action,"fcurves"):
        action.fcurves.remove(curve)
        return
    for layer in action.layers:
        for strip in layer.strips:
            for bag in getattr(strip,"channelbags",[]):
                if any(fc==curve for fc in bag.fcurves):
                    bag.fcurves.remove(curve)
                    return

def keep_channel(path,scope):
    if scope=="ALL":
        return True
    names={"BODY":("CTRL-body","spine.","torso."),"TAIL":("tail.",),
           "UPPER":("head","neck","arm.","forearm.","wing.","wingmid.","wingtip.","wingfinger.","wingrib.","antenna.","ponytail.","fin.","eye.","jaw"),"FEET":("CTRL-root","CTRL-leg.","POLE-leg.","CTRL-custom.")}
    return any('pose.bones["'+name in path for name in names[scope])

def curve_samples(context,obj):
    if not obj or obj.type!="CURVE":
        return []
    deps=context.evaluated_depsgraph_get()
    evaluated=obj.evaluated_get(deps)
    mesh=evaluated.to_mesh()
    try:
        # Mesh edges follow the evaluated spline order, including Bezier
        # interpolation. Reject branching/beveled geometry as a walk path.
        neighbors={}
        for edge in mesh.edges:
            a,b=edge.vertices
            neighbors.setdefault(a,[]).append(b)
            neighbors.setdefault(b,[]).append(a)
        if not neighbors or any(len(v)>2 for v in neighbors.values()):
            raise ValueError("Use one un-beveled, unbranched curve as a walk path")
        ends=[i for i,n in neighbors.items() if len(n)==1]
        if len(ends)!=2:
            raise ValueError("Use one open curve with two endpoints as the walk path")
        start=ends[0] if ends else min(neighbors)
        order=[start]
        previous=None
        current=start
        while True:
            choices=[i for i in neighbors[current] if i!=previous and i!=start]
            if not choices:
                break
            previous,current=current,choices[0]
            order.append(current)
            if len(order)>len(neighbors):
                raise ValueError("Unable to order the path curve")
        if len(order)!=len(neighbors):
            raise ValueError("Use a single spline for the walk path")
        return [obj.matrix_world @ mesh.vertices[i].co for i in order]
    finally:
        evaluated.to_mesh_clear()

def path_point(samples,distance):
    if distance<0:
        tangent=(samples[1]-samples[0]).normalized()
        return samples[0]+tangent*distance,tangent
    for a,b in zip(samples,samples[1:]):
        length=(b-a).length
        if distance<=length:
            return a.lerp(b,distance/max(length,1e-8)),(b-a).normalized()
        distance-=length
    tangent=(samples[-1]-samples[-2]).normalized()
    return samples[-1]+tangent*distance,tangent

def motion_plan(context,arm,p):
    limbs=json.loads(arm["cs_limbs"])
    # Swimmers have no legs: body length stands in for leg reach.
    reach=sum(l["reach"] for l in limbs)/len(limbs) if limbs else float(arm.get("cs_size",1.8))*.5
    if reach<=0:
        raise ValueError("The rig has zero-length legs")
    inverse=arm.matrix_world.inverted()
    path=[inverse @ point for point in curve_samples(context,p.path_object)] if p.travel and p.path_object else []
    path=[point for i,point in enumerate(path) if i==0 or (point-path[i-1]).length>1e-6]
    if p.travel and p.path_object and len(path)<2:
        raise ValueError("The path needs at least two distinct points")
    return dict(limbs=limbs,pairs=max((l["index"] for l in limbs),default=0)+1,reach=reach,
                stride=p.stride*reach,speed=p.stride*reach/p.stance,path=path)

def step_track(arm,plan,p,edited):
    """Body path implied by edited footprints: each marker says where the
    root must have been when that foot landed. Moving or turning a run of
    markers therefore steers, climbs or drops the whole walk."""
    inverse=arm.matrix_world.inverted()
    samples=[]
    for limb in plan["limbs"]:
        offset=limb_phase(arm,limb,plan,p)
        rest=Vector(limb["ankle"])+Vector((0,-plan["stride"]*.5,0))
        for (control,cycle),marker in edited.items():
            if control!=limb["control"]:
                continue
            matrix=inverse @ marker.matrix_world
            forward=matrix.to_3x3() @ Vector((0,-1,0))
            yaw=math.atan2(forward.x,-forward.y)
            samples.append((cycle-offset,matrix.translation-Matrix.Rotation(yaw,3,"Z") @ rest,yaw))
    samples.sort(key=lambda item:item[0])
    # Unwrap headings so a full loop keeps turning instead of snapping back.
    for i in range(1,len(samples)):
        t,point,yaw=samples[i]
        previous=samples[i-1][2]
        while yaw-previous>math.pi: yaw-=math.tau
        while yaw-previous<-math.pi: yaw+=math.tau
        samples[i]=(t,point,yaw)
    times=[item[0] for item in samples]
    def at(t):
        import bisect
        i=bisect.bisect_right(times,t)
        if i<=0: return samples[0][1],samples[0][2]
        if i>=len(samples): return samples[-1][1],samples[-1][2]
        (t0,p0,y0),(t1,p1,y1)=samples[i-1],samples[i]
        f=(t-t0)/max(t1-t0,1e-9)
        return p0.lerp(p1,f),y0+(y1-y0)*f
    def smooth(t,window=.3):
        # Averaging three taps leaves a straight walk untouched and rounds
        # off the step a single moved marker would otherwise put in the body.
        points=[at(t-window),at(t),at(t+window)]
        return sum((item[0] for item in points),Vector())/3,sum(item[1] for item in points)/3
    return smooth if samples else None

def root_frame(t,plan,p):
    if plan["path"]:
        point,tangent=path_point(plan["path"],t*plan["speed"])
        heading=math.atan2(tangent.x,-tangent.y)
        return point,Matrix.Rotation(heading,3,"Z")
    return Vector((0,-t*plan["speed"] if p.travel else 0,0)),Matrix.Identity(3)

def limb_phase(arm,limb,plan,p):
    return phase_for(limb,plan["pairs"],p.gait)+limb_setting(arm,limb["control"],"cs_phase",0.0)

def contact_frame(arm,limb,cycle,plan,p,edited=None):
    """Touchdown position and heading in armature coordinates."""
    if edited:
        marker=edited.get((limb["control"],cycle))
        if marker:
            matrix=arm.matrix_world.inverted() @ marker.matrix_world
            return matrix.translation,matrix.to_quaternion().to_matrix()
    start=cycle-limb_phase(arm,limb,plan,p)
    point,rotation=root_frame(start,plan,p)
    return point+rotation @ (Vector(limb["ankle"])+Vector((0,-plan["stride"]*.5,0))),rotation

def footprint_signature(arm,plan,p):
    payload={"rig":arm["cs_id"],"matrix":[list(row) for row in arm.matrix_world],
        "gait":p.gait,"cycles":p.cycles,"stance":p.stance,"stride":p.stride,
        "travel":p.travel,"path":[list(v) for v in plan["path"]],
        "limbs":[[l["control"],l["ankle"],l["reach"],limb_phase(arm,l,plan,p)] for l in plan["limbs"]]}
    return hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()

def create_footprints(context,arm,p):
    if not p.travel:
        raise ValueError("Enable Travel forward before creating footprints")
    plan=motion_plan(context,arm,p)
    for obj in footprint_objects(arm):
        bpy.data.objects.remove(obj,do_unlink=True)
    owner=arm.users_collection[0]
    collection=next((c for c in owner.children if c.get("cs_footprints")),None)
    if not collection:
        collection=bpy.data.collections.new("CK · Footprints")
        collection["cs_footprints"]=True
        owner.children.link(collection)
    created=[]
    for limb in plan["limbs"]:
        offset=limb_phase(arm,limb,plan,p)
        for cycle in range(math.floor(offset),math.floor(p.cycles+offset)+2):
            point,rotation=contact_frame(arm,limb,cycle,plan,p)
            obj=bpy.data.objects.new(f"Step · {limb['control'][5:]} · {cycle}",None)
            collection.objects.link(obj)
            obj.empty_display_type="CUBE"
            obj.empty_display_size=1
            obj.matrix_world=arm.matrix_world @ Matrix.Translation(point) @ rotation.to_4x4()
            obj.scale=(arm.get("cs_size",1.8)*.025,arm.get("cs_size",1.8)*.055,.008)
            obj.color=(.2,.85,.65,1) if limb["side"]==1 else (1,.45,.12,1)
            obj.show_in_front=True
            obj.hide_render=True
            obj["cs_footprint"]=True
            obj["cs_owned"]=True
            obj["cs_id"]=arm["cs_id"]
            obj["cs_limb"]=limb["control"]
            obj["cs_cycle"]=cycle
            obj["cs_contact_frame"]=p.start_frame+(cycle-offset)*p.cycle_frames
            obj["cs_original_matrix"]=json.dumps([list(row) for row in obj.matrix_world])
            created.append(obj)
    arm["cs_footprint_signature"]=footprint_signature(arm,plan,p)
    return created

def generate(context,arm,p,live=False):
    """live=True rewrites the active generated action in place and leaves the playhead alone."""
    if arm.data.pose_position=="REST":
        raise ValueError("Finish Fit mode before generating motion")
    from .rig import ensure_motion_controls
    ensure_motion_controls(arm)
    plan=motion_plan(context,arm,p)
    limbs=plan["limbs"]
    for name in ("CTRL-root","CTRL-body"):
        if name not in arm.pose.bones:
            raise ValueError("The rig is missing "+name)
    reach=plan["reach"]
    mode=p.motion_type
    if not limbs and mode!="IDLE":
        mode="SWIM"
    walking=mode=="WALK"
    edited={(obj.get("cs_limb"),obj.get("cs_cycle")):obj for obj in footprint_objects(arm)} if p.use_footprints and walking else {}
    if p.use_footprints and walking and not edited:
        raise ValueError("Create footprints first, or disable Use edited footprints")
    if edited and arm.get("cs_footprint_signature")!=footprint_signature(arm,plan,p):
        raise ValueError("Gait, stride, phase or path changed. Recreate footprints or disable Use edited footprints")
    if edited and not p.travel:
        raise ValueError("Edited footprints require Travel forward")
    if edited and not p.foot_planting:
        raise ValueError("Enable Plant feet when using edited footprints")
    arm.animation_data_create()
    previous=arm.animation_data.action
    scope=p.motion_scope
    if live and previous and previous.get("cs_motion"):
        action=previous
        # A layer keeps the channels it was generated with, whatever the menu says now.
        try:
            scope=json.loads(action.get("cs_parameters","{}")).get("motion_scope",scope)
        except ValueError:
            pass
    else:
        live=False
        if previous:
            previous.use_fake_user=True
        # NLA motion should not add on top of the newly generated action. Tracks
        # stay editable and can be unmuted deliberately in the NLA editor.
        for track in arm.animation_data.nla_tracks:
            track.mute=True
        label=p.gait.title() if walking else mode.title()
        action=bpy.data.actions.new(arm.name+" · "+label)
        action["cs_motion"]=True
        action.use_fake_user=True
        arm.animation_data.action=action
    if not any(keep_channel(b.path_from_id("location"),scope) for b in arm.pose.bones):
        raise ValueError("This rig has no bones for the selected motion channels")
    n=p.cycle_frames
    total=n*p.cycles
    frames=[p.start_frame+k for k in range(total+1)]
    # Values are collected in plain lists and written to the F-Curves in one
    # pass at the end. Keying frame by frame is far too slow for live updates.
    series={}
    paths={}
    def record(bone,prop,group,values):
        key=(bone.name,prop)
        path=paths.get(key)
        if path is None:
            path=paths[key]=bone.path_from_id(prop)
        if not keep_channel(path,scope):
            return
        for index,value in enumerate(values):
            entry=series.get((path,index))
            if entry is None:
                entry=series[(path,index)]=(group,[])
            entry[1].append(value)
    def local(bone,matrix):
        basis=bases[bone.name]
        return basis[1] @ matrix @ basis[0]
    bases={}
    axes={}
    side_axis=Vector((1,0,0))
    for bone in arm.pose.bones:
        basis=bone.bone.matrix_local.to_3x3()
        bases[bone.name]=(basis,basis.inverted())
        direction=(bone.bone.tail_local-bone.bone.head_local).normalized()
        bend=direction.cross(side_axis)
        bend=bend.normalized() if bend.length>1e-4 else Vector((0,0,1))
        axes[bone.name]=(direction,bend)
    def numbered(prefix):
        found=[b for b in arm.pose.bones if b.name.startswith(prefix) and b.name.split(".")[1].isdigit()]
        return sorted(found,key=lambda b:int(b.name.split(".")[1]))
    tails=[b for b in arm.pose.bones if b.name.startswith("tail.")]
    # The trunk bends as one chain: body spine first, then any upright torso.
    trunk=numbered("spine.")+numbered("torso.")
    heads=[b for b in arm.pose.bones if b.name in {"neck","head"} or b.name.startswith("neck.")]
    neck_count=max(1,sum(1 for b in heads if b.name!="head"))
    arms=[b for b in arm.pose.bones if b.name.startswith(("arm.","forearm."))]
    wings=[b for b in arm.pose.bones if b.name.startswith(("wing.","wingmid.","wingtip."))]
    wing_links=max(2,sum(1 for b in wings if b.name.endswith("L")))
    def wing_index(bone):
        if bone.name.startswith("wing."): return 0
        if bone.name.startswith("wingtip."): return wing_links-1
        return int(bone.name.split(".")[1])
    # Fingers close onto the outer wing as it folds: the turn that lays each one along it.
    wing_fingers=[]
    for bone in arm.pose.bones:
        if bone.name.startswith(("wingfinger.","wingrib.")) and bone.parent:
            mine=(bone.bone.tail_local-bone.bone.head_local).normalized()
            outer_dir=(bone.parent.bone.tail_local-bone.parent.bone.head_local).normalized()
            turn_axis,turn_angle=mine.rotation_difference(outer_dir).to_axis_angle()
            wing_fingers.append((bone,Vector(turn_axis),turn_angle))
    followers=[b for b in arm.pose.bones if b.name.startswith(("antenna.","ponytail.","fin.","eye."))]
    forward_axis=Vector((0,1,0))
    chain_counts={}
    for bone in followers:
        key=bone.name.split(".")[0]+bone.name[-2:]
        chain_counts[key]=chain_counts.get(key,0)+1
    jaw=arm.pose.bones.get("jaw")
    controls={limb["control"]:arm.pose.bones[limb["control"]] for limb in limbs}
    poles={limb["control"]:arm.pose.bones[limb["pole"]] for limb in limbs}
    leg_rest={limb["control"]:(arm.data.bones[limb["upper"]].head_local.copy(),Vector(limb["ankle"]),
                               arm.data.bones[limb["pole"]].head_local.copy()) for limb in limbs}
    previous_euler={}
    def euler(bone,matrix):
        value=matrix.to_euler("XYZ",previous_euler[bone.name]) if bone.name in previous_euler else matrix.to_euler("XYZ")
        previous_euler[bone.name]=value
        return value
    body=arm.pose.bones["CTRL-body"]
    root=arm.pose.bones["CTRL-root"]
    offsets={limb["control"]:limb_phase(arm,limb,plan,p) for limb in limbs}
    lifts={limb["control"]:p.lift*limb["reach"]*limb_setting(arm,limb["control"],"cs_lift",1.0) for limb in limbs}
    ex=max(0,p.exaggeration)
    links=max(1,len(trunk))
    steps=step_track(arm,plan,p,edited) if edited else None
    arching=arm.get("cs_species")=="WORM" and mode=="SWIM"
    front_length=sum(b.bone.length for b in trunk)
    tail_length=sum(b.bone.length for b in tails if b.name.split(".")[1].isdigit())
    travelling=p.travel and mode in {"WALK","SWIM","JUMP","FLY"}
    def ease(x):
        x=max(0.0,min(1.0,x))
        return x*x*(3-2*x)
    identity=Matrix.Identity(3)
    for k in range(total+1):
        t=k/n
        u=t % 1.0
        cycle_index=math.floor(t)
        phase_t=math.tau*(t+p.motion_phase)
        # Per-frame extras that the special cycles add on top of the shared body motion.
        feet={}
        lift_body=0.0       # extra body height
        lean=p.body_lean    # extra forward pitch of the body
        shift=0.0           # extra sideways body shift
        fold=0.0            # extra forward flex of the whole trunk
        turn=0.0            # extra twist of the whole trunk
        arm_pose={}         # bone name -> angle about the side axis, replacing the swing
        gain=1.0            # scales the walk's rhythmic body motion
        if mode in {"WALK","SWIM","FLY"}:
            if steps:
                point,yaw=steps(t)
                root_point,root_rotation=point,Matrix.Rotation(yaw,3,"Z")
            else:
                root_point,root_rotation=root_frame(t,plan,p)
        else:
            root_point,root_rotation=Vector((0,0,0)),identity
        if mode=="WALK":
            for limb in limbs:
                name=limb["control"]
                offset=offsets[name]
                phase=(t+offset) % 1
                # One shared stride keeps stance velocity equal and opposite to
                # root velocity even when front and rear legs have different reach.
                dy,dz=foot_offset(phase,p.stance,p.stride*reach,lifts[name])
                foot_rotation=identity
                delta=Vector((0,dy,dz))
                # Toe-down as the foot peels off the ground, level again before landing.
                roll=None
                if phase>=p.stance and p.foot_roll:
                    swing=(phase-p.stance)/(1-p.stance)
                    roll=Matrix.Rotation(p.foot_roll*ex*math.sin(math.pi*swing)*(1-swing)*1.8,3,"X")
                    foot_rotation=roll
                if p.travel and p.foot_planting:
                    cycle=math.floor(t+offset)
                    a,ra=contact_frame(arm,limb,cycle,plan,p,edited)
                    if phase < p.stance:
                        target=a
                        foot_rotation=ra
                    else:
                        b,rb=contact_frame(arm,limb,cycle+1,plan,p,edited)
                        w=ease((phase-p.stance)/(1-p.stance))
                        target=a.lerp(b,w)+Vector((0,0,dz))
                        foot_rotation=ra.to_quaternion().slerp(rb.to_quaternion(),w).to_matrix()
                    delta=root_rotation.inverted() @ (target-root_point)-Vector(limb["ankle"])
                    foot_rotation=root_rotation.inverted() @ foot_rotation
                    if roll:
                        foot_rotation=foot_rotation @ roll
                feet[name]=(delta,foot_rotation)
        elif mode=="IDLE":
            # Standing and breathing: feet stay put, everything else settles.
            gain=.3
        elif mode=="FLY":
            # Airborne: the body rides up on each downstroke and the legs trail, tucked.
            gain=.3
            soaring=p.wing_style=="GLIDE"
            beat=phase_t*p.wing_frequency
            lift_body=p.fly_height*reach-math.cos(beat)*p.wing_flap*ex*reach*(.02 if soaring else .14)
            lean+=.12
            for limb in limbs:
                r=limb["reach"]
                feet[limb["control"]]=(Vector((0,.30*r,lift_body+.42*r)),Matrix.Rotation(.9,3,"X"))
        elif mode=="JUMP":
            # Crouch, push off, fly, land, recover.
            crouch=p.jump_crouch*reach
            height=p.jump_height*reach
            if u<.22: down,air=ease(u/.22),0.0
            elif u<.32: down,air=1-ease((u-.22)/.10),0.0
            elif u<.72: down,air=0.0,(u-.32)/.40
            elif u<.84: down,air=.8*ease((u-.72)/.12),1.0
            else: down,air=.8*(1-ease((u-.84)/.16)),1.0
            flight=height*4*air*(1-air) if 0<air<1 else 0.0
            lift_body=flight-crouch*down
            fold=down*.5
            lean+=down*.15
            gain=.25
            tuck=math.sin(math.pi*air) if 0<air<1 else 0.0
            for limb in limbs:
                feet[limb["control"]]=(Vector((0,0,flight+tuck*limb["reach"]*.18)),
                                       Matrix.Rotation(p.foot_roll*ex*tuck*1.2,3,"X"))
            if travelling:
                root_point=Vector((0,-p.jump_distance*reach*(cycle_index+ease(air)),0))
            reach_up=down*.7-(1.5*math.sin(math.pi*min(1,air*1.3)) if 0<air<1 else 0.0)
            for bone in arms:
                arm_pose[bone.name]=reach_up*p.arm_swing*ex*2.2 if bone.name.startswith("arm.") else -down*.5
        elif mode in {"PUNCH","KICK"}:
            # Wind up, strike, hold, recover.
            if u<.30: wind,strike=ease(u/.30),0.0
            elif u<.45: wind,strike=1-ease((u-.30)/.15),ease((u-.30)/.15)
            elif u<.55: wind,strike=0.0,1.0
            else: wind,strike=0.0,1-ease((u-.55)/.45)
            side="L" if p.strike_side=="L" or (p.strike_side=="ALT" and cycle_index%2==0) else "R"
            sign=1 if side=="L" else -1
            busy=max(wind,strike)
            gain=.2
            if mode=="PUNCH":
                turn=sign*(.35*wind-.55*strike)*ex
                lean+=.10*strike*ex
                for bone in arms:
                    upper=bone.name.startswith("arm.")
                    if bone.name.endswith(side):
                        arm_pose[bone.name]=(.5*wind-(math.pi*.5)*p.strike_height*strike) if upper else -1.9*wind*(1-strike)-.25*(busy-strike)
                    else:
                        # The other arm comes up as a guard.
                        arm_pose[bone.name]=-.35*busy if upper else -1.7*busy
            else:
                lean-=.28*strike*ex
                shift=-sign*.10*reach*busy
                for limb in limbs:
                    kicking=limb["index"]==0 and limb["side"]==sign
                    if kicking:
                        r=limb["reach"]
                        delta=Vector((0,.22*r,.14*r))*wind+Vector((0,-.80*r,p.strike_height*r*.75))*strike*min(1.5,ex)
                        feet[limb["control"]]=(delta,Matrix.Rotation(.5*wind-.9*strike,3,"X"))
                for bone in arms:
                    if bone.name.startswith("arm."):
                        arm_pose[bone.name]=(.5 if bone.name.endswith(side) else -.5)*busy
        arch=0.0
        if arching:
            # An inchworm gathers itself into a hump and stretches out again:
            # the middle rises and both ends tip down just enough to stay on the ground.
            arch=(1-math.cos(phase_t))*.5*p.spine_flex*ex
            front_total=arch
            tail_total=arch*front_length/max(tail_length,1e-6)
            drop=0.0
            angle=0.0
            for bone in trunk:
                angle+=front_total/max(1,len(trunk))
                drop+=bone.bone.length*math.sin(angle)
            lift_body+=drop
        for limb in limbs:
            name=limb["control"]
            delta,foot_rotation=feet.get(name,(Vector((0,0,0)),identity))
            control=controls[name]
            # Control bones share a root parent. Rotation maps desired armature-space
            # motion into each control's local basis, including hand-edited rigs.
            record(control,"location","Feet · "+name,bases[name][1] @ delta)
            record(control,"rotation_euler","Feet · "+name,euler(control,local(control,foot_rotation)))
            # The knee target turns with the leg. Left where it stood, a foot
            # swung past it would flip the knee from one frame to the next.
            pole_move=Vector((0,0,0))
            if mode in {"KICK","FLY","JUMP"} and delta.length>1e-6:
                hip_rest,ankle_rest,pole_rest=leg_rest[name]
                hip=hip_rest+Vector((shift,0,p.body_height*reach+lift_body))
                turned=(ankle_rest-hip_rest).rotation_difference(ankle_rest+delta-hip)
                pole_move=hip+turned @ (pole_rest-hip_rest)-pole_rest
            record(poles[name],"location","Poles",bases[poles[name].name][1] @ pole_move)
        record(body,"location","Body",bases[body.name][1] @ Vector((math.sin(phase_t)*p.sway*reach*ex+shift,0,
            p.body_height*reach+p.bounce*reach*math.cos(phase_t*(1 if mode=="IDLE" else p.bounce_frequency))*ex*gain+lift_body)))
        # The hips turn toward the leading foot; the trunk above counter-rotates.
        rotation=Euler((lean+math.sin(phase_t+math.pi*.5)*p.body_pitch*ex*gain,
            math.sin(phase_t)*p.body_roll*ex*gain,-math.cos(phase_t)*p.body_twist*ex*gain),"XYZ").to_matrix()
        record(body,"rotation_euler","Body",local(body,rotation).to_euler())
        record(root,"location","Root",bases[root.name][1] @ Vector(root_point))
        record(root,"rotation_euler","Root",euler(root,local(root,root_rotation)))
        for bone in tails:
            idx=int(bone.name.split(".")[1])
            count=max(1,len(tails))
            if arching:
                record(bone,"rotation_euler","Tail",local(bone,Matrix.Rotation(-tail_total/count,3,side_axis)).to_euler("XYZ"))
                continue
            lag=idx*.40*(1-p.tail_stiffness*.8)
            tail_phase=phase_t*p.tail_frequency+math.tau*p.tail_phase-lag
            record(bone,"rotation_euler","Tail",(math.sin(tail_phase+math.pi*.35)*p.tail_lift*ex*(1-idx/count),0.0,
                math.sin(tail_phase)*p.tail_swing*ex*(1-idx/count*.72)))
        for index,bone in enumerate(trunk):
            # Sliders give the whole trunk's angle, shared out along its links,
            # so a long spine does not bend more than a short one.
            w=(index+1)/links
            direction,bend=axes[bone.name]
            share=1.5*(.35+.65*w)/links
            travel_phase=w*(.45+math.tau*p.body_wave)
            sideways=math.sin(phase_t+travel_phase)*p.spine_bend*ex*share*gain
            twist=math.cos(phase_t+w*.25)*(p.spine_twist+p.body_twist)*ex/links*gain+turn/links
            breathing=1 if mode=="IDLE" else gain
            flex=math.cos(phase_t*(1 if mode=="IDLE" else p.bounce_frequency)+w*.6+travel_phase)*p.spine_flex*ex*share*breathing+fold*share
            if arching:
                flex=arch/links
            matrix=Matrix.Rotation(flex,3,side_axis) @ Matrix.Rotation(sideways,3,bend) @ Matrix.Rotation(twist,3,Vector((0,0,1)) if turn else direction)
            record(bone,"rotation_euler","Spine",local(bone,matrix).to_euler("XYZ"))
        for bone in heads:
            # A long neck shares one nod between its links instead of curling up.
            angle=(math.cos(phase_t*p.bounce_frequency+.9)*p.head_bob*ex*gain-fold*.3)/(1 if bone.name=="head" else neck_count)
            if arching and bone.name=="head":
                angle-=arch   # keep the head level while the body humps up behind it
            record(bone,"rotation_euler","Head",local(bone,Matrix.Rotation(angle,3,side_axis)).to_euler("XYZ"))
        for bone in arms:
            # Swing about the armature's side axis so any rest pose works:
            # each arm goes back as the foot on its own side goes forward.
            side_phase=phase_t if bone.name.endswith("L") else phase_t+math.pi
            if bone.name.startswith("arm."):
                angle=math.cos(side_phase)*p.arm_swing*ex*gain
            else:
                angle=-(1-math.cos(side_phase))*.3*p.arm_swing*ex*gain
            if bone.name in arm_pose:
                angle=angle*.3+arm_pose[bone.name]
            record(bone,"rotation_euler","Arms",local(bone,Matrix.Rotation(angle,3,side_axis)).to_euler("XYZ"))
        for bone in wings:
            sign=1 if bone.name.endswith("L") else -1
            index=wing_index(bone)
            # 0 at the shoulder, 1 at the tip: each link out trails a little more,
            # which is what makes a many-jointed wing ripple like a membrane.
            out=index/(wing_links-1)
            outer=index>0
            style=p.wing_style
            if mode=="FLY" and style=="FOLDED":
                style="FLAP"   # nothing flies with its wings tucked in
            beat_phase=phase_t*p.wing_frequency
            fold=1.0 if style=="FOLDED" else 0.0 if mode=="FLY" else p.wing_fold
            amplitude=p.wing_flap*ex*(1-fold*.85)
            share=1.0 if index==0 else .7/(wing_links-1)*1.0 if wing_links>2 else .7
            sweep=0.0       # about the vertical axis: forward and back
            raise_=0.0      # held dihedral
            if style=="GLIDE":
                beat=math.sin(beat_phase*4-.9*out)*amplitude*.08
                raise_=.18 if not outer else -.06/(wing_links-1)
            elif style=="HOVER":
                beat_phase=phase_t*max(p.wing_frequency,3.0)
                beat=math.sin(beat_phase-.6*out)*amplitude*share
                sweep=math.cos(beat_phase-.6*out)*amplitude*.6*share
            elif style=="FLUTTER":
                beat=math.sin(phase_t*max(p.wing_frequency,1.0)*6-.5*out)*amplitude*.4*share
            elif style=="FOLDED":
                beat=math.sin(phase_t*p.bounce_frequency-.9*out)*p.wing_flap*ex*.05
            else:
                # The downstroke is quicker than the upstroke, and the outer wing trails.
                wave=beat_phase-(.9 if wing_links==2 else 1.5)*out
                beat=math.sin(wave+.35*math.sin(wave))*amplitude*(share if wing_links==2 or index==0 else share*1.6)
            # Folding: the inner wing swings back and down, and each link beyond
            # doubles back on the one before it, like a closing fan.
            if index==0: tuck=fold*1.25
            else: tuck=fold*(-3.2 if index%2 else 3.0)
            droop=fold*(0 if outer else .45)
            matrix=Matrix.Rotation(sign*(tuck+sweep),3,"Z") @ Matrix.Rotation(-sign*(beat+raise_)+sign*droop,3,forward_axis)
            record(bone,"rotation_euler","Wings",local(bone,matrix).to_euler("XYZ"))
        fold_now=0.0 if mode=="FLY" else 1.0 if p.wing_style=="FOLDED" else p.wing_fold
        for bone,turn_axis,turn_angle in wing_fingers:
            record(bone,"rotation_euler","Wings",local(bone,Matrix.Rotation(turn_angle*fold_now*.92,3,turn_axis)).to_euler("XYZ"))
        for bone in followers:
            # Follow-through: each link answers the body a little later than the
            # last. The total sway stays the same however many links share it.
            idx=int(bone.name.split(".")[1])
            count=chain_counts[bone.name.split(".")[0]+bone.name[-2:]]
            direction,bend=axes[bone.name]
            lag=idx*max(.22,1.65/count)
            amount=p.secondary*ex*(.6+.8*idx/count)*2/count
            if bone.name.startswith("eye."):
                # Eyes have their own control: stiff at 0, and both the bounce
                # and the delay behind the head grow as it is raised.
                amount=p.eye_bounce*ex
                lag=.5+2.2*min(1.0,p.eye_bounce/.8)
            sideways=math.sin(phase_t-lag)*amount
            nod=math.cos(phase_t*p.bounce_frequency-lag)*amount*.7
            matrix=Matrix.Rotation(nod,3,side_axis) @ Matrix.Rotation(sideways,3,bend)
            record(bone,"rotation_euler","Follow-through",local(bone,matrix).to_euler("XYZ"))
        if jaw is not None:
            # The mouth opens on some cycles and stays shut on others. Which
            # ones is fixed by the cycle number, so the result is repeatable.
            chance=math.sin((cycle_index % max(1,p.cycles))*12.9898+4.1)*43758.5453
            active=(chance-math.floor(chance))<p.jaw_chance
            opening=math.sin(math.pi*u*p.jaw_rate)**2*p.jaw_open*ex if active else 0.0
            record(jaw,"rotation_euler","Head",local(jaw,Matrix.Rotation(opening,3,side_axis)).to_euler("XYZ"))
    from .retarget import ensure_fcurve
    count=len(frames)
    flat=[0.0]*(2*count)
    flat[0::2]=[float(f) for f in frames]
    linear=[1]*count   # BEZT_IPO_LIN
    for (path,index),(group,values) in series.items():
        fc=ensure_fcurve(action,arm,path,index,group)
        points=fc.keyframe_points
        if len(points)!=count:
            points.clear()
            points.add(count)
        flat[1::2]=values
        points.foreach_set("co",flat)
        try:
            points.foreach_set("interpolation",linear)
        except (TypeError,RuntimeError):
            for point in points:
                point.interpolation="LINEAR"
        cyclic=[m for m in fc.modifiers if m.type=="CYCLES"]
        if travelling:
            for modifier in cyclic:
                fc.modifiers.remove(modifier)
        elif not cyclic:
            fc.modifiers.new("CYCLES")
        fc.update()
    for fc in list(curves(action)):
        if (fc.data_path,fc.array_index) not in series:
            remove_curve(action,fc)
    arm.update_tag()
    context.scene.frame_start=p.start_frame
    context.scene.frame_end=p.start_frame+total-1
    if not live:
        for bone in arm.pose.bones:
            bone.location=(0,0,0)
            bone.rotation_euler=(0,0,0)
            bone.scale=(1,1,1)
        context.scene.frame_set(p.start_frame)
    action["cs_gait"]=p.gait
    action["cs_parameters"]=json.dumps({key:scope if key=="motion_scope" else getattr(p,key) for key in MOTION_KEYS})
    action["cs_rig_id"]=arm["cs_id"]
    action["cs_version"]="1.2.0"
    arm["cs_last_action"]=action.name
    return action

def layer_entry(arm,strip):
    return next((item for item in arm.cs_layers if item.strip_name==strip.name),None)

def add_layer_controls(arm,strip,label):
    entry=arm.cs_layers.add()
    entry.strip_name=strip.name
    entry.label=label
    return entry

def update_layer_controls(entry):
    arm=entry.id_data
    if not arm or not arm.animation_data:
        return
    for track in arm.animation_data.nla_tracks:
        strip=next((s for s in track.strips if s.name==entry.strip_name),None)
        if not strip: continue
        track.name=entry.label or "Layer"
        strip.use_animated_influence=True
        strip.blend_in=strip.blend_out=0
        fc=strip.fcurves.find("influence")
        if not fc:
            strip.influence=entry.weight
            strip.keyframe_insert("influence",frame=strip.frame_start)
            fc=strip.fcurves.find("influence")
        fc.keyframe_points.clear()
        start,end=strip.frame_start,strip.frame_end
        duration=max(0,end-start)
        fade_in=min(entry.fade_in,duration)
        fade_out=min(entry.fade_out,max(0,duration-fade_in))
        points={start:0.0 if fade_in else entry.weight,end:0.0 if fade_out else entry.weight}
        if fade_in: points[start+fade_in]=entry.weight
        if fade_out: points[end-fade_out]=entry.weight
        for frame,value in sorted(points.items()):
            key=fc.keyframe_points.insert(frame,value,options={"FAST"})
            key.interpolation="LINEAR"
        fc.update()
        strip.influence=entry.weight
        arm.update_tag()
        return

def push_clip(arm,p=None):
    if not arm.animation_data or not arm.animation_data.action:
        raise ValueError("Generate a walk or select an action first")
    ad=arm.animation_data
    ad.use_nla=True
    action=ad.action
    slot=ad.action_slot if hasattr(ad,"action_slot") else None
    track=ad.nla_tracks.new()
    track.name=(p.layer_name.strip() if p and p.layer_name.strip() else action.name)
    strip=track.strips.new("CS-"+uuid.uuid4().hex[:12],int(action.frame_range[0]),action)
    if slot and hasattr(strip,"action_slot"):
        strip.action_slot=slot
    strip.blend_type=p.layer_blend if p else "REPLACE"
    strip.extrapolation="NOTHING"
    ad.action=None
    for bone in arm.pose.bones:
        bone.location=(0,0,0)
        bone.rotation_euler=(0,0,0)
        bone.scale=(1,1,1)
    arm.update_tag()
    entry=add_layer_controls(arm,strip,track.name)
    if p:
        entry.weight=p.layer_weight
        entry.fade_in=p.layer_blend_in
        entry.fade_out=p.layer_blend_out
    update_layer_controls(entry)
    return strip

def layer_snapshot(arm):
    if not arm or not arm.animation_data:
        return []
    return [{"name":track.name,"mute":track.mute,
             "strips":[{"name":strip.name,"action":strip.action.name if strip.action else "",
                         "blend_type":strip.blend_type,"influence":strip.influence,
                         "frame_start":strip.frame_start,"frame_end":strip.frame_end}
                        for strip in track.strips]} for track in arm.animation_data.nla_tracks]


# Live update ---------------------------------------------------------------
# A timer compares the motion controls with the values the active action was
# generated from, and rewrites the action when they differ. Polling also covers
# per-limb custom properties, footprint markers and path curves, which have no
# update callbacks.
SYNCING=False
LIVE_INTERVAL=0.05
LIVE_SETTLE=0.2
_live={}

def live_signature(context,arm,p):
    values=[getattr(p,key) for key in MOTION_KEYS if key!="motion_scope"]+[p.use_footprints,p.path_object.name if p.path_object else ""]
    for limb in json.loads(arm.get("cs_limbs","[]")):
        values+=[limb_setting(arm,limb["control"],key,0.0) for key in ("cs_phase","cs_lift")]
    def rounded(matrix):
        return [round(v,5) for row in matrix for v in row]
    if p.use_footprints:
        for obj in footprint_objects(arm):
            values.append(rounded(obj.matrix_world))
    if p.travel and p.path_object:
        values.append(rounded(p.path_object.matrix_world))
        values.append([[round(v,5) for v in point] for point in curve_samples(context,p.path_object)])
    return json.dumps(values,default=str)

def live_tick():
    try:
        context=bpy.context
        if context.window is None and context.window_manager.windows:
            # Timers can run without a window; borrow one so scene, view layer
            # and screen resolve the same way they do in the interface.
            with context.temp_override(window=context.window_manager.windows[0]):
                live_step(bpy.context)
        else:
            live_step(context)
    except Exception as exc:
        # Never let a transient state (file load, undo) stop the timer.
        _live["error"]=str(exc)
    return LIVE_INTERVAL

def live_body(context,arm,p):
    """Keep the body sliders and the active creature in step. Returns the
    armature to carry on with, which is a new object after a rebuild."""
    import time
    from . import rig
    rig_id=arm.get("cs_id")
    if _live.get("rig")!=rig_id:
        # A different creature became active: show its values, change nothing.
        _live["rig"]=rig_id
        _live.pop("body_pending",None)
        rig.load_settings(arm,p)
        return arm
    if not p.live_build or arm.data.pose_position=="REST":
        return arm
    changed=rig.differs(arm,p)
    if not changed or "species" in changed:
        # A different preset in the menu means a new creature is being set up.
        _live.pop("body_pending",None)
        return arm
    reason=rig.locked(arm)
    if reason:
        if _live.get("locked_note")!=rig_id:
            _live["locked_note"]=rig_id
            p.status=f"Live body is off for this creature because it {reason}. Build a new one to reshape it."
        return arm
    signature=json.dumps([getattr(p,key) for key in rig.BUILD_KEYS])
    now=time.monotonic()
    if _live.get("body_pending")!=signature:
        _live.update(body_pending=signature,body_since=now)
        return arm
    if now-_live.get("body_since",now)<LIVE_SETTLE:
        return arm
    _live.pop("body_pending",None)
    posing=context.mode=="POSE"
    try:
        new=rig.rebuild(context,arm,p)
    except Exception as exc:
        p.status="Live body paused: "+str(exc)
        # Do not retry the same values on every tick.
        rig.load_settings(arm,p)
        return arm
    action=new.animation_data.action if new.animation_data else None
    if action and action.get("cs_motion"):
        try:
            generate(context,new,p,live=True)
        except Exception as exc:
            p.status="Body rebuilt; cycle not updated: "+str(exc)
        else:
            p.status=f"Rebuilt {new.name} · {len(new.data.bones)} bones · cycle updated"
        if _live.get("key"):
            _live["key"]=(new.name,action.name)
    else:
        p.status=f"Rebuilt {new.name} · {len(new.data.bones)} bones"
    if posing:
        try: bpy.ops.object.mode_set(mode="POSE")
        except RuntimeError: pass
    context.scene.frame_set(context.scene.frame_current)
    return new

def live_step(context):
    scene=context.scene
    p=getattr(scene,"cs_settings",None) if scene else None
    if not p or context.mode not in {"OBJECT","POSE"}:
        return
    from .rig import active
    arm=active(context)
    if not arm:
        _live.pop("rig",None)
        return
    arm=live_body(context,arm,p)
    if not p.live_update:
        return
    action=arm.animation_data.action if arm and arm.animation_data else None
    if not action or not action.get("cs_motion") or arm.data.pose_position=="REST":
        return
    try:
        signature=live_signature(context,arm,p)
    except ValueError:
        return
    key=(arm.name,action.name)
    if _live.get("key")!=key:
        # A newly generated or newly selected action already matches its controls.
        _live.update(key=key,signature=signature)
        return
    if _live.get("signature")==signature:
        return
    if p.live_on_release:
        # No release event reaches a timer, so wait until the controls hold still.
        import time
        now=time.monotonic()
        if _live.get("pending")!=signature:
            _live.update(pending=signature,since=now)
            return
        if now-_live.get("since",now)<LIVE_SETTLE:
            return
    _live["signature"]=signature
    try:
        generate(context,arm,p,live=True)
        p.status=f"Live · {p.gait.title() if p.motion_type=='WALK' else p.motion_type.title()} · {p.cycle_frames} frames per cycle"
    except Exception as exc:
        p.status="Live update paused: "+str(exc)
    screen=context.screen
    if not (screen and screen.is_animation_playing):
        scene.frame_set(scene.frame_current)
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type in {"VIEW_3D","DOPESHEET_EDITOR","GRAPH_EDITOR","NLA_EDITOR"}:
                area.tag_redraw()

def live_start():
    if not bpy.app.timers.is_registered(live_tick):
        bpy.app.timers.register(live_tick,first_interval=LIVE_INTERVAL,persistent=True)

def live_stop():
    if bpy.app.timers.is_registered(live_tick):
        bpy.app.timers.unregister(live_tick)
    _live.clear()
