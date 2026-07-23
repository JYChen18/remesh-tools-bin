# sim-asset-tools

`sim-asset-tools` prepares portable assets for robotics and physics simulation.
Its `sim-assets` CLI provides standalone mesh processing, object-bundle
generation, and body-surface generation from compiled MuJoCo models.

## Installation

Install the CLI and all workflows as an isolated tool:

```bash
uv tool install sim-asset-tools
```

Project wheels support CPython 3.10–3.13 on Linux x86_64 or ARM64, Windows
x86_64, and macOS 12 or newer on Apple Silicon.

## Supported workflows

| Command family | Support |
| --- | --- |
| `mesh` | Normalize, OpenVDB SDF, ACVD remeshing, CoACD decomposition |
| `prepare object` / `prepare objects` | GLB, OBJ, PLY, STL to MJCF and/or URDF bundles |
| `prepare body-surfaces` / `check body-surfaces` | MuJoCo XML, MJCF, or MJB to body-local OBJ surfaces |
| `check object` | Object-bundle integrity |

See the [runnable examples](https://github.com/JYChen18/sim-asset-tools/blob/main/examples/README.md)
for CLI commands and `sim-assets --help` for all available options.

## Third-party software

| Component | Version or source | Use | License |
| --- | --- | --- | --- |
| ACVD | Commit `275554980e466914ae9053c8667006f251989422` | Bundled remeshing tools | [CeCILL-B](https://github.com/JYChen18/sim-asset-tools/blob/main/native/vendor/ACVD/LICENSE.txt) |
| OpenVDB | `v8.2.0` | Statically linked SDF processing | [MPL 2.0](https://github.com/JYChen18/sim-asset-tools/blob/main/licenses/OpenVDB-MPL-2.0.txt) |
| oneTBB | `v2022.0.0` | Bundled threading library | [Apache 2.0](https://github.com/JYChen18/sim-asset-tools/blob/main/licenses/oneTBB-Apache-2.0.txt) |
| Boost | `1.81.0` | OpenVDB build dependency | [Boost Software License 1.0](https://github.com/JYChen18/sim-asset-tools/blob/main/licenses/Boost-BSL-1.0.txt) |
| VTK | `9.6.2` | Native mesh processing runtime | [BSD 3-Clause](https://gitlab.kitware.com/vtk/vtk/-/blob/v9.6.2/Copyright.txt) |
| CoACD | `>=1.0.11` | Convex decomposition | [MIT](https://github.com/SarahWeiii/CoACD/blob/main/LICENSE) |
| MuJoCo | `>=3.9.0` | Compiled-model processing | [Apache 2.0](https://github.com/google-deepmind/mujoco/blob/main/LICENSE) |

Code authored for this repository is licensed under the
[Apache License 2.0](https://github.com/JYChen18/sim-asset-tools/blob/main/LICENSE).
Bundled third-party components retain their respective licenses.
