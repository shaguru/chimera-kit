"""Chimera Kit: procedural creature rigs and locomotion for Blender."""

bl_info = {
    "name": "Chimera Kit", "author": "Chimera Kit contributors",
    "version": (1, 3, 0), "blender": (4, 2, 0), "category": "Rigging",
    "location": "3D View > Sidebar > Chimera Kit",
    "description": "Build creature rigs, pose with IK, generate gaits and bind meshes",
}

import bpy
from bpy.props import (BoolProperty, CollectionProperty, EnumProperty, FloatProperty, IntProperty,
                       PointerProperty, StringProperty)
from . import rig, motion, operators, ui

PRESETS = [
    ("BIPED", "Biped", "Box-figure biped with clavicles, fingers and toes, in the 3ds Max tradition"),
    ("HUMAN", "Human", "Upright biped with arms"),
    ("APE", "Ape", "Upright primate with arms"),
    ("ALIEN", "Alien", "Slender biped with antennae"),
    ("ANGEL", "Angel", "Winged biped"),
    ("GORILLA", "Gorilla", "Knuckle-walking primate: long arms in front, short legs behind, deep chest"),
    ("CENTAUR", "Centaur", "Four-legged body with an upright torso and arms"),
    ("MECH", "Mech · Classic", "Mechanical biped with compact spine"),
    ("MECH_TROOPER", "Mech · Trooper", "Armoured humanoid mech: broad shoulders, heavy forearms and flared lower legs"),
    ("MECH_FLYER", "Mech · Flyer", "Slim humanoid mech with swept back wings and thruster legs"),
    ("MECH_POD", "Mech · Walker pod", "Cockpit pod on two reverse-jointed legs with side guns"),
    ("HORSE", "Horse", "Long-necked quadruped"),
    ("GNOU", "Gnou", "Heavy quadruped"),
    ("GIRAFFE", "Giraffe", "Tall quadruped with a very long, many-jointed neck"),
    ("PANTHER", "Panther", "Low quadruped with a long tail"),
    ("DRAGON", "Dragon", "Quadruped with articulated wings"),
    ("LIZARD", "Lizard", "Long sprawling body with a whip tail"),
    ("GECKO", "Gecko", "Short sprawling body, big head, fat tail and wide toe pads"),
    ("FROG", "Frog", "Squat body, wide head, long folded hind legs and eyes on top"),
    ("SNAKE", "Snake", "Legless: a long even body that slithers in travelling waves"),
    ("ALLOSAUR", "Allosaur", "Theropod dinosaur: level body, long balancing tail, three-clawed arms"),
    ("TREX", "T-Rex", "Heavy theropod: massive head, tiny two-clawed arms"),
    ("BRONTO", "Brontosaurus", "Sauropod: four pillar legs, very long neck and tail, small head"),
    ("BIRD", "Bird", "Small perching bird: short legs, beak, fan tail and wings"),
    ("EAGLE", "Eagle", "Raptor with broad wings and a hooked beak"),
    ("OSTRICH", "Ostrich", "Tall running bird: long legs and neck, small wings"),
    ("PENGUIN", "Penguin", "Upright waddler with flippers and a beak"),
    ("FISH", "Fish", "Deep-bodied fish that swims with a side-to-side tail beat"),
    ("SHARK", "Shark", "Long predator fish with a tall dorsal fin"),
    ("DOLPHIN", "Dolphin", "Small cetacean with a beak: swims with an up-and-down fluke beat"),
    ("WHALE", "Whale", "Huge-headed cetacean with broad flukes"),
    ("TADPOLE", "Tadpole", "Round body with a thin finned tail"),
    ("WORM", "Worm", "Short legless body that inches along"),
    ("SPIDER", "Spider", "Radial creature with eight legs"),
    ("CRAB", "Crab", "Radial creature with ten legs"),
    ("CENTIPEDE", "Centipede", "Segmented body with many leg pairs"),
]
GROUPS = [("Humanoids & primates", ("BIPED","HUMAN","APE","GORILLA","ALIEN","ANGEL","CENTAUR")),
          ("Mechs", ("MECH","MECH_TROOPER","MECH_FLYER","MECH_POD")),
          ("Four legs", ("HORSE","GNOU","GIRAFFE","PANTHER","DRAGON")),
          ("Reptiles, amphibians & dinosaurs", ("LIZARD","GECKO","FROG","SNAKE","ALLOSAUR","TREX","BRONTO")),
          ("Birds", ("BIRD","EAGLE","OSTRICH","PENGUIN")),
          ("Swimmers", ("FISH","SHARK","DOLPHIN","WHALE","TADPOLE")),
          ("Bugs & crawlers", ("SPIDER","CRAB","CENTIPEDE","WORM"))]
_BY_ID = {item[0]: item for item in PRESETS}
# Headed columns in the preset menu; a blank identifier is a column title.
PRESET_ITEMS = [entry for title, members in GROUPS for entry in [("", title, "")] + [_BY_ID[m] for m in members]]
SWIMMERS = {"FISH","SHARK","DOLPHIN","WHALE","TADPOLE","SNAKE","WORM"}

def preset_changed(self, context):
    if motion.SYNCING:
        return   # sliders are being loaded from an existing creature, not reset
    species = self.species
    # leg pairs, spine links, tail links, body length, leg length
    defaults = {
        "BIPED": (1, 3, 0, 1.0, 1.0), "MECH_TROOPER": (1, 2, 0, 1.0, 1.0), "MECH_FLYER": (1, 2, 0, 1.0, 1.05),
        "MECH_POD": (1, 1, 0, 1.0, 1.0),
        "HUMAN": (1, 2, 0, 1.0, 1.0), "APE": (1, 3, 0, 1.1, 0.7),
        "MECH": (1, 1, 0, 1.1, 1.0), "HORSE": (2, 4, 5, 1.35, 1.0),
        "GNOU": (2, 4, 1, 1.35, 1.0), "GORILLA": (2, 3, 0, 0.8, 0.95), "GIRAFFE": (2, 3, 3, 1.05, 1.55), "PANTHER": (2, 4, 9, 1.55, 0.8),
        "LIZARD": (2, 6, 9, 1.5, 1.0), "GECKO": (2, 4, 4, 1.0, 1.0), "ALIEN": (1, 3, 0, 1.0, 1.05),
        "TREX": (1, 4, 10, 1.0, 1.0), "BRONTO": (2, 5, 14, 1.7, 1.0),
        "ALLOSAUR": (1, 4, 10, 1.0, 1.0), "CENTAUR": (2, 4, 5, 1.35, 1.0), "DRAGON": (2, 5, 9, 1.35, 1.0),
        "ANGEL": (1, 3, 0, 1.0, 1.0),
        "BIRD": (1, 2, 2, 1.0, 1.0), "EAGLE": (1, 3, 3, 1.0, 1.0), "OSTRICH": (1, 3, 2, 1.0, 1.0),
        "PENGUIN": (1, 3, 0, 1.0, 0.5),
        "FISH": (1, 3, 4, 1.0, 1.0), "SHARK": (1, 5, 6, 1.0, 1.0), "DOLPHIN": (1, 4, 5, 1.0, 1.0),
        "WHALE": (1, 5, 5, 1.0, 1.0), "TADPOLE": (1, 2, 8, 1.0, 1.0), "SNAKE": (1, 10, 14, 1.0, 1.0),
        "WORM": (1, 6, 6, 1.0, 1.0), "FROG": (2, 2, 0, 0.75, 1.0),
        "SPIDER": (4, 2, 0, 1.0, 0.75), "CRAB": (5, 1, 2, 1.0, 0.75),
        "CENTIPEDE": (7, 7, 2, 2.0, 0.7),
    }[species]
    self.leg_pairs, self.spine_links, self.tail_links, self.body_length, self.leg_length = defaults
    self.body_width = {"APE":1.4,"MECH":1.5,"CRAB":1.7,"GNOU":1.3,"LIZARD":0.9,"GECKO":1.25,"ALIEN":0.8,
                       "PENGUIN":1.5,"MECH_TROOPER":1.15,"BRONTO":1.6,"FROG":1.5,"GORILLA":1.55}.get(species,1.0)
    self.arm_length = {"APE":1.5,"ALIEN":1.3,"PENGUIN":0.9}.get(species,1.0)
    self.head_size = {"APE":0.75,"ALIEN":1.2,"GECKO":1.15,"BRONTO":0.7}.get(species,1.0)
    self.neck_length = {"GIRAFFE":3.4,"BRONTO":5.0}.get(species,1.0)
    self.neck_links = {"GIRAFFE":5,"OSTRICH":3,"BRONTO":9}.get(species,1)
    # Animals with a mouth worth opening get a hinged jaw; beaks, visors and box heads do not.
    self.jaw = species in {"APE","ALIEN","CENTAUR","HORSE","GNOU","GIRAFFE","PANTHER","DRAGON","LIZARD","GECKO",
                           "ALLOSAUR","TREX","BRONTO","FISH","SHARK","WHALE","FROG"}
    self.antenna_length, self.antenna_links = 1.0, 3
    self.tail_length, self.wing_span, self.wing_links = 1.0, 1.0, 2
    self.eyes, self.eye_size = species in {"FROG","TADPOLE"}, {"FROG":1.5,"TADPOLE":1.2}.get(species,1.0)
    self.eye_spacing, self.eye_height, self.eye_forward = 0.48, 0.0, 0.45
    # Front and hind leg heights: a gorilla and a giraffe stand taller in front.
    self.front_legs, self.hind_legs = {"GORILLA":(1.22,0.80),"GIRAFFE":(1.10,0.92)}.get(species,(1.0,1.0))
    # Trunk profile: animals carry a deep chest, a tucked waist and solid hips.
    animals = {"HORSE","GNOU","GIRAFFE","PANTHER","DRAGON","CENTAUR","LIZARD","GECKO","ALLOSAUR","TREX","BRONTO",
               "BIRD","EAGLE","OSTRICH"}
    people = {"HUMAN","APE","ALIEN","ANGEL","BIPED"}
    self.chest_size, self.belly_size, self.hip_size = ((1.5,1.15,0.9) if species=="GORILLA" else (1.15,0.85,1.08) if species in animals else
        (1.08,0.92,1.0) if species in people else (1.0,1.0,1.0))
    self.wings = species in {"DRAGON","ANGEL","BIRD","EAGLE","OSTRICH","MECH_FLYER"}
    self.antennae = species=="ALIEN"
    self.ponytail = False
    self.fingers = 0 if species.startswith("MECH_") else 5
    # Motion defaults that suit the body plan. Sprawling reptiles walk on
    # diagonal pairs with a strongly bending spine; fish beat the tail side
    # to side; cetaceans beat it up and down.
    tuned = dict(gait="WALK", spine_bend=0.10, tail_swing=0.20, body_height=-0.08, spine_flex=0.05,
                  tail_lift=0.0, spine_twist=0.10, body_twist=0.06, sway=0.025, head_bob=0.04,
                  arm_swing=0.22, wing_flap=0.45, wing_style="FLAP", wing_frequency=1.0, wing_fold=0.0,
                  body_roll=0.015, body_wave=0.0, bounce=0.025)
    if species in {"LIZARD","GECKO"}:
        tuned.update(gait="TROT", spine_bend=0.5, tail_swing=0.5, body_height=-0.02)
    elif species=="SNAKE":
        # Each bend travels from head to tail: about one and a half waves along the body.
        tuned.update(bounce=0.0, spine_bend=1.3, body_wave=0.75, tail_swing=0.75, tail_stiffness=0.0, body_height=0.0, spine_flex=0.0,
                     spine_twist=0.0, body_twist=0.0, sway=0.0, head_bob=0.0, body_roll=0.0)
    elif species=="WORM":
        # An inchworm arches its back in a wave instead of bending sideways.
        tuned.update(bounce=0.0, spine_bend=0.06, spine_flex=0.9, body_wave=0.0, tail_swing=0.03, tail_lift=0.0, tail_stiffness=0.0,
                     body_height=0.0, spine_twist=0.0, body_twist=0.0, sway=0.0, head_bob=0.0, body_roll=0.0)
    elif species=="FROG":
        tuned.update(gait="BOUND", spine_bend=0.08, body_height=-0.02, spine_flex=0.12)
    elif species in {"FISH","SHARK","TADPOLE"}:
        tuned.update(spine_bend=0.28, tail_swing=0.45, body_height=0.0, spine_flex=0.0, spine_twist=0.0,
                      body_twist=0.0, sway=0.01, head_bob=0.0, body_roll=0.0)
    elif species in {"DOLPHIN","WHALE"}:
        tuned.update(spine_bend=0.0, tail_swing=0.0, body_height=0.0, spine_flex=0.16, tail_lift=0.14,
                      spine_twist=0.0, body_twist=0.0, sway=0.0, head_bob=0.03, body_roll=0.0)
    elif species=="PENGUIN":
        tuned.update(sway=0.06, body_roll=0.10, arm_swing=0.08, spine_twist=0.04)
    elif species in {"BIRD","EAGLE","OSTRICH"}:
        # A gentle beat while walking; Folded is one click away in Motion tuning.
        tuned.update(head_bob=0.12, wing_flap=0.3)
    elif species.startswith("MECH"):
        tuned.update(wing_style="GLIDE", spine_bend=0.03, spine_flex=0.02, head_bob=0.0, sway=0.035)
    for key, value in tuned.items():
        setattr(self, key, value)

def rig_filter(self, obj):
    return obj.type == "ARMATURE" and bool(obj.get("cs_rig"))

class CSLayerSettings(bpy.types.PropertyGroup):
    strip_name: StringProperty()
    label: StringProperty(name="Layer name",default="Layer",update=operators.layer_settings_changed)
    weight: FloatProperty(name="Weight",default=1,min=0,max=1,subtype="FACTOR",update=operators.layer_settings_changed)
    fade_in: FloatProperty(name="Fade in",default=0,min=0,max=10000,update=operators.layer_settings_changed)
    fade_out: FloatProperty(name="Fade out",default=0,min=0,max=10000,update=operators.layer_settings_changed)

class CSRetargetItem(bpy.types.PropertyGroup):
    slot: StringProperty()
    label: StringProperty()
    kind: StringProperty(default="ROT")
    source: StringProperty(name="Source bone",description="Bone on the source armature that provides the motion")
    target: StringProperty(name="Target bone",description="Bone or control on the target armature that receives keys")
    ref: StringProperty(name="Reference bone",description="Target skeleton bone used for rest-pose geometry")

def armature_filter(self, obj):
    return obj.type == "ARMATURE"

def retarget_pair_changed(self, context):
    self.rt_items.clear()
    self.rt_source_kind = self.rt_target_kind = ""

class CSSettings(bpy.types.PropertyGroup):
    species: EnumProperty(name="Creature", items=PRESET_ITEMS, default="BIPED", update=preset_changed)
    mannequin_style: EnumProperty(name="Mannequin", items=[
        ("BOX","Boxes","Flat-shaded tapered boxes; left side blue, right side green"),
        ("ROUND","Rounded","Smooth capsules and ellipsoids")], default="BOX")
    wings: BoolProperty(name="Wings", default=False, description="Add a pair of articulated wings at the shoulders")
    antennae: BoolProperty(name="Antennae", default=False, description="Add two antennae with follow-through motion")
    ponytail: BoolProperty(name="Ponytail", default=False, description="Add a ponytail with follow-through motion")
    secondary: FloatProperty(name="Follow-through", default=0.3, min=0, max=1.2, subtype="ANGLE",
        description="Lagging sway of antennae and ponytail")
    foot_roll: FloatProperty(name="Foot roll", default=0.35, min=0, max=1.2, subtype="ANGLE",
        description="Tip the foot toe-down as it leaves the ground")
    fingers: IntProperty(name="Fingers", default=5, min=0, max=5, description="Biped fingers per hand")
    finger_links: IntProperty(name="Finger links", default=3, min=1, max=3)
    character_name: StringProperty(name="Name", default="")
    size: FloatProperty(name="Size", default=1.8, min=0.1, max=100, soft_max=10, subtype="DISTANCE")
    body_length: FloatProperty(name="Body length", default=1.0, min=0.2, max=40, soft_max=12)
    body_width: FloatProperty(name="Body width", default=1.0, min=0.2, max=10, soft_max=4)
    leg_length: FloatProperty(name="Leg length", default=1.0, min=0.2, max=10, soft_max=5)
    arm_length: FloatProperty(name="Arm length", default=1.0, min=0.2, max=10, soft_max=5)
    head_size: FloatProperty(name="Head size", default=1.0, min=0.2, max=10, soft_max=4)
    neck_length: FloatProperty(name="Neck length", default=1.0, min=0.2, max=80, soft_max=20,
        description="1 is the preset's own neck; a giraffe is about 3.4")
    neck_links: IntProperty(name="Neck links", default=1, min=1, max=30, soft_max=12)
    live_build: BoolProperty(name="Live body", default=True,
        description="Rebuild the active creature as you change its body sliders and link counts")
    module_type: EnumProperty(name="Add structure", items=[("HUB","Hub","Add a new body hub"),
        ("SPINE","Spine + hub","Build a chain ending in a hub"),("TAIL","Tail","Add an articulated tail"),
        ("LEGS","Leg pair + IK","Append a pair of walking legs with foot and pole controls"),
        ("ARMS","Arm pair","Append two FK arms")])
    module_links: IntProperty(name="Links",default=4,min=1,max=20)
    module_length: FloatProperty(name="Length / size",default=.45,min=.05,max=1.5)
    module_parent: StringProperty(name="Parent bone",default="pelvis",
        description="Exact parent bone name on the active rig")
    leg_pairs: IntProperty(name="Leg pairs", default=1, min=1, max=40, soft_max=12)
    spine_links: IntProperty(name="Spine links", default=3, min=1, max=60, soft_max=16)
    tail_links: IntProperty(name="Tail links", default=0, min=0, max=80, soft_max=24)
    mannequin: BoolProperty(name="Preview mannequin", default=True)
    show_rig: BoolProperty(name="Show skeleton", default=True)
    ui_tab: EnumProperty(name="Workflow", items=[
        ("BUILD","Build","Choose a creature, build it, fit it and skin it","COLLECTION_COLOR_05",0),
        ("ANIMATE","Animate","Walks, idles, jumps and strikes, with live tuning and footsteps","COLLECTION_COLOR_04",1),
        ("LAYERS","Layers","Stack and blend animation layers","COLLECTION_COLOR_03",2),
        ("RETARGET","Retarget","Mixamo import, CloudRig and skeleton-to-skeleton","COLLECTION_COLOR_06",3),
        ("EXPORT","Export","Recipes, game export and validation","COLLECTION_COLOR_02",4)], default="BUILD")
    motion_type: EnumProperty(name="Cycle", items=[
        ("WALK","Walk","Locomotion with the chosen gait; legless creatures swim","PLAY",0),
        ("IDLE","Idle","Standing and breathing with planted feet","PAUSE",1),
        ("JUMP","Jump","Crouch, push off, fly, land and recover","TRIA_UP",2),
        ("PUNCH","Punch","Wind up and strike with one arm","FORWARD",3),
        ("KICK","Kick","Wind up and strike with one leg","FRAME_NEXT",4),
        ("FLY","Fly","Airborne with the legs tucked: flap, hover, or glide to soar","SORT_DESC",5)], default="WALK")
    fly_height: FloatProperty(name="Flight height / leg", default=1.5, min=0.0, max=20, soft_max=6)
    jump_height: FloatProperty(name="Jump height / leg", default=0.6, min=0.0, max=3.0)
    jump_distance: FloatProperty(name="Jump distance / leg", default=1.2, min=0.0, max=6.0,
        description="Used when Travel forward is on")
    jump_crouch: FloatProperty(name="Crouch depth / leg", default=0.22, min=0.0, max=0.6)
    strike_side: EnumProperty(name="Side", items=[("L","Left",""),("R","Right",""),
        ("ALT","Alternate","Left on one cycle, right on the next")], default="R")
    strike_height: FloatProperty(name="Strike height", default=1.0, min=0.2, max=1.6,
        description="1 is a shoulder-height punch or a hip-height kick")
    body_lean: FloatProperty(name="Forward lean", default=0.0, min=-0.5, max=0.8, subtype="ANGLE",
        description="Constant forward lean of the body: more for a run")
    export_all_cycles: BoolProperty(name="All generated cycles", default=True,
        description="Export every cycle generated for this creature as its own animation clip")
    gait: EnumProperty(name="Gait", items=[("WALK", "Walk", "Sequential footfalls"),
        ("TROT", "Trot / tripod", "Alternating diagonal groups"),
        ("PACE", "Pace", "Same side together"), ("BOUND", "Bound", "Front and rear groups")])
    cycle_frames: IntProperty(name="Frames / cycle", default=32, min=8, max=240)
    cycles: IntProperty(name="Cycles", default=4, min=1, max=30)
    start_frame: IntProperty(name="First frame", default=1, min=1, max=100000)
    stride: FloatProperty(name="Max stride / leg", default=0.52, min=0.05, max=1.1,
        description="Maximum CAT-style stride expressed as a fraction of average leg reach")
    lift: FloatProperty(name="Foot lift / leg length", default=0.15, min=0.01, max=0.45)
    stance: FloatProperty(name="Ground contact", default=0.65, min=0.5, max=0.85, subtype="FACTOR")
    foot_planting: BoolProperty(name="Plant feet", default=True,
        description="Keep stance targets fixed against the ground while the body travels")
    exaggeration: FloatProperty(name="Exaggeration", default=1.0, min=0.0, max=3.0,
        description="Multiply body, spine, tail, head, arm and wing motion; foot stride stays unchanged")
    body_height: FloatProperty(name="Body height / leg", default=-0.08, min=-0.4, max=0.15)
    bounce: FloatProperty(name="Body bounce", default=0.025, min=0, max=0.25)
    bounce_frequency: IntProperty(name="Bounce frequency", default=2, min=1, max=4)
    sway: FloatProperty(name="Side sway", default=0.025, min=0, max=0.25)
    body_roll: FloatProperty(name="Body roll", default=0.015, min=0, max=0.65, subtype="ANGLE")
    body_pitch: FloatProperty(name="Body pitch", default=0.0, min=0, max=0.65, subtype="ANGLE")
    body_twist: FloatProperty(name="Hip twist", default=0.06, min=0, max=0.65, subtype="ANGLE")
    motion_phase: FloatProperty(name="Body phase", default=0.0, min=-1.0, max=1.0)
    tail_swing: FloatProperty(name="Tail swing", default=0.20, min=0, max=1.2, subtype="ANGLE")
    tail_lift: FloatProperty(name="Tail lift", default=0.0, min=0, max=0.6, subtype="ANGLE")
    tail_frequency: IntProperty(name="Tail frequency", default=1, min=1, max=4)
    tail_stiffness: FloatProperty(name="Tail stiffness", default=0.25, min=0.0, max=1.0, subtype="FACTOR")
    tail_phase: FloatProperty(name="Tail phase", default=0.0, min=-1.0, max=1.0, subtype="FACTOR")
    spine_bend: FloatProperty(name="Spine side bend", default=0.10, min=0, max=0.8, subtype="ANGLE",
        description="Side-to-side bend of the whole trunk, shared along its links")
    spine_twist: FloatProperty(name="Spine twist", default=0.10, min=0, max=0.8, subtype="ANGLE",
        description="Counter-rotation of the chest against the hips")
    spine_flex: FloatProperty(name="Spine flex", default=0.05, min=0, max=0.8, subtype="ANGLE",
        description="Forward and back flex of the trunk with each step")
    head_bob: FloatProperty(name="Head bob", default=0.04, min=0, max=0.6, subtype="ANGLE")
    arm_swing: FloatProperty(name="Arm swing", default=0.22, min=0, max=1.2, subtype="ANGLE")
    wing_flap: FloatProperty(name="Wing beat", default=0.45, min=0, max=1.6, subtype="ANGLE",
        description="How far the wings travel on each beat")
    wing_style: EnumProperty(name="Wing motion", items=[
        ("FLAP","Flap","Steady up-and-down beat with the outer wing trailing"),
        ("GLIDE","Glide","Wings held out and slightly raised, with a small tremble"),
        ("HOVER","Hover","Fast beats that also sweep forward and back, like a hummingbird"),
        ("FLUTTER","Flutter","Small, very quick beats, like an insect or a nervous bird"),
        ("FOLDED","Folded","Wings tucked against the body, shifting a little with each step")], default="FLAP")
    wing_frequency: FloatProperty(name="Beats per cycle", default=1.0, min=0.25, max=16, soft_max=8)
    wing_fold: FloatProperty(name="Wing fold", default=0.0, min=0, max=1, subtype="FACTOR",
        description="How far the wings are tucked in: 0 is fully spread, 1 is folded against the body")
    tail_length: FloatProperty(name="Tail length", default=1.0, min=0.1, max=40, soft_max=8,
        description="1 is the preset's own tail")
    wing_span: FloatProperty(name="Wingspan", default=1.0, min=0.1, max=20, soft_max=5)
    wing_links: IntProperty(name="Wing joints", default=2, min=2, max=12, soft_max=6,
        description="Bones along the leading edge. More joints let the wing ripple like a membrane")
    eyes: BoolProperty(name="Eyeballs", default=False, description="Add two cartoon eyeballs on stalks that wobble as the creature moves")
    eye_size: FloatProperty(name="Eye size", default=1.0, min=0.2, max=10, soft_max=4)
    eye_spacing: FloatProperty(name="Eye spacing", default=0.48, min=0, max=4, soft_max=2,
        description="0 is together, 1 is at the edges of the head, more is out past it")
    eye_height: FloatProperty(name="Eye height", default=0.0, min=-1, max=10, soft_max=4,
        description="0 sits on top of the head. Higher raises the stalks; below 0 slides the eyes down the sides of the head")
    eye_forward: FloatProperty(name="Eye forward", default=0.45, min=-1, max=1.5,
        description="0 is the middle of the head, 1 is its front edge")
    front_legs: FloatProperty(name="Front legs", default=1.0, min=0.2, max=5, soft_max=2.5,
        description="Height of the front legs and shoulders relative to the preset")
    hind_legs: FloatProperty(name="Hind legs", default=1.0, min=0.2, max=5, soft_max=2.5,
        description="Height of the hind legs and hips relative to the preset")
    chest_size: FloatProperty(name="Chest", default=1.0, min=0.2, max=5, soft_max=2.5,
        description="Thickness of the trunk at the chest")
    belly_size: FloatProperty(name="Belly", default=1.0, min=0.2, max=5, soft_max=2.5,
        description="Thickness of the trunk at the waist")
    hip_size: FloatProperty(name="Hips", default=1.0, min=0.2, max=5, soft_max=2.5,
        description="Thickness of the trunk at the hips")
    eye_bounce: FloatProperty(name="Eye follow-through", default=0.25, min=0, max=1.5, subtype="ANGLE",
        description="0 is stiff. Higher values make the eyeballs bounce further and lag further behind the head")
    body_wave: FloatProperty(name="Body wave", default=0.0, min=0, max=4,
        description="Waves travelling along the trunk: 0 bends the body as one, 1 fits a full wave between hips and head")
    jaw: BoolProperty(name="Jaw", default=False, description="Add a hinged lower jaw that can open and close")
    jaw_open: FloatProperty(name="Jaw opening", default=0.3, min=0, max=1.4, subtype="ANGLE")
    jaw_chance: FloatProperty(name="Jaw how often", default=0.5, min=0, max=1, subtype="FACTOR",
        description="Share of cycles in which the mouth opens: 1 is every cycle, 0 is never")
    jaw_rate: IntProperty(name="Jaw openings per cycle", default=1, min=1, max=8)
    antenna_length: FloatProperty(name="Antenna length", default=1.0, min=0.1, max=40, soft_max=8)
    antenna_links: IntProperty(name="Antenna links", default=3, min=1, max=40, soft_max=12)
    layer_name: StringProperty(name="Layer name", default="Walk layer")
    layer_weight: FloatProperty(name="Layer weight", default=1.0, min=0.0, max=1.0, subtype="FACTOR")
    layer_blend: EnumProperty(name="Layer blend", items=[("REPLACE","Replace","Replace lower layers"),
        ("ADD","Add","Add transforms to lower layers"), ("COMBINE","Combine","Combine with lower layers")], default="REPLACE")
    layer_blend_in: FloatProperty(name="Blend in", default=0, min=0, max=240)
    layer_blend_out: FloatProperty(name="Blend out", default=0, min=0, max=240)
    limb_choice: EnumProperty(name="Limb", items=operators.limb_items)
    use_footprints: BoolProperty(name="Use edited footprints", default=False,
        description="Use the editable footprint objects to place traveling stance feet")
    tuning_preset: EnumProperty(name="Motion style", items=[("NEUTRAL","Neutral","Subtle natural motion"),
        ("SNEAK","Sneak","Low body and long planted stance"),
        ("HEAVY","Heavy","Weighted bounce and slow pace"),
        ("CARTOON","Cartoon","Exaggerated sway, tail and body motion"),
        ("RUN","Run","Fast cycle, long stride, high lift and a forward lean")])
    motion_scope: EnumProperty(name="Channels", items=[("ALL","Full creature","All generated motion"),
        ("BODY","Body + spine","Body and spine transforms"),
        ("TAIL","Tail only","Only tail transforms"),
        ("UPPER","Head, arms + wings","Only head, arm and wing transforms"),
        ("FEET","Root + feet","Root travel and foot IK targets")], default="ALL")
    live_update: BoolProperty(name="Live update", default=True,
        description="Rewrite the walk as you move any motion control, limb setting, footprint or path, while it plays")
    live_on_release: BoolProperty(name="On release", default=True,
        description="Update when the control stops moving instead of on every step of a drag")
    travel: BoolProperty(name="Travel forward", default=False,
        description="Move the root forward with planted stance feet; otherwise walk in place")
    path_object: PointerProperty(name="Follow curve", type=bpy.types.Object,
        poll=lambda self, obj: obj.type == "CURVE",
        description="Optional curve to follow during a traveling walk")
    active_rig: PointerProperty(name="Active creature", type=bpy.types.Object, poll=rig_filter)
    rt_source: PointerProperty(name="Motion from", type=bpy.types.Object, poll=armature_filter,
        update=retarget_pair_changed, description="Armature whose motion is copied: a creature, a Mixamo import or any skeleton")
    rt_target: PointerProperty(name="Apply to", type=bpy.types.Object, poll=armature_filter,
        update=retarget_pair_changed, description="Armature that receives keys: a creature, a CloudRig character or any skeleton")
    rt_items: CollectionProperty(type=CSRetargetItem)
    rt_source_kind: StringProperty()
    rt_target_kind: StringProperty()
    rt_show_map: BoolProperty(name="Show bone map", default=False)
    rt_show_fingers: BoolProperty(name="Fingers", default=False)
    rt_use_source_range: BoolProperty(name="Use source action range", default=True)
    rt_frame_start: IntProperty(name="Start", default=1)
    rt_frame_end: IntProperty(name="End", default=64)
    rt_align_rest: BoolProperty(name="Match rest poses", default=True,
        description="Correct for different rest poses, such as a T-pose source and an A-pose target")
    rt_in_place: BoolProperty(name="In place", default=False,
        description="Remove horizontal travel so the target walks on the spot")
    rt_leg_mode: EnumProperty(name="Legs", items=[
        ("BOTH","FK + IK","Key FK leg controls and IK feet, so either mode of the target rig plays the motion"),
        ("IK","IK feet only","Key IK foot and knee pole controls"),
        ("FK","FK only","Key FK leg rotations")], default="BOTH")
    rt_height_offset: FloatProperty(name="Hips offset", default=0.0, min=-2, max=2, subtype="DISTANCE",
        description="Raise or lower the retargeted hips")
    pose_name: StringProperty(name="Pose name", default="My pose")
    pose_choice: EnumProperty(name="Saved pose", items=operators.pose_items)
    io_path: StringProperty(name="File", subtype="FILE_PATH", default="//character.glb")
    status: StringProperty(default="Choose a creature and build a rig.")

CLASSES = (CSLayerSettings,CSRetargetItem,CSSettings) + operators.CLASSES + ui.CLASSES

def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.cs_settings = PointerProperty(type=CSSettings)
    bpy.types.Object.cs_layers = CollectionProperty(type=CSLayerSettings)
    motion.live_start()

def unregister():
    motion.live_stop()
    if hasattr(bpy.types.Object,"cs_layers"):
        del bpy.types.Object.cs_layers
    if hasattr(bpy.types.Scene, "cs_settings"):
        del bpy.types.Scene.cs_settings
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
