"""Native Blender sidebar panels, grouped by the artist's workflow."""
import bpy
from . import rig, motion

TAB_ICONS={"BUILD":"COLLECTION_COLOR_05","ANIMATE":"COLLECTION_COLOR_04","LAYERS":"COLLECTION_COLOR_03",
           "RETARGET":"COLLECTION_COLOR_06","EXPORT":"COLLECTION_COLOR_02"}

class CSPanel:
    bl_space_type="VIEW_3D"
    bl_region_type="UI"
    bl_category="Chimera Kit"
    tab=None
    @classmethod
    def poll(cls,context):
        # Only the panels of the chosen workflow are shown.
        return cls.tab is None or context.scene.cs_settings.ui_tab==cls.tab
    def draw_header(self,context):
        if self.tab:
            self.layout.label(text="",icon=TAB_ICONS[self.tab])

class CS_PT_studio(CSPanel,bpy.types.Panel):
    bl_idname="CS_PT_studio"
    bl_label="CHARACTER STUDIO"
    bl_order=0
    def draw(self,context):
        p=context.scene.cs_settings
        layout=self.layout
        from . import bl_info
        layout.label(text="Version "+".".join(str(n) for n in bl_info["version"])+" loaded",icon="CHECKMARK")
        row=layout.row(align=True)
        row.scale_y=1.5
        row.prop(p,"ui_tab",expand=True)
        layout.prop(p,"active_rig",text="Creature")
        arm=rig.active(context)
        if arm:
            row=layout.row(align=True)
            row.label(text=arm.get("cs_species","").title(),icon="OUTLINER_OB_ARMATURE")
            row.label(text=f"{len(arm.data.bones)} bones")
        if p.status:
            box=layout.box()
            # Wrap status so long export paths do not force an oversized panel.
            import textwrap
            for line in textwrap.wrap(p.status,width=max(24,int(context.region.width/7)-6)):
                box.label(text=line)

class CS_PT_build(CSPanel,bpy.types.Panel):
    bl_idname="CS_PT_build"
    bl_label="Creature builder"
    tab="BUILD"
    bl_order=1
    bl_parent_id="CS_PT_studio"
    def draw(self,context):
        layout=self.layout
        p=context.scene.cs_settings
        layout.prop(p,"species",text="Preset")
        from . import PRESETS
        layout.label(text=f"{len(PRESETS)} presets · Biped is the box figure",icon="OUTLINER_OB_ARMATURE")
        layout.prop(p,"character_name")
        layout.prop(p,"size")
        col=layout.column(align=True)
        col.prop(p,"body_length")
        col.prop(p,"body_width")
        col.prop(p,"leg_length")
        col.prop(p,"head_size")
        if p.species not in {"FISH","SHARK","DOLPHIN","WHALE","TADPOLE","SNAKE","WORM"}:
            col.prop(p,"neck_length")
            shape=layout.box()
            shape.label(text="Trunk shape",icon="MOD_SIMPLEDEFORM")
            row=shape.row(align=True)
            row.prop(p,"chest_size")
            row.prop(p,"belly_size")
            row.prop(p,"hip_size")
        if p.species in {"BIPED","HUMAN","ALLOSAUR","TREX","ALIEN","CENTAUR","APE","MECH","ANGEL","PENGUIN","MECH_TROOPER","MECH_FLYER","MECH_POD"}: col.prop(p,"arm_length")
        layout.separator()
        box=layout.box()
        box.label(text="Custom structure",icon="BONE_DATA")
        if p.species in {"BIPED","MECH_TROOPER","MECH_FLYER"}:
            box.prop(p,"spine_links")
            row=box.row(align=True)
            row.prop(p,"fingers")
            row.prop(p,"finger_links")
        else:
            if p.species not in {"FISH","SHARK","DOLPHIN","WHALE","TADPOLE","SNAKE","WORM"}:
                box.prop(p,"leg_pairs")
            box.prop(p,"spine_links")
            if p.leg_pairs>=2 and p.species not in {"FISH","SHARK","DOLPHIN","WHALE","TADPOLE","SNAKE","WORM","SPIDER","CRAB","CENTIPEDE"}:
                row=box.row(align=True)
                row.prop(p,"front_legs")
                row.prop(p,"hind_legs")
        if p.species not in {"FISH","SHARK","DOLPHIN","WHALE","TADPOLE","SNAKE","WORM"}:
            box.prop(p,"neck_links")
        box=layout.box()
        box.label(text="Accessories",icon="OUTLINER_OB_ARMATURE")
        row=box.row(align=True)
        row.prop(p,"tail_links",text="Tail links")
        row.prop(p,"tail_length",text="Length")
        row=box.row(align=True)
        row.prop(p,"wings",toggle=True)
        row.prop(p,"antennae",toggle=True)
        row.prop(p,"ponytail",toggle=True)
        row.prop(p,"jaw",toggle=True)
        row.prop(p,"eyes",toggle=True)
        if p.wings:
            row=box.row(align=True)
            row.prop(p,"wing_span")
            row.prop(p,"wing_links",text="Joints")
        if p.eyes:
            col=box.column(align=True)
            col.prop(p,"eye_size")
            col.prop(p,"eye_spacing")
            col.prop(p,"eye_height")
            col.prop(p,"eye_forward")
        if p.antennae:
            row=box.row(align=True)
            row.prop(p,"antenna_length",text="Antenna length")
            row.prop(p,"antenna_links",text="Links")
        if p.wings or p.jaw or p.antennae or p.ponytail:
            box.label(text="Their motion: Animate tab › Motion tuning.",icon="INFO")
        row=layout.row(align=True)
        row.prop(p,"mannequin")
        row.prop(p,"show_rig")
        if p.mannequin:
            layout.prop(p,"mannequin_style",expand=True)
        row=layout.row()
        row.scale_y=2.6
        row.operator("chimera_kit.build",text="Build new creature",icon="ADD")
        arm=rig.active(context)
        layout.prop(p,"live_build",toggle=True,icon="FILE_REFRESH")
        if arm and arm.get("cs_species")!=p.species:
            col=layout.column(align=True)
            col.label(text="Sliders are set up for a new "+p.species.replace("_"," ").title()+".",icon="INFO")
            col.operator("chimera_kit.sync_settings",text="Back to "+arm.name)
        elif arm and p.live_build:
            reason=rig.locked(arm)
            layout.label(text=("Live body off: creature "+reason) if reason else "Sliders reshape the active creature.",icon="INFO")
        else:
            layout.label(text="Each build creates a separate editable rig.",icon="INFO")

class CS_PT_modules(CSPanel,bpy.types.Panel):
    bl_idname="CS_PT_modules"
    bl_label="Append custom structures"
    tab="BUILD"
    bl_parent_id="CS_PT_build"
    bl_options={"DEFAULT_CLOSED"}
    def draw(self,context):
        layout=self.layout
        p=context.scene.cs_settings
        arm=rig.active(context)
        layout.enabled=arm is not None
        layout.prop(p,"module_type")
        if arm:
            layout.prop_search(p,"module_parent",arm.data,"bones",text="Parent")
        if p.module_type in {"TAIL","SPINE"}: layout.prop(p,"module_links")
        if p.module_type!="HUB": layout.prop(p,"module_length")
        layout.operator("chimera_kit.add_module",icon="BONE_DATA")
        layout.label(text="Returns rig to rest for structural editing.")

class CS_PT_motion(CSPanel,bpy.types.Panel):
    bl_idname="CS_PT_motion"
    bl_label="Cycle"
    tab="ANIMATE"
    bl_order=1
    bl_parent_id="CS_PT_studio"
    def draw(self,context):
        layout=self.layout
        p=context.scene.cs_settings
        arm=rig.active(context)
        layout.enabled=arm is not None
        import json
        limbs=json.loads(arm.get("cs_limbs","[]")) if arm else []
        row=layout.row(align=True)
        row.scale_y=1.4
        row.prop(p,"motion_type",expand=True)
        kind=p.motion_type
        if not limbs and arm and kind!="IDLE":
            layout.label(text="No legs: this creature swims or slithers.",icon="INFO")
            kind="SWIM"
        row=layout.row(align=True)
        row.prop(p,"cycle_frames",text="Frames")
        row.prop(p,"cycles")
        layout.prop(p,"start_frame")
        if kind=="WALK":
            layout.prop(p,"gait")
            col=layout.column(align=True)
            col.prop(p,"stride",slider=True)
            col.prop(p,"lift",slider=True)
            col.prop(p,"stance",slider=True)
        elif kind=="SWIM":
            layout.prop(p,"stride",text="Speed",slider=True)
        elif kind=="JUMP":
            col=layout.column(align=True)
            col.prop(p,"jump_height",slider=True)
            col.prop(p,"jump_crouch",slider=True)
            if p.travel:
                col.prop(p,"jump_distance",slider=True)
        elif kind=="FLY":
            layout.prop(p,"fly_height",slider=True)
            layout.label(text="Choose Glide in Wings to soar.",icon="INFO")
        elif kind in {"PUNCH","KICK"}:
            layout.prop(p,"strike_side",expand=True)
            layout.prop(p,"strike_height",slider=True)
        if arm and "wing.L" in arm.data.bones:
            wings=layout.box()
            wings.label(text="Wings",icon="MOD_CLOTH")
            wings.prop(p,"wing_style",text="")
            if p.wing_style!="FOLDED":
                wings.prop(p,"wing_flap",slider=True)
        if kind in {"WALK","SWIM","JUMP","FLY"}:
            layout.prop(p,"travel")
        if p.travel and kind in {"WALK","SWIM","FLY"}:
            layout.prop(p,"path_object")
            if kind=="WALK":
                layout.prop(p,"foot_planting")
        if limbs and kind=="WALK":
            reach=sum(l["reach"] for l in limbs)/len(limbs)
            stride=p.stride*reach
            fps=context.scene.render.fps/context.scene.render.fps_base
            layout.label(text=f"Stride {stride:.3f} m · speed {stride/p.stance*fps/p.cycle_frames:.2f} m/s")
        action=arm.animation_data.action if arm and arm.animation_data else None
        walking=bool(action and action.get("cs_motion"))
        row=layout.row()
        row.scale_y=2.6
        row.operator("chimera_kit.generate_motion",text=("New " if walking else "Generate ")+("swim" if kind=="SWIM" else kind.lower()),icon="ACTION")
        row=layout.row(align=True)
        row.scale_y=1.6
        screen=getattr(context,"screen",None)
        playing=bool(screen and screen.is_animation_playing)
        row.operator("screen.animation_play",text="Pause" if playing else "Play",icon="PAUSE" if playing else "PLAY")
        row.prop(p,"live_update",toggle=True,icon="FILE_REFRESH")
        if p.live_update:
            row.prop(p,"live_on_release",toggle=True)
        if walking and p.live_update:
            layout.label(text="Controls update the walk when you let go." if p.live_on_release else "Controls update the walk as you drag.",icon="INFO")
        elif walking:
            layout.label(text="Live update is off: generate again to apply changes.")
        else:
            layout.label(text="Generate once, press Play, then drag any slider.")

class CS_PT_tuning(CSPanel,bpy.types.Panel):
    bl_idname="CS_PT_tuning"
    bl_label="Motion tuning"
    tab="ANIMATE"
    bl_order=2
    bl_parent_id="CS_PT_studio"
    def draw(self,context):
        layout=self.layout
        p=context.scene.cs_settings
        layout.enabled=rig.active(context) is not None
        row=layout.row(align=True)
        row.prop(p,"tuning_preset",text="")
        row.operator("chimera_kit.motion_style",text="Apply style")
        layout.prop(p,"exaggeration",slider=True)
        layout.operator("chimera_kit.load_motion",text="Read controls from active action",icon="IMPORT")
        body=layout.box()
        body.label(text="Body / hub motion",icon="ORIENTATION_GIMBAL")
        for key in ("body_height","body_lean","bounce","bounce_frequency","sway","body_roll","body_pitch","body_twist","motion_phase"):
            body.prop(p,key,slider=key not in {"bounce_frequency","motion_phase"})
        spine=layout.box()
        spine.label(text="Spine, head & limbs",icon="BONE_DATA")
        for key in ("spine_bend","spine_twist","spine_flex","body_wave","head_bob","arm_swing","foot_roll"):
            spine.prop(p,key,slider=True)
        tail=layout.box()
        tail.label(text="Tail dynamics",icon="CURVE_PATH")
        for key in ("tail_swing","tail_lift","tail_frequency","tail_stiffness","tail_phase"):
            tail.prop(p,key,slider=key not in {"tail_frequency","tail_phase"})
        arm=rig.active(context)
        names=arm.data.bones.keys() if arm else []
        wings=layout.box()
        wings.label(text="Wings",icon="MOD_CLOTH")
        if "wing.L" in names:
            wings.prop(p,"wing_style",text="")
            wings.prop(p,"wing_flap",slider=True)
            wings.prop(p,"wing_frequency")
            if p.wing_style!="FOLDED":
                wings.prop(p,"wing_fold",slider=True)
        else:
            wings.label(text="None on this creature. Add them in Build › Accessories.")
        extras=layout.box()
        extras.label(text="Jaw, antennae & ponytail",icon="MOD_WAVE")
        if "jaw" in names:
            extras.prop(p,"jaw_open",slider=True)
            extras.prop(p,"jaw_chance",slider=True)
            extras.prop(p,"jaw_rate")
        else:
            extras.label(text="No jaw. Add one in Build › Accessories.")
        extras.prop(p,"secondary",slider=True)
        if "eye.01.L" in names:
            extras.prop(p,"eye_bounce",slider=True)
        if not p.live_update:
            layout.operator("chimera_kit.generate_motion",text="Apply as a new walk",icon="FILE_REFRESH")

class CS_PT_limbs(CSPanel,bpy.types.Panel):
    bl_idname="CS_PT_limbs"
    bl_label="Per-limb timing & footsteps"
    tab="ANIMATE"
    bl_parent_id="CS_PT_tuning"
    bl_options={"DEFAULT_CLOSED"}
    def draw(self,context):
        layout=self.layout
        p=context.scene.cs_settings
        arm=rig.active(context)
        if not arm: return
        layout.prop(p,"limb_choice")
        control=arm.pose.bones.get(p.limb_choice)
        if not control or "cs_phase" not in control:
            layout.operator("chimera_kit.limb_controls",text="Enable controls on this rig").operation="INIT"
        else:
            layout.prop(control,'["cs_phase"]',text="Phase offset")
            layout.prop(control,'["cs_lift"]',text="Foot lift multiplier")
            layout.prop(control,'["cs_ik_weight"]',text="IK weight",slider=True)
            layout.operator("chimera_kit.limb_controls",text="Copy to paired limb").operation="COPY"
        box=layout.box()
        box.label(text="Editable traveling footprints",icon="EMPTY_DATA")
        box.label(text="Move markers: the walk follows." if p.live_update else "Move markers, then generate a new walk.")
        box.prop(p,"use_footprints")
        row=box.row()
        row.enabled=p.travel
        row.operator("chimera_kit.footprints",text="Create / recreate").operation="CREATE"
        box.operator("chimera_kit.footprints",text="Select from active step onward",icon="RESTRICT_SELECT_OFF").operation="SELECT_AFTER"
        col=box.column(align=True)
        col.label(text="Turn: select onward, then R Z.")
        col.label(text="Stairs or slope: O for proportional, G Z.")
        row=box.row(align=True)
        row.operator("chimera_kit.footprints",text="Reset edits").operation="RESET"
        row.operator("chimera_kit.footprints",text="Remove").operation="REMOVE"

class CS_PT_layers(CSPanel,bpy.types.Panel):
    bl_idname="CS_PT_layers"
    bl_label="Animation layers"
    tab="LAYERS"
    bl_order=1
    bl_parent_id="CS_PT_studio"
    def draw(self,context):
        layout=self.layout
        p=context.scene.cs_settings
        arm=rig.active(context)
        layout.enabled=arm is not None
        layout.prop(p,"motion_scope")
        layout.label(text="Generate chosen channels, then add a layer.")
        layout.prop(p,"layer_name")
        row=layout.row(align=True)
        row.prop(p,"layer_blend",text="")
        row.prop(p,"layer_weight",text="Weight",slider=True)
        row=layout.row(align=True)
        row.prop(p,"layer_blend_in")
        row.prop(p,"layer_blend_out")
        layout.operator("chimera_kit.push_clip",text="Add active action as layer",icon="ADD")
        row=layout.row(align=True)
        row.operator("chimera_kit.layer",text="Play enabled layers",icon="PLAY").operation="PLAY"
        row.operator("chimera_kit.layer",text="Enable all").operation="UNMUTE"
        ad=arm.animation_data if arm else None
        if ad and ad.action:
            layout.label(text="Previewing action: "+ad.action.name,icon="ACTION")
            layout.label(text="Generation isolates this action for tuning.")
        if not ad or not ad.nla_tracks:
            layout.label(text="No layers yet.")
            return
        for i,track in reversed(list(enumerate(ad.nla_tracks))):
            box=layout.box()
            row=box.row(align=True)
            row.prop(track,"mute",text="",icon="HIDE_ON" if track.mute else "HIDE_OFF")
            row.prop(track,"is_solo",text="",icon="SOLO_ON" if track.is_solo else "SOLO_OFF")
            entry=motion.layer_entry(arm,track.strips[0]) if track.strips else None
            if entry:
                row.prop(entry,"label",text="")
            else:
                row.prop(track,"name",text="")
            op=row.operator("chimera_kit.layer",text="",icon="X")
            op.operation="REMOVE"; op.index=i
            for strip in track.strips:
                row=box.row(align=True)
                row.prop(strip,"blend_type",text="")
                entry=motion.layer_entry(arm,strip)
                if entry:
                    row.prop(entry,"weight",text="Weight",slider=True)
                else:
                    op=row.operator("chimera_kit.layer",text="Enable weights")
                    op.operation="ADOPT"; op.index=i
                row=box.row(align=True)
                row.prop(strip,"frame_start",text="Start")
                row.prop(strip,"frame_end",text="End")
                row=box.row(align=True)
                if entry:
                    row.prop(entry,"fade_in",text="Fade in")
                    row.prop(entry,"fade_out",text="Fade out")
            op=box.operator("chimera_kit.layer",text="Apply range / fade changes")
            op.operation="REFRESH"; op.index=i
            op=box.operator("chimera_kit.layer",text="Edit / read this action",icon="ACTION")
            op.operation="EDIT"; op.index=i

class CS_PT_pose(CSPanel,bpy.types.Panel):
    bl_idname="CS_PT_pose"
    bl_label="Pose & fit"
    tab="BUILD"
    bl_order=2
    bl_parent_id="CS_PT_studio"
    def draw(self,context):
        layout=self.layout
        p=context.scene.cs_settings
        arm=rig.active(context)
        layout.enabled=arm is not None
        row=layout.row(align=True)
        for action,label in (("RESET","Rest"),("MIRROR","Mirror"),("KEY","Key pose")):
            op=row.operator("chimera_kit.pose_tools",text=label)
            op.operation=action
        layout.prop(p,"pose_name",text="Name")
        layout.operator("chimera_kit.capture_pose",text="Capture pose",icon="POSE_HLT")
        row=layout.row(align=True)
        row.prop(p,"pose_choice",text="")
        row.operator("chimera_kit.apply_pose",text="Apply")
        layout.separator()
        row=layout.row(align=True)
        row.operator("chimera_kit.fit_start",text="Start fit",icon="EDITMODE_HLT")
        row.operator("chimera_kit.fit_finish",text="Finish fit",icon="CHECKMARK")
        layout.label(text="Fit edit bones before binding your mesh.")

class CS_PT_skin(CSPanel,bpy.types.Panel):
    bl_idname="CS_PT_skin"
    bl_label="Skin your mesh"
    tab="BUILD"
    bl_order=3
    bl_parent_id="CS_PT_studio"
    def draw(self,context):
        layout=self.layout
        layout.enabled=rig.active(context) is not None
        layout.label(text="Choose the rig above; select your mesh.",icon="MESH_DATA")
        row=layout.row(align=True)
        row.operator("chimera_kit.bind",text="Distance weights").method="ENVELOPE"
        row.operator("chimera_kit.bind",text="Auto weights").method="AUTO"
        layout.operator("chimera_kit.preview",text="Show / hide mannequin",icon="HIDE_OFF")

class CS_PT_files(CSPanel,bpy.types.Panel):
    bl_idname="CS_PT_files"
    bl_label="Library & export"
    tab="EXPORT"
    bl_order=1
    bl_parent_id="CS_PT_studio"
    def draw(self,context):
        layout=self.layout
        p=context.scene.cs_settings
        layout.prop(p,"io_path",text="File")
        row=layout.row(align=True)
        row.operator("chimera_kit.preset_file",text="Save recipe").operation="SAVE"
        row.operator("chimera_kit.preset_file",text="Load recipe").operation="LOAD"
        row=layout.row(align=True)
        layout.prop(p,"export_all_cycles")
        row=layout.row(align=True)
        row.operator("chimera_kit.export",text="Export GLB",icon="EXPORT").format="GLB"
        row.operator("chimera_kit.export",text="Export FBX",icon="EXPORT").format="FBX"
        layout.operator("chimera_kit.animation_export",text="Bake independent skeleton",icon="ARMATURE_DATA")
        row=layout.row(align=True)
        row.operator("chimera_kit.validate",icon="CHECKMARK")
        row.operator("chimera_kit.report",text="Manifest",icon="TEXT")

class CS_PT_retarget(CSPanel,bpy.types.Panel):
    bl_idname="CS_PT_retarget"
    bl_label="Retarget, Mixamo & CloudRig"
    tab="RETARGET"
    bl_order=1
    bl_parent_id="CS_PT_studio"
    def draw(self,context):
        layout=self.layout
        p=context.scene.cs_settings
        layout.operator("chimera_kit.import_mixamo",icon="IMPORT")
        col=layout.column(align=True)
        row=col.row(align=True)
        row.prop(p,"rt_source")
        row.operator("chimera_kit.retarget_pick",text="",icon="EYEDROPPER").role="SOURCE"
        row=col.row(align=True)
        row.prop(p,"rt_target")
        row.operator("chimera_kit.retarget_pick",text="",icon="EYEDROPPER").role="TARGET"
        if p.rt_source_kind:
            layout.label(text=p.rt_source_kind+"  →  "+p.rt_target_kind,icon="FORWARD")
        ready=bool(p.rt_source and p.rt_target and p.rt_source!=p.rt_target)
        row=layout.row()
        row.enabled=ready
        row.operator("chimera_kit.retarget_automap",icon="BONE_DATA")
        if p.rt_items:
            mapped=sum(1 for item in p.rt_items if item.source and item.target)
            layout.prop(p,"rt_show_map",text=f"Bone map · {mapped} of {len(p.rt_items)} paired",
                        icon="TRIA_DOWN" if p.rt_show_map else "TRIA_RIGHT",emboss=False)
            if p.rt_show_map and ready:
                box=layout.box()
                header=box.row()
                header.label(text="")
                header.label(text="From")
                header.label(text="To")
                fingers=("thumb","index","middle","ring","pinky")
                for item in p.rt_items:
                    if item.slot.startswith(fingers):
                        continue
                    row=box.row(align=True)
                    row.label(text=item.label)
                    if item.kind in {"IK_FOOT","POLE"}:
                        row.label(text=item.source or "—")
                    else:
                        row.prop_search(item,"source",p.rt_source.data,"bones",text="")
                    row.prop_search(item,"target",p.rt_target.data,"bones",text="")
                if any(item.slot.startswith(fingers) for item in p.rt_items):
                    box.prop(p,"rt_show_fingers",icon="TRIA_DOWN" if p.rt_show_fingers else "TRIA_RIGHT",emboss=False)
                    if p.rt_show_fingers:
                        for item in p.rt_items:
                            if not item.slot.startswith(fingers):
                                continue
                            row=box.row(align=True)
                            row.label(text=item.label)
                            row.prop_search(item,"source",p.rt_source.data,"bones",text="")
                            row.prop_search(item,"target",p.rt_target.data,"bones",text="")
                row=box.row(align=True)
                row.operator("chimera_kit.retarget_map_file",text="Save map").operation="SAVE"
                row.operator("chimera_kit.retarget_map_file",text="Load map").operation="LOAD"
        col=layout.column(align=True)
        col.prop(p,"rt_use_source_range")
        if not p.rt_use_source_range:
            row=col.row(align=True)
            row.prop(p,"rt_frame_start")
            row.prop(p,"rt_frame_end")
        col=layout.column(align=True)
        col.prop(p,"rt_leg_mode")
        col.prop(p,"rt_align_rest")
        col.prop(p,"rt_in_place")
        col.prop(p,"rt_height_offset")
        row=layout.row()
        row.scale_y=1.4
        row.enabled=ready
        row.operator("chimera_kit.retarget_run",icon="ACTION")
        layout.label(text="Layers and footsteps are included as played.",icon="INFO")

CLASSES=(CS_PT_studio,CS_PT_build,CS_PT_modules,CS_PT_motion,CS_PT_tuning,CS_PT_limbs,CS_PT_layers,CS_PT_pose,CS_PT_skin,CS_PT_files,CS_PT_retarget)
