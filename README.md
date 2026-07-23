# sim-asset-tools

`sim-asset-tools` prepares portable, versioned assets for robotics and physics
simulation. It combines packaged OpenVDB and ACVD executables, peer raw-mesh
operations such as normalization and CoACD decomposition, and higher-level
object and body-surface workflows behind one `sim-assets` command.

## Installation

Install all object and model operations as an isolated tool:

```bash
uv tool install "sim-asset-tools[all]"
```

The default installation includes native remeshing, normalization, validation,
and their VTK/Trimesh runtimes. Install `sim-asset-tools[coacd]` for object
preparation or `sim-asset-tools[mujoco]` for compiled-model body surfaces.

Prebuilt wheels support CPython 3.10–3.13 on Linux x86_64 or ARM64, Windows
x86_64, and macOS 12 or newer on Intel or Apple Silicon. Headless processing
does not require additional OS packages beyond the platform baseline.

To build from source:

```bash
git clone https://github.com/JYChen18/sim-asset-tools.git
cd sim-asset-tools
uv sync --all-extras
uv build --wheel
```

Native source organization and dependency-update guidance live in
[native/README.md](native/README.md).

## Mesh operations

```bash
sim-assets mesh normalize input.obj normalized.obj

sim-assets mesh openvdb input.obj output.obj \
  --resolution 50 --level-set 0.1

sim-assets mesh acvd input.obj output.ply \
  --vertices 3000 --gradation 1.5

sim-assets mesh coacd input.obj collision/
```

## Object bundles

Prepare one object or every supported mesh in a folder:

```bash
sim-assets prepare object raw/cup.obj \
  --output assets/objects/cup --formats mjcf,urdf
sim-assets prepare objects raw/ --output assets/objects --jobs 8
sim-assets check object assets/objects/cup
```

Each object is self-describing:

```text
cup/
├── asset.json
├── source.glb
├── visual.obj
├── collision/
│   └── part_000.obj
├── model.xml
└── model.urdf
```

The pipeline normalizes the source mesh, runs OpenVDB and ACVD, decomposes the
result with CoACD, and records the recipe, artifact hashes, and canonical
geometry information in `asset.json`.

`source_aabb_center` and the full `source_aabb_extents` are measured on the
input mesh. When `recipe.normalize` is true, processed coordinates are
`2 * (source - source_aabb_center) / norm(source_aabb_extents)`.
`obb_center`, `obb_axes`, and the full `obb_extents` describe the processed
visual surface. `volume`, `center_of_mass`, and `inertia_per_unit_mass` are
computed from the published collision parts so that they match simulation mass
and density behavior. The inertia assumes uniform density, is measured about
`center_of_mass`, and converts to physical inertia by multiplying by the chosen
mass.

## Body surfaces

Prepare body-local, watertight surfaces from the final compiled model so that
entity prefixes, scaling, and attached collision geoms are included:

```bash
sim-assets prepare body-surfaces scene.xml \
  --output assets/derived/scene/body-surfaces

sim-assets check body-surfaces scene.xml \
  --assets assets/derived/scene/body-surfaces
```

The `body-surfaces/v1` manifest maps exact model body names to hashed filenames,
which supports names containing separators such as `hand/forearm`. Run
`sim-assets check body-surfaces` to validate the source and generated mesh
hashes before using the surfaces.

## Manifest compatibility

Object bundles use schema `sim-object/v1`. Their `sha256` object maps each
non-collision artifact path directly to its digest. The reserved `collision`
entry fingerprints a canonical map from every collision-relative filename to
its file digest, so changing, adding, removing, or renaming any part invalidates
the collision set as one unit. The reserved keys `schema`, `geometry`, and
`recipe` fingerprint the corresponding top-level values, while `sha256`
fingerprints every other entry in the `sha256` object. JSON fingerprints use
UTF-8 JSON with sorted keys and compact separators. This catches accidental
metadata edits without loading and recomputing the geometry. Body-surface
bundles continue to use the `sim-asset/v1` envelope and the separately
versioned `body-surfaces/v1` contract. Every manifest is published only after
its referenced files are complete.

## Third-party software

| Component | Version or source | Use | License |
| --- | --- | --- | --- |
| ACVD | Commit `275554980e466914ae9053c8667006f251989422` | Bundled remeshing tools | [CeCILL-B](native/vendor/ACVD/LICENSE.txt) |
| OpenVDB | `v8.2.0` | Statically linked SDF processing | [MPL 2.0](licenses/OpenVDB-MPL-2.0.txt) |
| oneTBB | `v2022.0.0` | Bundled threading library | [Apache 2.0](licenses/oneTBB-Apache-2.0.txt) |
| Boost | `1.81.0` | OpenVDB build dependency | [Boost Software License 1.0](licenses/Boost-BSL-1.0.txt) |
| VTK | `9.6.2` | Native mesh processing runtime | BSD-style VTK license |
| CoACD | Optional Python dependency | Convex decomposition | See the installed CoACD distribution |

Code authored for this repository is licensed under the
[Apache License 2.0](LICENSE). Bundled third-party components retain their
respective licenses.
