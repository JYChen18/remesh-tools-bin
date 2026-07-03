# acvd-bin

`acvd-bin` is a Python packaging wrapper for the official
[valette/ACVD](https://github.com/valette/ACVD) command line tools.

The package is designed for:

```bash
uv add git+https://github.com/JYChen18/acvd-bin.git
```

It pins the runtime VTK dependency to `vtk==9.4.0`. During the isolated build,
it downloads the matching official VTK 9.4.0 wheel SDK archive from
`https://vtk.org/files/wheel-sdks/`, points ACVD's CMake build at that SDK, and
does not use system VTK.

Installed launchers include:

- `ACVD`
- `ACVDP`
- `ACVDQ`
- `ACVDQP`
- `AnisotropicRemeshing`
- `AnisotropicRemeshingQ`
- `AnisotropicRemeshingQP`
- `VolumeAnalysis`

You can also run `acvd-bin` with no arguments to list the packaged tools, or
use `acvd-bin ACVD ...` as a generic dispatcher.

## Requirements

- CPython 3.8 through 3.13
- A working C++ compiler
- Network access during source builds so the VTK 9.4.0 SDK archive can be
  downloaded

The ACVD source is vendored as a pinned official snapshot under
`third_party/ACVD`.
