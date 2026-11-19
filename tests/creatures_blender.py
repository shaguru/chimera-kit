"""Run with Blender --background --factory-startup --python-exit-code 1 --python tests/creatures_blender.py."""
import json
from pathlib import Path
import sys
import bpy
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import chimera_kit as cs
from chimera_kit import rig, motion
cs.register()
scene=bpy.context.scene
p=scene.cs_settings
def check(condition,message):
    if not condition: raise AssertionError(message)
def build(species,**options):
    p.species=species
    for key,value in options.items(): setattr(p,key,value)
    arm=rig.build(bpy.context,p)
    check(not rig.validate(arm),species+": validation")
    return arm,json.loads(arm["cs_limbs"])
def head(arm,name): return arm.data.bones[name].head_local

# Quadrupeds: front legs fold at a backward elbow, hind legs at a backward hock. Forward is -Y.
for species in ("HORSE","PANTHER","GNOU","DRAGON","CENTAUR"):
    arm,limbs=build(species)
    check(len(limbs)==4,f"{species}: {len(limbs)} legs")
    front,hind="leg.01.L","leg.02.L"
    check(head(arm,front+".lower").y>head(arm,front+".upper").y+.03,species+": front elbow does not point back")
    check(head(arm,hind+".lower").y<head(arm,hind+".upper").y-.03,species+": hind stifle does not point forward")
    check(head(arm,hind+".foot").y>head(arm,hind+".lower").y+.1,species+": hock does not point back")
    check(head(arm,front+".foot").z>.12 and "toe.01.L" in arm.data.bones,species+": not standing on a raised ankle")
# Sprawlers: feet well outside the body, belly low, diagonal gait and a bending spine.
for species in ("LIZARD","GECKO"):
    arm,limbs=build(species)
    check(p.gait=="TROT" and p.spine_bend>.3,species+": reptile gait defaults")
    check(head(arm,"pelvis").z<.35,species+": body too high")
    check(head(arm,"leg.01.L.foot").x>head(arm,"leg.01.L.upper").x+.2,species+": legs do not sprawl")
lizard,_=build("LIZARD"); gecko,_=build("GECKO")
tail=lambda arm:max(b.tail_local.y for b in arm.data.bones if b.name.startswith("tail."))-min(b.head_local.y for b in arm.data.bones if b.name.startswith("tail."))
check(tail(lizard)>tail(gecko)*1.8,"lizard tail is not clearly longer than the gecko's")
# Theropods and the alien stand on two legs.
allosaur,limbs=build("ALLOSAUR"); check(len(limbs)==2,"allosaur legs")
rex,limbs=build("TREX"); check(len(limbs)==2,"t-rex legs")
length=lambda arm,name:arm.data.bones[name].length
check(length(allosaur,"arm.L")>length(rex,"arm.L")*2,"allosaur arms should be much longer than the t-rex's")
check(length(rex,"head")>length(allosaur,"head")*1.2,"t-rex head should be larger")
check("claw.3.L" in allosaur.data.bones and "claw.3.L" not in rex.data.bones and "claw.2.L" in rex.data.bones,"claw counts")
check(abs(allosaur.data.bones["spine.02"].tail_local.z-allosaur.data.bones["spine.02"].head_local.z)<.1,"theropod spine is not level")
alien,limbs=build("ALIEN")
check(len(limbs)==2 and p.antennae and "antenna.03.L" in alien.data.bones and "arm.L" in alien.data.bones,"alien is not an antennaed biped")
check(p.gait=="WALK" and p.spine_bend<.2,"gait defaults not restored after a reptile")
# Accessories on any creature, with follow-through motion.
biped,_=build("BIPED",wings=True,antennae=True,ponytail=True,tail_links=4)
for name in ("wing.L","wingtip.R","wingfinger.3.L","antenna.03.R","ponytail.04","tail.04"):
    check(name in biped.data.bones,"accessory bone missing: "+name)
check(any(o.name.endswith("wing membrane") for o in biped.children),"wing membrane missing")
action=motion.generate(bpy.context,biped,p)
paths={fc.data_path for fc in motion.curves(action)}
for name in ("antenna.02.L","ponytail.03","wing.L","wingtip.L","tail.02"):
    check(any(f'["{name}"]' in path for path in paths),name+" is not animated")
def swing(name):
    values=[]
    for frame in range(1,p.cycle_frames+1):
        scene.frame_set(frame)
        values.append(biped.pose.bones[name].tail.copy())
    return max((a-values[0]).length for a in values)
check(swing("antenna.03.L")>.01 and swing("ponytail.04")>.02,"follow-through does not move")
plain,_=build("HORSE",wings=False,antennae=False,ponytail=False)
check(not any(b.name.startswith(("wing","antenna","ponytail")) for b in plain.data.bones),"accessories leaked onto a plain horse")
# Foot roll: toe dips below the ankle during the swing, flat in stance.
p.foot_roll=.5
action=motion.generate(bpy.context,biped,p)
control=biped.pose.bones["CTRL-leg.01.L"]
dips=[]
for frame in range(1,p.cycle_frames+1):
    scene.frame_set(frame)
    dips.append(control.head.z-control.tail.z)
check(max(dips)-min(dips)>.03,"foot does not roll during the swing")
print("CHIMERA_KIT_CREATURES_PASSED")
cs.unregister()
