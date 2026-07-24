# Examples

Run these commands from the repository root after installing `sim-asset-tools`.
The commands are listed in runnable order, and each processing command writes
to a separate folder under `examples/outputs/`.

## Mesh operations

Normalize an Objaverse mesh:

```bash
uv run sim-assets mesh normalize \
  examples/objects/aY8hdiQMQdDjXtWRHM7PjnVwjdu.glb \
  examples/outputs/mesh/normalize/object.obj
```

Apply OpenVDB surface processing to the normalized mesh:

```bash
uv run sim-assets mesh openvdb \
  examples/outputs/mesh/normalize/object.obj \
  examples/outputs/mesh/openvdb/object.obj
```

Remesh the OpenVDB result with ACVD:

```bash
uv run sim-assets mesh acvd \
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
uv run sim-assets mesh acvd \
  examples/outputs/mesh/openvdb/object.obj \
  examples/outputs/mesh/acvd/object-quadric-parallel.ply \
  --method acvd-quadric-parallel \
  --vertices 1024 --gradation 1.5 \
  --quadric-level 1 --threads 8
```

Decompose the remeshed object into convex collision parts with CoACD:

```bash
uv run sim-assets mesh coacd \
  examples/outputs/mesh/acvd/object.ply \
  examples/outputs/mesh/coacd
```

## Asset preparation

Prepare one object as an MJCF and URDF bundle:

```bash
uv run sim-assets prepare object \
  examples/objects/aY8hdiQMQdDjXtWRHM7PjnVwjdu.glb \
  --output examples/outputs/prepare/object
```

Prepare every object in the example folder:

```bash
uv run sim-assets prepare objects examples/objects \
  --output examples/outputs/prepare/objects --jobs 3
```

## Validation

Check the prepared single-object bundle:

```bash
uv run sim-assets check object examples/outputs/prepare/object
```
