# UnderWhere

UnderWhere is the Blender extension; BodyOcclusionCuller is its source repository.

A Blender Extension that finds body faces hidden under clothing and produces a mask, or a copy with those faces removed. The original Body is never modified. Results are finite-sample candidates for the poses you inspect, not a guarantee for every pose or view.

Tested on Blender 5.2.3 LTS (Windows).

## Install

Download the Extension ZIP from [GitHub Releases](https://github.com/marc2825/BodyOcclusionCuller/releases) and use **Preferences → Get Extensions → Install from Disk**. Open the **UnderWhere** tab in the 3D View sidebar (N).

## Workflow

The sidebar is split into five sections: **1 Inputs**, **2 Inspection** (with collapsed Materials and Advanced), **3 Results**, **4 Review and Fix** and **5 Output**. The result sections appear after Analyze.

1. Select the clothing and the Body, with the Body active, and press **Use Selection**.
2. Choose **Generate Mask**, or **Audit Existing Mask** for a single vertex-group Mask modifier at the end of the stack (Smooth off).
3. The current frame is always inspected. **Current + Selected Frames** adds up to 32 frames. A face is a candidate only if it stays hidden in every inspected frame.
4. Pick a work budget (Quick / Balanced / Detailed — sampling density, not a safety level), then **Preflight** and **Analyze**.

Results are labelled Candidate, Keep (seen) and Review (undecided). **Output hides** is the face count actually removed by the generated mask. **Update Comparison** shows a colored copy beside the Body: Classification, **Before / After** (existing mask versus output), Output or Unmasked.

When auditing, exposed faces are always restored. **Restore exposed + undecided** (default) also restores faces that could not be decided; **Restore exposed only** keeps the existing mask there and reports how many undecided faces stay hidden. A disabled mask, or one that hides nothing or everything, is flagged.

Review faces are never hidden automatically; you decide. Under **Fix faces**, choose where to select (Comparison or Body), pick **Box**, **Lasso** or **Brush** (paint; mouse wheel resizes) and drag in the viewport — Shift adds, Ctrl removes, and switching tools keeps the selection. Then press **Keep / Hide / Clear**; a selection on the colored comparison maps back to the Body. With **Review faces only** (default) a rough selection affects only Review and existing-mask issue faces. **Select in bulk** picks all Review faces, all existing-mask issues, or faces with one reason. **Select**, **Next** and **View Ray** inspect single faces, and each face shows a hint for its reason. Overrides are undoable; the original evidence is kept.

## Output

- **Apply to New Copy** creates a copy with a Mask modifier.
- **Create Deleted Copy** removes the faces from a copy, keeping shape keys, UVs, weights and the Armature.

A Mask modifier cannot be applied to a mesh with shape keys, so use the deleted copy for FBX/VRChat. Select it with its Armature (and any clothing you export) and export with **Selected Objects on** and **Apply Modifiers off**.

## Materials and supported setups

- Only a directly connected Principled BSDF with constant Alpha 1, Transmission 0, no backface culling and no volume/displacement is trusted automatically. MToon and alpha-textured materials end up in Review.
- **Opaque** in the Materials section lets you declare a material fully opaque on both sides. It is recorded as your assumption, is unavailable for backface-culled materials, and must not be used for textures with cut-out holes.
- Armature deformation, shape keys and Solidify on clothing are supported. Clothing whose openings cannot be resolved is reported by name and never used to auto-hide.
- Body modifiers that change topology (Subdivision, Mirror, Geometry Nodes, …) are refused.

The Body itself is never treated as a blocker, so a garment with an open back may keep front faces as well. Narrow gaps, poses between or outside the inspected frames, shadows, reflections and physics are not covered.

## Reports

**Export Shareable Report** contains counts, reasons and versions only — no geometry, names or personal paths. Use it for bug reports. **Private full diagnostics** include mesh data; do not share them.

Results are not saved in the .blend file. Analyze again after reopening a file, re-enabling the Extension or changing inputs.

License: MIT, Copyright (c) 2026 marc2825. No network access or telemetry.
