# Changes

## 1.7.0

- **Presets build on the spot.** Picking a preset builds it at once. The creature it replaces is deleted if nothing has been done to it yet (no animation, fitting, appended structures or mesh of your own); otherwise it is hidden and kept. **Build another creature** adds one alongside.
- **Creature chooser.** A bin next to the chooser deletes the active creature (with a confirmation). The chooser lists only creatures in the scene, and lets go of one deleted with X in the viewport or Outliner, so it no longer lingers in the list until the file is reopened.
- **Foot length and Foot thickness** replace Foot size. Length stretches heel to toe along the ground; thickness widens and deepens the foot and, on a flat foot, raises the ankle. Recipes with the older Foot size set both.
- **Horse, Gnu and Centaur** carry a barrel (the belly as deep as the chest) and a level back. The Centaur's human torso is deeper at the chest and rises from the horse's breast, ahead of the forelegs, and it has a person's neck rather than a horse's.
- The Build tab is laid out in numbered steps: 1 · Creature skeleton, 2 · Mesh from skeleton (experimental), 3 · Skin your own mesh.
- Rigs and actions are stamped with the version that made them.
- Experimental mesh: shoulders sit lower; leg openings are centred on the hip and shoulder on four-legged bodies.

## 1.6.0

- Experimental mesh: **human base models.** Two-legged creatures with arms can wear the MakeHuman light proxies (01 Low, 741 vertices; 02 Base, 1,591 vertices; CC0), fitted to the skeleton bone by bone and skinned with their own weights. `tools/make_templates.py` regenerates the data.

## 1.5.0 to 1.5.2

- Experimental mesh: an **Arms** choice (A-pose, T-pose or as built) sets the arm rest before building; arms resting at the sides are modelled in an A-pose and lowered. Shoulders slope from the neck into the deltoid; the bridge between the shoulder and the arm no longer twists; the trapezius no longer swells into a lump.

## 1.4.x

- **Dog** and **Cat** presets (38 presets).
- **Hand size**, **Arm rest pose**, **Natural curve** and **Head shape** sliders; **Chest width** and **Hip width** under Trunk shape; **Wing angle** and **Wing height** under Accessories. Body length also lengthens upright creatures.
- Experimental mesh: **Mesh from skeleton** builds one connected, skinned, all-quad body around the skeleton, with loops gathered at the joints and a **Muscle taper** slider; mechs get separate hard parts.

## 1.3.0

- Renamed from Character Studio for Blender to Chimera Kit. Recipes and bone maps saved under the old name still load.
