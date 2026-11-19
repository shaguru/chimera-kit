"""Load the exact release zip and verify a saved demo reopens with its rig/action."""
from pathlib import Path
from zipfile import ZipFile
import sys
import bpy
import addon_utils
ROOT=Path(__file__).resolve().parents[1]
dest=ROOT/"tests"/"output"/"package"
dest.mkdir(parents=True,exist_ok=True)
with ZipFile(ROOT/"Chimera_Kit.zip") as archive:
    archive.extractall(dest)
sys.path.insert(0,str(dest))
addon_utils.enable("chimera_kit",default_set=False,persistent=True)
import chimera_kit as cs
assert Path(cs.__file__).resolve().is_relative_to(dest.resolve())
assert hasattr(bpy.types.Scene,"cs_settings")
assert cs.bl_info["version"]==(1,7,0)
from chimera_kit import template
assert set(template.data()["levels"])=={"LOW","BASE"},"the human templates should ship in the zip"
bpy.ops.wm.open_mainfile(filepath=str(ROOT/"Character_Studio_Demo.blend"))
arm=next(o for o in bpy.context.scene.objects if o.get("cs_rig"))
assert arm["cs_species"]=="DRAGON"
assert arm.animation_data and len(arm.animation_data.nla_tracks)==2
assert len(arm.cs_layers)==2
assert bpy.context.scene.cs_settings.active_rig==arm
from types import SimpleNamespace
from chimera_kit import ui
class Layout:
    def __getattr__(self,key):
        if key in {"box","row","column"}: return lambda *a,**kw: self
        if key=="prop": return lambda obj,name,**kw: obj.path_resolve(name)
        if key=="operator": return lambda *a,**kw: SimpleNamespace()
        return lambda *a,**kw: None
ctx=SimpleNamespace(object=arm,scene=bpy.context.scene,region=SimpleNamespace(width=380))
for panel in ui.CLASSES:
    panel.draw(SimpleNamespace(layout=Layout()),ctx)
assert bpy.ops.chimera_kit.validate()=={"FINISHED"}
print("CHIMERA_KIT_PACKAGE_PASSED",cs.__file__)
