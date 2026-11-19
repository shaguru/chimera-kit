"""Choosing a preset builds the creature at once; the chooser forgets deleted creatures."""
from pathlib import Path
import sys
import bpy
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import chimera_kit as cs
from chimera_kit import rig, motion
cs.register()
p=bpy.context.scene.cs_settings
scene=bpy.context.scene

def creatures():
    return [o for o in scene.objects if o.get("cs_rig")]

def check(condition,message):
    if not condition: raise AssertionError(message)

# A preset builds right away.
check(not creatures(),"the scene should start empty")
check(bpy.ops.chimera_kit.choose_preset(species="DOG")=={"FINISHED"},"choosing a preset failed")
check(len(creatures())==1 and creatures()[0]["cs_species"]=="DOG","a preset should build its creature")
check(p.species=="DOG" and p.active_rig==creatures()[0],"the new creature should be the active one")

# An untouched creature is replaced by the next preset.
check(bpy.ops.chimera_kit.choose_preset(species="HORSE")=={"FINISHED"},"second preset failed")
check([o["cs_species"] for o in creatures()]==["HORSE"],"an untouched creature should be replaced, not kept")
check(not any(o.get("cs_rig") and o.get("cs_species")=="DOG" for o in bpy.data.objects),"the replaced creature should be gone from memory")

# One that has been worked on (animated) is hidden and kept.
horse=p.active_rig
motion.generate(bpy.context,horse,p)
check(bpy.ops.chimera_kit.choose_preset(species="CAT")=={"FINISHED"},"third preset failed")
names=sorted(o["cs_species"] for o in creatures())
check(names==["CAT","HORSE"],"an animated creature should be kept: "+str(names))
layer=bpy.context.view_layer.layer_collection.children[horse.users_collection[0].name]
check(layer.hide_viewport,"the kept creature should be hidden")
check(p.active_rig["cs_species"]=="CAT","the new creature should be active")

# Deleting from the scene (as X does): the chooser lets go of it.
cat=p.active_rig
for obj in list(cat.users_collection[0].all_objects):
    bpy.data.objects.remove(obj,do_unlink=True)
bpy.context.view_layer.update()
cs.forget_deleted(scene)
check(p.active_rig is None,"the chooser should forget a deleted creature")
check(rig.active(bpy.context) is None or rig.active(bpy.context).get("cs_species")!="CAT","a deleted creature should not stay active")
listed=[o for o in bpy.data.objects if o.type=="ARMATURE" and cs.rig_filter(None,o)]
check(all(o.get("cs_species")!="CAT" for o in listed),"the chooser should not list a deleted creature")

# The Delete button removes the active creature and what the kit made for it.
p.active_rig=horse
check(bpy.ops.chimera_kit.delete()=={"FINISHED"},"delete failed")
check(not creatures(),"delete should remove the creature")

print("CHIMERA_KIT_PRESETS_PASSED")
