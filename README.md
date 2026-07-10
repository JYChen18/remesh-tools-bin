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

Published releases provide prebuilt wheels for Linux x86_64 (glibc 2.28 or
newer), Windows x86_64, macOS Intel, and macOS Apple Silicon (macOS 12 or
newer).

### Requirements

- CPython 3.10 through 3.13
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

## Acknowledgements

The ACVD tools are provided by the vendored
[valette/ACVD](https://github.com/valette/ACVD) source at commit
`275554980e466914ae9053c8667006f251989422`. ACVD credits CNRS, INSA-Lyon,
UCBL, and INSERM, and derives from the following work:

- S. Valette, J.-M. Chassery, and R. Prost, "Generic remeshing of 3D
  triangular meshes with metric-dependent discrete Voronoi Diagrams," IEEE
  TVCG 14(2), 369-381, 2008.
- S. Valette and J.-M. Chassery, "Approximated Centroidal Voronoi Diagrams for
  Uniform Polygonal Mesh Coarsening," Computer Graphics Forum 23(3), 381-389,
  2004.
- M. Audette et al., "Approach-guided controlled resolution brain meshing for
  FE-based interactive neurosurgery simulation," MICCAI Mesh Processing in
  Medical Image Analysis Workshop, 2011.

The package also uses OpenVDB for signed-distance-field processing, oneTBB for
threading, Boost components required by OpenVDB, and VTK for native mesh
processing and Python runtime support.

## Third-Party Software

| Component | Version or source | Use | License |
| --- | --- | --- | --- |
| ACVD | Commit `275554980e466914ae9053c8667006f251989422` | Bundled native remeshing tools | [CeCILL-B](third_party/ACVD/LICENSE.txt) |
| OpenVDB | `v8.2.0` | Statically linked SDF remeshing implementation | [MPL 2.0](licenses/OpenVDB-MPL-2.0.txt) |
| oneTBB | `v2022.0.0` | Bundled threading library | [Apache 2.0](licenses/oneTBB-Apache-2.0.txt) and [third-party notices](licenses/oneTBB-THIRD-PARTY-PROGRAMS.txt) |
| Boost | `1.81.0`, or a compatible system version | OpenVDB build dependency | [Boost Software License 1.0](licenses/Boost-BSL-1.0.txt) |
| VTK | `9.5.2` | External build and runtime dependency | BSD-style VTK license, supplied by the `vtk` distribution |

## License

Code authored for this repository is licensed under the
[Apache License 2.0](LICENSE). Bundled third-party components remain under
their respective licenses listed above.
