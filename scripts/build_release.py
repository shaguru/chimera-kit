"""Package only the Blender add-on, without REA, tests or machine-local files."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
root=Path(__file__).resolve().parents[1]
dest=root/"Chimera_Kit.zip"
with ZipFile(dest,"w",ZIP_DEFLATED) as archive:
    for path in sorted((root/"chimera_kit").glob("*.py")):
        archive.write(path,path.relative_to(root).as_posix())
    for path in sorted((root/"chimera_kit"/"templates").glob("*.json")):
        archive.write(path,path.relative_to(root).as_posix())
    if (root/"licenses").exists():
        for path in sorted((root/"licenses").glob("*")):
            archive.write(path,"chimera_kit/licenses/"+path.name)
    for name in ("README.md","LICENSE"):
        if (root/name).exists(): archive.write(root/name,"chimera_kit/"+name)
print("Built",dest,"—",dest.stat().st_size,"bytes")
