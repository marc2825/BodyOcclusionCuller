# UnderWhere

[![Version](https://img.shields.io/github/v/release/marc2825/BodyOcclusionCuller?label=version)](https://github.com/marc2825/BodyOcclusionCuller/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

[日本語](README.md) | [English](README_EN.md)


UnderWhere is a Blender Extension that analyzes which faces of a body mesh are hidden beneath clothing and creates either a mask to hide those faces or a copy with them removed. It leaves the original Body untouched and highlights faces that should remain visible or could not be reliably classified. It works entirely offline.

> Tested on Blender 5.2.3 LTS for Windows.

## Installation

Download the Extension ZIP from [GitHub Releases](https://github.com/marc2825/BodyOcclusionCuller/releases), then install it in Blender via **Preferences → Get Extensions → Install from Disk**. Do not extract the ZIP file.

In the 3D Viewport, press **N** to open the sidebar and select the UnderWhere tab.

## Quick Start

1. Select the clothing and Body objects (select the Body last so that it is the active object), then click **Use Selection**.
2. Check the inputs with **Preflight**, then run **Analyze**.
3. Review the classification results and the number of faces actually hidden by the clothing. If necessary, make adjustments using **Keep / Hide / Clear**.
4. Generate the output using **Apply to New Copy** (a copy with a visibility mask) or **Create Deleted Copy** (a copy with the selected faces removed). For FBX export to VRChat, use the latter.

For more details, see the [User Guide](docs/user/OVERVIEW_EN.md). Japanese: [操作ガイド](docs/user/QUICKSTART_JA.md).

## Limitations

The classification results are estimates based on a finite number of samples from the tested poses. The extension cannot guarantee correct results for narrow gaps, untested poses, intermediate frames, shadows, reflections, or physics simulations.

Always inspect the exported model in the poses in which it will actually be used.

When reporting a bug, please attach a report generated with **Export Shareable Report**. These reports do not contain mesh geometry or object names. Do not publicly share full diagnostic data (**Private full diagnostics**) or purchased models.

## Documentation

- [User Guide (Japanese)](docs/user/QUICKSTART_JA.md)
- [English Overview](docs/user/OVERVIEW_EN.md)
- [Verification](docs/testing/VERIFICATION.md)
- [Changelog](CHANGELOG.md)
- [Roadmap](ROADMAP.md)

**UnderWhere** is the official name of the add-on, while **BodyOcclusionCuller** is the name of the source code repository.

## Development

The extension uses only Python's standard library and modules bundled with Blender.

```bash
python3 scripts/extension/run_tests.py --blender /path/to/blender        # Run tests
python3 scripts/extension/package_extension.py --blender /path/to/blender # Build ZIP
blender -b --factory-startup --python scripts/extension/create_sample.py  # Generate demo
```

## License

MIT License. Copyright (c) 2026 marc2825