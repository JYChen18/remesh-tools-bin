# remesh-tools-bin

`remesh-tools-bin` is a Python packaging wrapper for native remeshing command
line tools. It currently packages the official
[valette/ACVD](https://github.com/valette/ACVD) remeshing tools and a small
[OpenVDB](https://github.com/AcademySoftwareFoundation/openvdb) SDF remeshing
tool.

## Installation

The package is designed for:

```bash
uv add git+https://github.com/JYChen18/remesh-tools-bin.git
```

Source installs compile native dependencies and may take roughly 5-15 minutes depending on machine/network.

### Requirements

- CPython 3.8 through 3.13
- A system C++ compiler/toolchain available to CMake. `uv` does not install
  GCC, Clang, MSVC, or Xcode Command Line Tools.

## Usage

The installed launcher is:

```bash
remesh
```

### ACVD Remeshing

ACVD methods remesh a surface to a target vertex count. `--gradation 0`
requests uniform remeshing; higher values give more influence to local
curvature.

```bash
remesh acvd input.obj output.ply --vertices 3000 --gradation 0
remesh acvd-quadric input.obj output.ply --vertices 3000 --gradation 1.5
remesh acvd-anisotropic-quadric input.obj output.ply --vertices 1000 --gradation 1.5
```

Available ACVD methods:

- `acvd`
- `acvd-parallel`
- `acvd-quadric`
- `acvd-quadric-parallel`
- `acvd-anisotropic`
- `acvd-anisotropic-quadric`
- `acvd-anisotropic-quadric-parallel`

Common options include `--vertices`, `--gradation`, `--subsample`,
`--split-long-edges`, and `--display`. Parallel methods also accept
`--threads`.

### OpenVDB SDF Remeshing

The OpenVDB method reads OBJ meshes and writes OBJ meshes by converting the
input surface to a signed distance field and extracting a new surface:

```bash
remesh openvdb-sdf input.obj output.obj --resolution 50 --level-set 0.1
```

By default it normalizes the input mesh before applying the OpenVDB conversion
and then recovers the original scale, matching the way CoACD uses this
preprocessing step. Use `--no-normalize` to apply OpenVDB directly in input
coordinates.
