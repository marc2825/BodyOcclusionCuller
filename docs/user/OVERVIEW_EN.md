# UnderWhere

UnderWhere is the Blender extension; BodyOcclusionCuller is its source repository.

A Blender Extension that finds body faces hidden under clothing and produces a mask, or a copy with those faces removed. The original Body is never modified. Results are finite-sample candidates for the poses you inspect, not a guarantee for every pose or view.

Tested on Blender 5.2.3 LTS (Windows). The interface follows Blender's language setting (English or Japanese).

## Install

Download the Extension ZIP from [GitHub Releases](https://github.com/marc2825/BodyOcclusionCuller/releases) and use **Preferences → Get Extensions → Install from Disk**. Open the **UnderWhere** tab in the 3D View sidebar (N).

## Layout

The top of the sidebar says what is going on and what to do next: progress and **Cancel** while analyzing, or what went wrong and how to fix it. Below it, three steps: **Set up**, **Review** and **Export**. After an analysis the sidebar moves to Review on its own.

## Set up

1. Select the clothing, then the Body last, and press **Use selection**. If the Body is split into several objects (for example a separate head), turn on **Body has several objects** and add the other parts with **+**; each part gets its own output copy. Body objects never hide each other; only the clothing does.
2. Choose the **Detail** (Fast / Standard / Fine). It is the sampling density, not a safety level.
3. Press **Analyze**. Esc over the view, or **Cancel**, stops it. **Check inputs only** checks geometry, modifiers, materials and an existing mask without analyzing, and shows the Body size.

Collapsed sections hold the rest. **Poses and purpose**: inspect the current pose, or add up to 32 listed frames (a face is hideable only if every frame hides it); find hideable faces, or check an existing vertex-group Mask modifier at the bottom of the stack (Smooth off). **Clothing materials**: the automatic verdict and the **Opaque** switch for each material. **Sampling values**: the raw numbers.

## Review

**Result** shows how many faces can be removed, as a count and a share, and the verdicts: **Hideable** (green), **Visible** (blue) and **Unsure** (yellow). When checking an existing mask, red marks visible faces it hides and purple unsure faces it hides. Your own choices show as pink (**Hidden by you**) and white (**Kept by you**).

**Next steps** lists what still needs a person, most important first: points to check before export, clothing materials that leave faces unsure (with an **Opaque** switch and **Analyze again** right there), and the unsure faces left (with buttons to start picking them). When nothing is left, it offers **Go to Export**.

The verdict colours appear as soon as the analysis finishes, **Beside the Body** (default: a coloured copy; if the colours do not show, press **Show colours in this view**) or **On the Body** (drawn on the Body itself; nothing is added to the scene). On the Body, **Show through clothing** keeps the colours visible under the clothing, **Opacity** sets their strength, faces are picked on the Body, and the colours fade while you edit the Body so the selection stays visible. **Show** switches between **Verdicts** (click a legend colour to show or hide it), **Before / After** (existing mask versus output), **After output**, **Without mask** and **Poses** (the share of inspected frames that hide each face; the verdict still keeps any face seen in one frame).

To decide unsure faces: under **Choose faces**, pick where to select (**Comparison** or **Body**), press **Box**, **Lasso** or **Brush** (mouse wheel resizes) and drag. Shift adds, Ctrl removes, and switching tools keeps the selection. Under **Decide**, press **Keep**, **Hide** or **Clear choice**; the comparison is redrawn and you can go on selecting. Press **Done** to return to Object Mode. With **Only change unsure faces** (default) a rough selection never changes decided faces. **Select by reason** and **One face at a time** (collapsed) select by cause or step through single faces with **Select**, **Next** and **View ray**. Everything is undoable and the original verdicts stay recorded. The comparison is only a view: after deleting or adding faces on it, Keep and Hide are refused until you press **Update**.

When checking an existing mask, visible faces are always shown again. **Show visible and unsure faces again** (default) also restores unsure faces; **Show visible faces again** keeps the existing mask there and reports how many unsure faces stay hidden.

## Export

- **Create masked copy** hides the faces with a Mask modifier; easy to undo.
- **Create copy with faces removed** deletes them and keeps shape keys, UVs, weights and the Armature.

A Mask modifier cannot be applied to a mesh with shape keys, so use the copy with faces removed for FBX/VRChat. Press **Select the copy**, add its Armature (and any clothing you export) and export with **Selected Objects on** and **Apply Modifiers off**.

## Materials and supported setups

- Only a directly connected Principled BSDF with constant Alpha 1, Transmission 0, no backface culling and no volume/displacement is trusted automatically. MToon and alpha-textured materials end up Unsure.
- **Opaque** declares a material fully opaque on both sides. It is recorded as your statement, is unavailable for backface-culled materials, and must not be used for textures with cut-out holes. Materials that really animate (an action, driver or NLA with content) are not trusted; an empty animation container is fine.
- Armature deformation, shape keys and Solidify on clothing are supported. Clothing whose openings cannot be resolved is named under Next steps and never used to hide faces automatically.
- Body modifiers that change topology (Subdivision, Mirror, Geometry Nodes, …) are refused.
- A Body larger than 10 m in world space (for example a 100x FBX import) is sampled at human scale. Tiny object scales (such as 0.0001 from FBX) are fine when the world size is correct.

The Body itself never hides other faces, so a garment with an open back may keep front faces as well. Narrow gaps, poses between or outside the inspected frames, shadows, reflections and physics are not covered.

## Saving and reports

Results are not saved in the .blend file. Analyze again after reopening a file, re-enabling the Extension or changing inputs; the top of the sidebar explains why and offers **Analyze again**. Your Keep and Hide choices are saved in the file and restored automatically while the Body's faces are unchanged; **Clear** removes them all.

**Export shareable report** contains counts, reasons and versions only — no geometry, names or personal paths. Use it for bug reports. **Include full diagnostics** adds mesh data; do not share it.

License: Original License (free to use, and what you make with it is yours; redistributing or selling the add-on itself is not permitted), Copyright (c) 2026 marc2825. No network access or telemetry.
