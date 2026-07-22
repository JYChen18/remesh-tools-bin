# Examples

Run these commands from the repository root after installing
`sim-asset-tools[all]`. The commands are listed in runnable order, and each
processing command writes to a separate folder under `examples/outputs/`.

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

Prepare body-local collision surfaces for the right Shadow Hand:

```bash
sim-assets prepare body-surfaces examples/models/shadow_hand/scene_right.xml \
  --output examples/outputs/prepare/body-surfaces
```

## Validation

Check the prepared single-object bundle:

```bash
sim-assets check object examples/outputs/prepare/object
```

Check the prepared Shadow Hand body surfaces:

```bash
sim-assets check body-surfaces examples/models/shadow_hand/scene_right.xml \
  --assets examples/outputs/prepare/body-surfaces
```
