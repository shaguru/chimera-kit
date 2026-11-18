"""UI-safe operators. Each destructive action is undoable and scoped to owned data."""
import json
import os
import bpy
from bpy.types import Operator
from bpy.props import EnumProperty, IntProperty
from . import motion, rig, retarget

_POSE_ITEMS=[]
_LIMB_ITEMS=[]

def layer_settings_changed(self,context):
    motion.update_layer_controls(self)

def limb_items(self, context):
    global _LIMB_ITEMS
    arm=active(context) if context else None
    _LIMB_ITEMS=[(limb["control"],limb["control"].removeprefix("CTRL-"),"Foot phase, lift and IK weight")
        for limb in json.loads(arm.get("cs_limbs","[]"))] if arm else []
    _LIMB_ITEMS=_LIMB_ITEMS or [("NONE","No limbs","Build a rig first")]
    return _LIMB_ITEMS

def settings(context):
    return context.scene.cs_settings

def active(context):
    return rig.active(context)

def pose_items(self, context):
    global _POSE_ITEMS
    arm=active(context)
    if not arm:
        return [("NONE","No rig","Build a rig first")]
    names=[]
    for key in sorted(arm.keys()):
        if key.startswith("cs_pose_"):
            names.append((key[8:],key[8:].replace("_"," ").title(),"Saved pose"))
    _POSE_ITEMS=names or [("NONE","No saved poses","Capture a pose first")]
    return _POSE_ITEMS

class CS_OT_build(Operator):
    bl_idname="chimera_kit.build"
    bl_label="Build new creature"
    bl_options={"REGISTER","UNDO"}
    def execute(self,context):
        p=settings(context)
        try:
            arm=rig.build(context,p)
        except Exception as exc:
            self.report({"ERROR"},"Build failed: "+str(exc))
            return {"CANCELLED"}
        p.active_rig=arm
        p.status=f"Built {p.species.title()} · {len(arm.data.bones)} bones · {len(json.loads(arm['cs_limbs']))} IK limbs"
        self.report({"INFO"},p.status)
        return {"FINISHED"}

class CS_OT_sync_settings(Operator):
    bl_idname="chimera_kit.sync_settings"
    bl_label="Load this creature's body values"
    bl_description="Set the body sliders to the active creature, so changing them reshapes it"
    bl_options={"REGISTER","UNDO"}
    def execute(self,context):
        arm=active(context)
        if not arm: return {"CANCELLED"}
        rig.load_settings(arm,settings(context))
        settings(context).status="Body sliders now show "+arm.name
        return {"FINISHED"}

class CS_OT_add_module(Operator):
    bl_idname="chimera_kit.add_module"
    bl_label="Append structure to rig"
    bl_options={"REGISTER","UNDO"}
    def execute(self,context):
        from . import modules
        arm=active(context)
        if not arm: return {"CANCELLED"}
        try:
            names=modules.add(context,arm,settings(context))
        except ValueError as exc:
            self.report({"ERROR"},str(exc))
            return {"CANCELLED"}
        settings(context).status=f"Added {len(names)} bones. Use Fit to shape the new structure; update motion afterwards."
        return {"FINISHED"}

class CS_OT_delete(Operator):
    bl_idname="chimera_kit.delete"
    bl_label="Delete owned rig"
    bl_options={"REGISTER","UNDO"}
    def execute(self,context):
        arm=active(context)
        if not arm:
            self.report({"WARNING"},"Select a Chimera Kit rig")
            return {"CANCELLED"}
        collection=arm.users_collection[0] if arm.users_collection else None
        if collection:
            rig.object_mode(context)
            for obj in list(collection.all_objects):
                if obj==arm or obj.get("cs_owned"):
                    bpy.data.objects.remove(obj,do_unlink=True)
                else:
                    # A custom artist mesh can be linked into this collection.
                    # Preserve it at the scene root when deleting the rig.
                    if context.scene.collection.objects.get(obj.name) is None:
                        context.scene.collection.objects.link(obj)
                    world=obj.matrix_world.copy()
                    obj.parent=None
                    obj.matrix_world=world
            bpy.data.collections.remove(collection)
        settings(context).active_rig=None
        settings(context).status="Owned rig deleted"
        return {"FINISHED"}

class CS_OT_validate(Operator):
    bl_idname="chimera_kit.validate"
    bl_label="Validate rig"
    def execute(self,context):
        issues=rig.validate(active(context))
        settings(context).status="Healthy rig: no missing bones, IK chains or controls" if not issues else " · ".join(issues[:4])
        self.report({"INFO" if not issues else "WARNING"},settings(context).status)
        return {"FINISHED"}

class CS_OT_fit_start(Operator):
    bl_idname="chimera_kit.fit_start"
    bl_label="Start fit mode"
    bl_options={"REGISTER","UNDO"}
    def execute(self,context):
        arm=active(context)
        if not arm:
            self.report({"WARNING"},"Build or select a rig first")
            return {"CANCELLED"}
        rig.fit(context,arm)
        settings(context).status="Fit mode: move edit bones to match your mesh, then Finish Fit"
        return {"FINISHED"}

class CS_OT_fit_finish(Operator):
    bl_idname="chimera_kit.fit_finish"
    bl_label="Finish fit mode"
    bl_options={"REGISTER","UNDO"}
    def execute(self,context):
        arm=active(context)
        if not arm:
            return {"CANCELLED"}
        try:
            rig.finish_fit(context,arm)
        except Exception as exc:
            self.report({"ERROR"},"Fit failed: "+str(exc))
            return {"CANCELLED"}
        settings(context).status="Fit committed; IK planes recalibrated"
        return {"FINISHED"}

class CS_OT_generate_motion(Operator):
    bl_idname="chimera_kit.generate_motion"
    bl_label="Generate gait"
    bl_options={"REGISTER","UNDO"}
    def execute(self,context):
        arm=active(context)
        if not arm:
            self.report({"WARNING"},"Build or select a rig first")
            return {"CANCELLED"}
        try:
            action=motion.generate(context,arm,settings(context))
        except Exception as exc:
            self.report({"ERROR"},"Motion failed: "+str(exc))
            return {"CANCELLED"}
        p=settings(context)
        settings(context).status=f"Generated {p.gait.title() if p.motion_type=='WALK' else p.motion_type.title()} · {action.name} · {context.scene.frame_start}–{context.scene.frame_end}"
        self.report({"INFO"},settings(context).status)
        return {"FINISHED"}

class CS_OT_push_clip(Operator):
    bl_idname="chimera_kit.push_clip"
    bl_label="Push action to NLA"
    bl_options={"REGISTER","UNDO"}
    def execute(self,context):
        try:
            strip=motion.push_clip(active(context),settings(context))
        except Exception as exc:
            self.report({"ERROR"},str(exc))
            return {"CANCELLED"}
        settings(context).status="Added animation layer: "+strip.name
        return {"FINISHED"}

class CS_OT_motion_style(Operator):
    bl_idname="chimera_kit.motion_style"
    bl_label="Apply motion style"
    bl_options={"REGISTER","UNDO"}
    def execute(self,context):
        p=settings(context)
        defaults={"exaggeration":1,"body_height":-.08,"bounce":.025,"sway":.025,"body_roll":.015,
            "body_pitch":0,"body_twist":.06,"motion_phase":0,"bounce_frequency":2,"tail_swing":.2,
            "tail_lift":0,"tail_frequency":1,"tail_stiffness":.25,"tail_phase":0,"spine_bend":.10,
            "spine_twist":.10,"spine_flex":.05,"secondary":.3,"foot_roll":.35,"jaw_open":.3,"jaw_chance":.5,"head_bob":.04,"arm_swing":.22,"wing_flap":.055,"stance":.65,
            "cycle_frames":32,"lift":.15,"stride":.52,"body_lean":0}
        styles={
            "NEUTRAL":{},
            "SNEAK":{"cycle_frames":48,"body_height":-.22,"bounce":.008,"sway":.015,"stance":.82,
                "lift":.08,"stride":.34,"tail_swing":.12,"head_bob":.035,"spine_bend":.05,"spine_twist":.05,"spine_flex":.08},
            "HEAVY":{"cycle_frames":48,"body_height":-.13,"bounce":.075,"sway":.05,"body_roll":.065,
                "body_pitch":.04,"stance":.75,"lift":.11,"stride":.42,"tail_lift":.04,"head_bob":.06},
            "CARTOON":{"exaggeration":1.5,"bounce":.065,"sway":.075,"body_roll":.10,"body_pitch":.05,
                "body_twist":.12,"tail_swing":.45,"tail_lift":.07,"spine_bend":.28,"spine_twist":.25,"spine_flex":.14,
                "head_bob":.10,"arm_swing":.5,"wing_flap":.9,"jaw_open":.6,"jaw_chance":1,"lift":.22,"secondary":.6,"foot_roll":.6},
            "RUN":{"cycle_frames":18,"stance":.5,"stride":.95,"lift":.32,"body_lean":.22,"bounce":.06,
                "arm_swing":.75,"foot_roll":.8,"body_twist":.12,"spine_twist":.18,"body_height":-.12}}
        defaults.update(styles[p.tuning_preset])
        for key,value in defaults.items():
            setattr(p,key,value)
        p.status="Applied "+p.tuning_preset.title()+" controls."
        return {"FINISHED"}

class CS_OT_load_motion(Operator):
    bl_idname="chimera_kit.load_motion"
    bl_label="Read controls from action"
    bl_options={"REGISTER","UNDO"}
    def execute(self,context):
        arm=active(context)
        action=arm.animation_data.action if arm and arm.animation_data else None
        if not action or not action.get("cs_parameters"):
            self.report({"WARNING"},"Select an active generated action first")
            return {"CANCELLED"}
        values=json.loads(action["cs_parameters"])
        for key in motion.MOTION_KEYS:
            if key in values:
                setattr(settings(context),key,values[key])
        settings(context).status="Loaded controls from "+action.name
        return {"FINISHED"}

class CS_OT_limb_controls(Operator):
    bl_idname="chimera_kit.limb_controls"
    bl_label="Limb controls"
    bl_options={"REGISTER","UNDO"}
    operation: EnumProperty(items=[("INIT","Enable limb controls","Upgrade older rigs"),
        ("COPY","Copy to paired limb","Copy phase, lift and IK weight to the opposite side")])
    def execute(self,context):
        arm=active(context)
        if not arm: return {"CANCELLED"}
        rig.ensure_motion_controls(arm)
        if self.operation=="COPY":
            source=arm.pose.bones.get(settings(context).limb_choice)
            other=arm.pose.bones.get(source.name[:-2]+(".R" if source.name.endswith(".L") else ".L")) if source else None
            if not other: return {"CANCELLED"}
            for key in ("cs_phase","cs_lift","cs_ik_weight"):
                other[key]=source[key]
            arm.update_tag()
        settings(context).status="Limb controls ready."
        return {"FINISHED"}

class CS_OT_footprints(Operator):
    bl_idname="chimera_kit.footprints"
    bl_label="Footprint objects"
    bl_options={"REGISTER","UNDO"}
    operation: EnumProperty(items=[("CREATE","Create / recreate","Replace footprints from current gait and path"),
        ("RESET","Reset edits","Restore the generated footprint transforms"),
        ("REMOVE","Remove","Remove this rig's footprint objects"),
        ("SELECT_AFTER","Select onward","Select the active footstep and every later one, pivoting on the active step")])
    def execute(self,context):
        arm=active(context)
        if not arm: return {"CANCELLED"}
        try:
            if self.operation=="CREATE":
                objects=motion.create_footprints(context,arm,settings(context))
                settings(context).use_footprints=True
                settings(context).status=f"Created {len(objects)} footprints. Move or rotate them to reshape the walk."
            elif self.operation=="SELECT_AFTER":
                markers=motion.footprint_objects(arm)
                start=context.object if context.object in markers else None
                if not start:
                    raise ValueError("Select one footstep marker first")
                rig.object_mode(context)
                bpy.ops.object.select_all(action="DESELECT")
                count=0
                for obj in markers:
                    if obj["cs_contact_frame"]>=start["cs_contact_frame"]-1e-6:
                        obj.select_set(True)
                        count+=1
                context.view_layer.objects.active=start
                # Rotating now swings the rest of the walk around this step.
                context.scene.tool_settings.transform_pivot_point="ACTIVE_ELEMENT"
                settings(context).status=f"Selected {count} footsteps. R Z turns the walk here; G Z raises it."
            elif self.operation=="RESET":
                from mathutils import Matrix
                for obj in motion.footprint_objects(arm):
                    obj.matrix_world=Matrix(json.loads(obj["cs_original_matrix"]))
                settings(context).status="Footprint edits reset."
            else:
                for obj in motion.footprint_objects(arm):
                    bpy.data.objects.remove(obj,do_unlink=True)
                settings(context).use_footprints=False
                settings(context).status="Footprint objects removed."
        except (ValueError,KeyError) as exc:
            self.report({"ERROR"},str(exc))
            return {"CANCELLED"}
        return {"FINISHED"}

class CS_OT_layer(Operator):
    bl_idname="chimera_kit.layer"
    bl_label="Animation layer"
    bl_options={"REGISTER","UNDO"}
    operation: EnumProperty(items=[("REMOVE","Remove layer","Remove this NLA layer"),
        ("EDIT","Edit action","Make this layer's action active, preserving the layer"),
        ("PLAY","Play layers","Detach the active action and evaluate the enabled layers"),
        ("UNMUTE","Enable all","Enable all layers for playback"),
        ("ADOPT","Enable layer controls","Use Chimera Kit weight and fade controls for this strip"),
        ("REFRESH","Update range","Recompute the weight fades for this strip's current time range")])
    index: IntProperty(default=0)
    def execute(self,context):
        arm=active(context)
        if not arm or not arm.animation_data:
            return {"CANCELLED"}
        ad=arm.animation_data
        if self.operation in {"PLAY","UNMUTE"}:
            if ad.action: ad.action.use_fake_user=True
            ad.action=None
            ad.use_nla=True
            if self.operation=="UNMUTE":
                for track in ad.nla_tracks:
                    track.mute=False
                    track.is_solo=False
            for bone in arm.pose.bones:
                bone.location=(0,0,0)
                bone.rotation_euler=(0,0,0)
                bone.scale=(1,1,1)
        elif self.index>=len(ad.nla_tracks):
            return {"CANCELLED"}
        else:
            track=ad.nla_tracks[self.index]
            if self.operation=="REMOVE":
                for strip in track.strips:
                    if strip.action: strip.action.use_fake_user=True
                    for i in reversed(range(len(arm.cs_layers))):
                        if arm.cs_layers[i].strip_name==strip.name:
                            arm.cs_layers.remove(i)
                ad.nla_tracks.remove(track)
            elif self.operation in {"ADOPT","REFRESH"}:
                for strip in track.strips:
                    entry=motion.layer_entry(arm,strip)
                    if not entry:
                        entry=motion.add_layer_controls(arm,strip,track.name)
                    motion.update_layer_controls(entry)
            elif track.strips and track.strips[0].action:
                strip=track.strips[0]
                slot=strip.action_slot if hasattr(strip,"action_slot") else None
                if ad.action: ad.action.use_fake_user=True
                ad.action=strip.action
                if slot and hasattr(ad,"action_slot"): ad.action_slot=slot
                for item in ad.nla_tracks: item.mute=True
                if ad.action.get("cs_parameters"):
                    values=json.loads(ad.action["cs_parameters"])
                    for key in motion.MOTION_KEYS:
                        if key in values: setattr(settings(context),key,values[key])
        arm.update_tag()
        context.scene.frame_set(context.scene.frame_current)
        settings(context).status="Layer "+self.operation.lower()+" complete"
        return {"FINISHED"}

class CS_OT_capture_pose(Operator):
    bl_idname="chimera_kit.capture_pose"
    bl_label="Capture pose"
    bl_options={"REGISTER","UNDO"}
    def execute(self,context):
        arm=active(context)
        name=settings(context).pose_name.strip() or "My pose"
        if not arm:
            return {"CANCELLED"}
        payload={bone.name:{"location":list(bone.location),"rotation_mode":bone.rotation_mode,
            "rotation_quaternion":list(bone.rotation_quaternion),"rotation_euler":list(bone.rotation_euler),"scale":list(bone.scale)} for bone in arm.pose.bones}
        arm["cs_pose_"+name.replace(" ","_")]=json.dumps(payload)
        settings(context).status=f"Captured pose: {name}"
        return {"FINISHED"}

class CS_OT_apply_pose(Operator):
    bl_idname="chimera_kit.apply_pose"
    bl_label="Apply pose"
    bl_options={"REGISTER","UNDO"}
    def execute(self,context):
        arm=active(context)
        key="cs_pose_"+settings(context).pose_choice
        if not arm or key not in arm:
            self.report({"WARNING"},"Capture or choose a pose first")
            return {"CANCELLED"}
        data=json.loads(arm[key])
        for name,state in data.items():
            bone=arm.pose.bones.get(name)
            if not bone: continue
            bone.location=state["location"]
            bone.rotation_mode=state["rotation_mode"]
            bone.rotation_quaternion=state["rotation_quaternion"]
            bone.rotation_euler=state["rotation_euler"]
            bone.scale=state["scale"]
        settings(context).status=f"Applied pose: {settings(context).pose_choice.replace('_',' ')}"
        return {"FINISHED"}

class CS_OT_clear_animation(Operator):
    bl_idname="chimera_kit.clear_animation"
    bl_label="Clear animation"
    bl_options={"REGISTER","UNDO"}
    def execute(self,context):
        arm=active(context)
        if not arm: return {"CANCELLED"}
        if arm.animation_data:
            arm.animation_data.action=None
            for track in list(arm.animation_data.nla_tracks):
                arm.animation_data.nla_tracks.remove(track)
            arm.cs_layers.clear()
        settings(context).status="Animation cleared"
        return {"FINISHED"}

class CS_OT_export(Operator):
    bl_idname="chimera_kit.export"
    bl_label="Export creature"
    bl_options={"REGISTER"}
    format: EnumProperty(items=[("GLB","glTF Binary","Portable rigged creature"),("FBX","FBX","Biped/CAT-friendly interchange")],default="GLB")
    def execute(self,context):
        arm=active(context)
        if not arm:
            self.report({"WARNING"},"Build or select a rig first")
            return {"CANCELLED"}
        path=bpy.path.abspath(settings(context).io_path)
        if not path or path.endswith("/") or path.endswith("\\"):
            path=os.path.join(bpy.path.abspath("//"),"chimera_kit."+self.format.lower())
        expected="."+self.format.lower()
        if os.path.splitext(path)[1].lower()!=expected:
            path=os.path.splitext(path)[0]+expected
        rig.object_mode(context)
        selected=list(context.selected_objects)
        previous=context.view_layer.objects.active
        bpy.ops.object.select_all(action="DESELECT")
        arm.select_set(True)
        # A bound artist mesh may live in another collection. Include meshes
        # actually deformed by this rig, and exclude all control shape meshes.
        meshes=[obj for obj in context.scene.objects if obj.type=="MESH" and not obj.get("cs_shape")
                and not obj.hide_render and any(m.type=="ARMATURE" and m.object==arm for m in obj.modifiers)]
        hidden={obj:obj.hide_get() for obj in meshes}
        for obj in meshes:
            obj.hide_set(False)
            obj.select_set(True)
        context.view_layer.objects.active=arm
        # Every cycle generated for this creature becomes its own clip: each is
        # placed on a temporary NLA track, which both exporters write as a take.
        temporary=[]
        animation=arm.animation_data
        cycles=[a for a in bpy.data.actions if a.get("cs_motion") and a.get("cs_rig_id")==arm.get("cs_id")] \
            if settings(context).export_all_cycles and animation else []
        if len(cycles)<2:
            cycles=[]
        saved=None
        if cycles:
            saved=(animation.action,[(t,t.mute) for t in animation.nla_tracks])
            animation.action=None
            for track,_ in saved[1]:
                track.mute=True
            for action in cycles:
                track=animation.nla_tracks.new()
                track.name=action.name.split(" · ")[-1]
                strip=track.strips.new(track.name,int(action.frame_range[0]),action)
                strip.name=track.name
                temporary.append(track)
        try:
            if self.format=="GLB":
                options=dict(filepath=path,export_format="GLB",use_selection=True,
                    export_apply=False,export_frame_range=not cycles)
                if "export_animation_mode" in bpy.ops.export_scene.gltf.get_rna_type().properties:
                    options["export_animation_mode"]="NLA_TRACKS" if cycles else "SCENE"
                bpy.ops.export_scene.gltf(**options)
            else:
                bpy.ops.export_scene.fbx(filepath=path,object_types={"ARMATURE","MESH"},use_selection=True,
                    add_leaf_bones=False,bake_anim=True,bake_anim_use_all_actions=False,
                    bake_anim_use_nla_strips=bool(cycles),bake_anim_use_all_bones=True,use_armature_deform_only=True)
        except Exception as exc:
            self.report({"ERROR"},"Export failed: "+str(exc))
            return {"CANCELLED"}
        finally:
            for track in temporary:
                animation.nla_tracks.remove(track)
            if saved:
                for track,mute in saved[1]:
                    track.mute=mute
                animation.action=saved[0]
            bpy.ops.object.select_all(action="DESELECT")
            for obj,was_hidden in hidden.items(): obj.hide_set(was_hidden)
            for obj in selected: obj.select_set(True)
            context.view_layer.objects.active=previous
        settings(context).status="Exported "+path+(f" · {len(cycles)} cycles" if cycles else "")
        self.report({"INFO"},settings(context).status)
        return {"FINISHED"}

class CS_OT_report(Operator):
    bl_idname="chimera_kit.report"
    bl_label="Write JSON manifest"
    def execute(self,context):
        arm=active(context)
        if not arm:
            self.report({"WARNING"},"Build or select a rig first")
            return {"CANCELLED"}
        collection=arm.users_collection[0] if arm.users_collection else None
        report={"schema":1,"tool":"Chimera Kit for Blender","rig":arm.name,
            "species":arm.get("cs_species"),"bones":[b.name for b in arm.data.bones],
            "ik_limbs":json.loads(arm.get("cs_limbs","[]")),"objects":[o.name for o in collection.all_objects] if collection else [],
            "actions":[a.name for a in bpy.data.actions if a.get("cs_motion")],"frame_range":[context.scene.frame_start,context.scene.frame_end]}
        path=bpy.path.abspath("//chimera_kit_manifest.json")
        try:
            with open(path,"w",encoding="utf-8") as handle: json.dump(report,handle,indent=2)
        except OSError as exc:
            self.report({"ERROR"},str(exc))
            return {"CANCELLED"}
        settings(context).status="Manifest written "+path
        return {"FINISHED"}

class CS_OT_pose_tools(Operator):
    bl_idname="chimera_kit.pose_tools"
    bl_label="Pose tools"
    bl_options={"REGISTER","UNDO"}
    operation: EnumProperty(items=[("RESET","Reset pose","Detach active action and reset controls"),
        ("MIRROR","Mirror pose","Swap left and right across the rig X plane"),
        ("KEY","Key pose","Key selected pose bones, or all controls")])

    def execute(self,context):
        arm=active(context)
        if not arm:
            self.report({"WARNING"},"Select a creature rig")
            return {"CANCELLED"}
        if self.operation=="RESET":
            rig.reset(context,arm)
        elif self.operation=="MIRROR":
            from mathutils import Matrix
            mirror=Matrix.Diagonal((-1,1,1,1))
            stored={b.name:b.matrix_basis.copy() for b in arm.pose.bones}
            for bone in arm.pose.bones:
                other=bone.name[:-2]+(".R" if bone.name.endswith(".L") else ".L") if bone.name.endswith((".L",".R")) else bone.name
                if other not in stored: continue
                source=arm.data.bones[other].matrix_local
                dest=bone.bone.matrix_local
                bone.matrix_basis=dest.inverted() @ mirror @ source @ stored[other] @ source.inverted() @ mirror @ dest
        else:
            selected=list(context.selected_pose_bones or []) if context.object==arm and context.mode=="POSE" else []
            for bone in selected or list(arm.pose.bones):
                bone.keyframe_insert("location",frame=context.scene.frame_current,group=bone.name)
                bone.keyframe_insert("rotation_euler",frame=context.scene.frame_current,group=bone.name)
                bone.keyframe_insert("scale",frame=context.scene.frame_current,group=bone.name)
        settings(context).status=self.operation.title()+" pose complete"
        context.view_layer.update()
        return {"FINISHED"}

class CS_OT_bind(Operator):
    bl_idname="chimera_kit.bind"
    bl_label="Bind selected meshes"
    bl_options={"REGISTER","UNDO"}
    method: EnumProperty(items=[("ENVELOPE","Distance weights","Stable closest bone segment weights"),
        ("AUTO","Automatic weights","Blender bone heat automatic weights")],default="ENVELOPE")

    def execute(self,context):
        arm=active(context)
        meshes=[o for o in context.selected_objects if o.type=="MESH" and not o.get("cs_preview") and not o.get("cs_owned")]
        if not arm or not meshes:
            self.report({"WARNING"},"Choose an Active creature, then select your mesh objects")
            return {"CANCELLED"}
        if arm.data.pose_position=="REST" or context.mode!="OBJECT":
            self.report({"WARNING"},"Finish Fit mode, switch to Object mode and select the meshes")
            return {"CANCELLED"}
        if self.method=="AUTO":
            arm.select_set(True)
            context.view_layer.objects.active=arm
            bpy.ops.object.parent_set(type="ARMATURE_AUTO")
            for obj in meshes: obj["cs_bound"]=arm["cs_id"]
        else:
            inverse=arm.matrix_world.inverted()
            bones=[b for b in arm.data.bones if b.use_deform]
            for obj in meshes:
                world=obj.matrix_world.copy()
                obj.parent=arm
                obj.matrix_world=world
                groups={b.name:obj.vertex_groups.get(b.name) or obj.vertex_groups.new(name=b.name) for b in bones}
                transform=inverse @ obj.matrix_world
                indexes=list(range(len(obj.data.vertices)))
                for group in groups.values(): group.remove(indexes)
                for vertex in obj.data.vertices:
                    point=transform @ vertex.co
                    distances=[]
                    for bone in bones:
                        a,b=bone.head_local,bone.tail_local
                        ab=b-a
                        t=max(0,min(1,(point-a).dot(ab)/max(ab.length_squared,1e-9)))
                        distances.append(((point-a-ab*t).length_squared,bone.name))
                    closest=sorted(distances)[:3]
                    weights=[1/(d+0.00001)**2 for d,name in closest]
                    total=sum(weights)
                    for (_,name),weight in zip(closest,weights):
                        groups[name].add([vertex.index],weight/total,"REPLACE")
                mod=next((m for m in obj.modifiers if m.type=="ARMATURE" and m.object==arm),None)
                if not mod:
                    mod=obj.modifiers.new("Chimera Kit Skin","ARMATURE")
                    mod.object=arm
                obj["cs_bound"]=arm["cs_id"]
        settings(context).status=f"Bound {len(meshes)} mesh(es) · refine weights in Weight Paint mode"
        return {"FINISHED"}

class CS_OT_preview(Operator):
    bl_idname="chimera_kit.preview"
    bl_label="Toggle mannequin"
    bl_options={"REGISTER","UNDO"}
    def execute(self,context):
        arm=active(context)
        if not arm: return {"CANCELLED"}
        objects=[o for o in arm.children if o.get("cs_preview")]
        hidden=not all(o.hide_get() for o in objects)
        for obj in objects:
            obj.hide_set(hidden)
            obj.hide_render=hidden
        return {"FINISHED"}

class CS_OT_preset_file(Operator):
    bl_idname="chimera_kit.preset_file"
    bl_label="Creature recipe"
    bl_options={"REGISTER","UNDO"}
    operation: EnumProperty(items=[("SAVE","Save recipe","Write the current rig recipe as JSON"),
        ("LOAD","Load recipe","Load an editable recipe without building a rig")])
    def execute(self,context):
        p=settings(context)
        path=bpy.path.abspath(p.io_path)
        if not path.lower().endswith(".json"):
            path=os.path.splitext(path)[0]+".json"
        keys=("species","size","body_length","body_width","leg_length","arm_length","head_size","leg_pairs","spine_links","tail_links",
              "fingers","finger_links","mannequin_style","wings","antennae","ponytail","neck_length","neck_links","jaw","antenna_length","antenna_links",
              "tail_length","wing_span","wing_links","eyes","eye_size","chest_size","belly_size","hip_size",
              "eye_spacing","eye_height","eye_forward","front_legs","hind_legs",
              "wing_style","wing_frequency","wing_fold","jaw_open","jaw_chance","jaw_rate","eye_bounce","body_wave","secondary","foot_roll",
              "motion_type","jump_height","jump_distance","jump_crouch","strike_side","strike_height","body_lean","fly_height",
              "gait","cycle_frames","cycles","start_frame","stride","lift","stance","foot_planting","exaggeration","body_height",
              "bounce","bounce_frequency","sway","body_roll","body_pitch","body_twist","motion_phase","tail_swing","tail_lift",
              "tail_frequency","tail_stiffness","tail_phase","spine_bend","spine_twist","spine_flex","head_bob","arm_swing","wing_flap",
              "travel","motion_scope","layer_name","layer_weight","layer_blend")
        try:
            if self.operation=="SAVE":
                with open(path,"w",encoding="utf-8") as handle:
                    json.dump({"schema":2,"chimera_kit":{key:getattr(p,key) for key in keys}},handle,indent=2)
            else:
                with open(path,encoding="utf-8") as handle: data=json.load(handle)
                # Recipes saved under the add-on's earlier name still load.
                if "chimera_kit" in data: data["character_studio"]=data["chimera_kit"]
                if data.get("schema") not in {1,2} or not isinstance(data.get("character_studio"),dict):
                    raise ValueError("This is not a Chimera Kit recipe")
                values=data["character_studio"]
                if values.get("species") not in {x[0] for x in __import__(__package__,fromlist=["PRESETS"]).PRESETS}:
                    raise ValueError("Unknown creature species")
                p.species=values["species"]
                for key in keys[1:]:
                    if key in values:
                        prop=p.bl_rna.properties[key]
                        value=values[key]
                        if prop.type=="ENUM":
                            if value not in {item.identifier for item in prop.enum_items}:
                                raise ValueError("Unknown recipe value for "+key)
                        elif prop.type=="STRING" and not isinstance(value,str):
                            raise ValueError("Expected text for "+key)
                        elif prop.type=="BOOLEAN":
                            value=bool(value)
                        elif prop.type not in {"STRING","ENUM"} and not isinstance(value,(int,float)):
                            raise ValueError("Expected a number for "+key)
                        setattr(p,key,value)
        except (OSError,ValueError,TypeError) as exc:
            self.report({"ERROR"},str(exc))
            return {"CANCELLED"}
        p.status=self.operation.title()+" recipe: "+path
        return {"FINISHED"}

class CS_OT_animation_export(Operator):
    bl_idname="chimera_kit.animation_export"
    bl_label="Bake deform skeleton"
    bl_options={"REGISTER","UNDO"}
    def execute(self,context):
        arm=active(context)
        if not arm: return {"CANCELLED"}
        rig.select(context,arm)
        duplicate=arm.copy()
        duplicate.data=arm.data.copy()
        context.scene.collection.objects.link(duplicate)
        duplicate.name=arm.name+" · Baked"
        duplicate.animation_data_clear()
        duplicate["cs_rig"]=False
        bpy.ops.object.select_all(action="DESELECT")
        duplicate.select_set(True)
        context.view_layer.objects.active=duplicate
        # Copy final evaluated transforms from the live rig; Bake Action samples
        # these constraints into an independent skeleton for DCC interchange.
        for bone in duplicate.pose.bones:
            for c in list(bone.constraints): bone.constraints.remove(c)
            c=bone.constraints.new("COPY_TRANSFORMS")
            c.target=arm
            c.subtarget=bone.name
        bpy.ops.object.mode_set(mode="POSE")
        bpy.ops.nla.bake(frame_start=context.scene.frame_start,frame_end=context.scene.frame_end,
            only_selected=False,visual_keying=True,clear_constraints=True,use_current_action=False,bake_types={"POSE"})
        bpy.ops.object.mode_set(mode="OBJECT")
        settings(context).status="Baked independent skeleton created: "+duplicate.name
        return {"FINISHED"}

def fill_map(p,source,target):
    source_kind,target_kind,rows=retarget.automap(source,target)
    p.rt_items.clear()
    for row in rows:
        item=p.rt_items.add()
        for key,value in row.items():
            setattr(item,key,value)
    p.rt_source_kind,p.rt_target_kind=source_kind,target_kind
    return sum(1 for row in rows if row["source"] and row["target"])

def map_rows(p):
    return [dict(slot=i.slot,label=i.label,kind=i.kind,source=i.source,target=i.target,ref=i.ref) for i in p.rt_items]

class CS_OT_retarget_pick(Operator):
    bl_idname="chimera_kit.retarget_pick"
    bl_label="Use selected armature"
    bl_description="Use the selected armature, or the active creature when nothing else is selected"
    bl_options={"REGISTER","UNDO"}
    role: EnumProperty(items=[("SOURCE","Motion from",""),("TARGET","Apply to","")])
    def execute(self,context):
        p=settings(context)
        obj=context.object if context.object and context.object.type=="ARMATURE" else active(context)
        if not obj:
            self.report({"WARNING"},"Select an armature first")
            return {"CANCELLED"}
        if self.role=="SOURCE": p.rt_source=obj
        else: p.rt_target=obj
        return {"FINISHED"}

class CS_OT_retarget_automap(Operator):
    bl_idname="chimera_kit.retarget_automap"
    bl_label="Auto-map bones"
    bl_description="Recognise both armatures and pair their bones by name and position in the body"
    bl_options={"REGISTER","UNDO"}
    def execute(self,context):
        p=settings(context)
        if not p.rt_source or not p.rt_target or p.rt_source==p.rt_target:
            self.report({"WARNING"},"Choose two different armatures")
            return {"CANCELLED"}
        count=fill_map(p,p.rt_source,p.rt_target)
        p.rt_show_map=True
        p.status=f"Mapped {count} bones · {p.rt_source_kind} → {p.rt_target_kind}. Check the table, then retarget."
        self.report({"INFO"},p.status)
        return {"FINISHED"}

class CS_OT_retarget_run(Operator):
    bl_idname="chimera_kit.retarget_run"
    bl_label="Retarget motion"
    bl_description="Key the target armature so it performs the source armature's motion"
    bl_options={"REGISTER","UNDO"}
    def execute(self,context):
        p=settings(context)
        source,target=p.rt_source,p.rt_target
        if not source or not target or source==target:
            self.report({"WARNING"},"Choose two different armatures")
            return {"CANCELLED"}
        if not p.rt_items:
            fill_map(p,source,target)
        start,end=p.rt_frame_start,p.rt_frame_end
        if p.rt_use_source_range:
            found=retarget.action_range(source)
            start,end=found if found else (context.scene.frame_start,context.scene.frame_end)
        try:
            # Old keys on the target must not mix into the sampled result.
            if target.get("cs_rig"):
                rig.reset(context,target)
            elif target.animation_data and target.animation_data.action:
                target.animation_data.action.use_fake_user=True
                target.animation_data.action=None
            action,count,scale=retarget.retarget(context,source,target,map_rows(p),start,end,
                align_rest=p.rt_align_rest,in_place=p.rt_in_place,leg_mode=p.rt_leg_mode,
                height_offset=p.rt_height_offset)
        except Exception as exc:
            self.report({"ERROR"},"Retarget failed: "+str(exc))
            return {"CANCELLED"}
        context.scene.frame_start,context.scene.frame_end=start,end
        if target.get("cs_rig"):
            p.active_rig=target
        p.rt_frame_start,p.rt_frame_end=start,end
        p.status=f"Retargeted {count} bones to {target.name} · frames {start}–{end} · size ratio {scale:.2f} · {action.name}"
        self.report({"INFO"},p.status)
        return {"FINISHED"}

class CS_OT_import_mixamo(Operator):
    bl_idname="chimera_kit.import_mixamo"
    bl_label="Import Mixamo FBX"
    bl_description="Import a Mixamo (or other) FBX animation and make it the motion source"
    bl_options={"REGISTER","UNDO"}
    filepath: bpy.props.StringProperty(subtype="FILE_PATH")
    filter_glob: bpy.props.StringProperty(default="*.fbx",options={"HIDDEN"})
    def invoke(self,context,event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}
    def execute(self,context):
        p=settings(context)
        creature=active(context)
        try:
            armature,created=retarget.import_fbx(context,self.filepath)
        except Exception as exc:
            self.report({"ERROR"},"Import failed: "+str(exc))
            return {"CANCELLED"}
        armature["cs_motion_source"]=True
        p.rt_source=armature
        if not p.rt_target and creature:
            p.rt_target=creature
        found=retarget.action_range(armature)
        if found:
            p.rt_frame_start,p.rt_frame_end=found
        message=f"Imported {armature.name} · {len(armature.data.bones)} bones"
        if p.rt_target and p.rt_target!=armature:
            count=fill_map(p,armature,p.rt_target)
            message+=f" · mapped {count} bones to {p.rt_target.name}. Press Retarget motion."
        else:
            message+=". Choose the rig to apply it to."
        p.status=message
        self.report({"INFO"},message)
        return {"FINISHED"}

class CS_OT_retarget_map_file(Operator):
    bl_idname="chimera_kit.retarget_map_file"
    bl_label="Bone map file"
    bl_options={"REGISTER","UNDO"}
    operation: EnumProperty(items=[("SAVE","Save map","Write the bone map as JSON"),
        ("LOAD","Load map","Read a bone map saved earlier")])
    def execute(self,context):
        p=settings(context)
        path=bpy.path.abspath(p.io_path)
        if not path.lower().endswith(".json"):
            path=os.path.splitext(path)[0]+".json"
        try:
            if self.operation=="SAVE":
                with open(path,"w",encoding="utf-8") as handle:
                    json.dump({"schema":1,"chimera_kit_bone_map":map_rows(p)},handle,indent=2)
            else:
                with open(path,encoding="utf-8") as handle: data=json.load(handle)
                rows=data.get("chimera_kit_bone_map") or data.get("character_studio_bone_map")
                if not isinstance(rows,list):
                    raise ValueError("This is not a Chimera Kit bone map")
                p.rt_items.clear()
                for row in rows:
                    item=p.rt_items.add()
                    for key in ("slot","label","kind","source","target","ref"):
                        setattr(item,key,str(row.get(key,"")))
        except (OSError,ValueError,TypeError) as exc:
            self.report({"ERROR"},str(exc))
            return {"CANCELLED"}
        p.status=self.operation.title()+" bone map: "+path
        return {"FINISHED"}

CLASSES=(CS_OT_sync_settings,CS_OT_retarget_pick,CS_OT_retarget_automap,CS_OT_retarget_run,CS_OT_import_mixamo,CS_OT_retarget_map_file,
         CS_OT_build,CS_OT_add_module,CS_OT_delete,CS_OT_validate,CS_OT_fit_start,CS_OT_fit_finish,
         CS_OT_generate_motion,CS_OT_push_clip,CS_OT_capture_pose,CS_OT_apply_pose,
         CS_OT_clear_animation,CS_OT_export,CS_OT_report,CS_OT_pose_tools,CS_OT_bind,
         CS_OT_preview,CS_OT_preset_file,CS_OT_animation_export,CS_OT_motion_style,
         CS_OT_load_motion,CS_OT_limb_controls,CS_OT_footprints,CS_OT_layer)
