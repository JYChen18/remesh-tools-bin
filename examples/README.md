# Examples

Run these commands from the repository root after installing `sim-asset-tools`.
The commands are listed in runnable order, and each processing command writes
to a separate folder under `examples/outputs/`.

## Mesh operations

Normalize an Objaverse mesh:

```bash
sim-assets mesh normalize \
  examples/objects/aY8hdiQMQdDjXtWRHM7PjnVwjdu.glb \
  examples/outputs/mesh/normalize/object.obj
```

Apply OpenVDB surface processing to the normalized mesh:

```bash
sim-assets mesh openvdb \
  examples/outputs/mesh/normalize/object.obj \
  examples/outputs/mesh/openvdb/object.obj
```

Remesh the OpenVDB result with ACVD:

```bash
sim-assets mesh acvd \
  examples/outputs/mesh/openvdb/object.obj \
  examples/outputs/mesh/acvd/object.ply \
  --vertices 1024 --gradation 1.5
```

The command defaults to `--method acvd`. All seven packaged ACVD variants are
available:

| Method | Native tool | Additional options |
| --- | --- | --- |
| `acvd` | `ACVD` | |
| `acvd-parallel` | `ACVDP` | `--threads` |
| `acvd-quadric` | `ACVDQ` | `--quadric-level` |
| `acvd-quadric-parallel` | `ACVDQP` | `--quadric-level`, `--threads` |
| `acvd-anisotropic` | `AnisotropicRemeshing` | |
| `acvd-anisotropic-quadric` | `AnisotropicRemeshingQ` | `--quadric-level` |
| `acvd-anisotropic-quadric-parallel` | `AnisotropicRemeshingQP` | `--quadric-level`, `--threads` |

For example, run parallel quadric remeshing with:

```bash
sim-assets mesh acvd \
  examples/outputs/mesh/openvdb/object.obj \
  examples/outputs/mesh/acvd/object-quadric-parallel.ply \
  --method acvd-quadric-parallel \
  --vertices 1024 --gradation 1.5 \
  --quadric-level 1 --threads 8
```

Decompose the remeshed object into convex collision parts with CoACD:

```bash
sim-assets mesh coacd \
  examples/outputs/mesh/acvd/object.ply \
  examples/outputs/mesh/coacd
```

## Asset preparation

Prepare one object as an MJCF and URDF bundle:

```bash
sim-assets prepare object \
  examples/objects/aY8hdiQMQdDjXtWRHM7PjnVwjdu.glb \
  --output examples/outputs/prepare/object
```

Prepare every object in the example folder:

```bash
sim-assets prepare objects examples/objects \
  --output examples/outputs/prepare/objects --jobs 3
```

Prepare both Shadow Hand models into their shared flat surface provider:

```bash
sim-assets prepare body-surfaces examples/models/shadow_hand/scene_right.xml
sim-assets prepare body-surfaces examples/models/shadow_hand/scene_left.xml
```

Only bodies with multiple collision-enabled geoms receive prepared surfaces.
Single-geom bodies use their compiled MuJoCo collision surfaces directly. A
plane or heightfield must be the only collision-enabled geom on its body.

Without `--output`, surfaces are written to `surfaces/` under the model's
resolved MuJoCo compiler `meshdir`. Pass `--output DIRECTORY` to override it.
Models that resolve to the same output share one flat provider: each command
adds its non-conflicting body surfaces to the common `asset.json`. Re-running
an unchanged model reuses its set. `--overwrite` regenerates only that model's
set and preserves sets prepared from other models.

## Validation

Check the prepared single-object bundle:

```bash
sim-assets check object examples/outputs/prepare/object
```

Check the prepared Shadow Hand body surfaces:

```bash
sim-assets check body-surfaces examples/models/shadow_hand/scene_right.xml
sim-assets check body-surfaces examples/models/shadow_hand/scene_left.xml
```
