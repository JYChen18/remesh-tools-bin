# Native build subsystem

This directory owns every source-time input used to build the packaged ACVD and
OpenVDB executables:

- `CMakeLists.txt` configures the VTK SDK, install layout, and platform runtime
  paths.
- `cmake/` defines the ACVD and OpenVDB targets and their fetched dependencies.
- `src/` contains native code maintained by sim-asset-tools.
- `tools/` contains Python helpers invoked by CMake.
- `vendor/ACVD/` is the pinned upstream ACVD source snapshot.

The similarly named `sim_asset_tools/_native/` directory is an install target,
not a source directory. It is created inside wheels and contains only packaged
executables, runtime libraries, and ACVD support files. Do not commit generated
contents there.

The repository root `CMakeLists.txt` intentionally remains a small facade so
both scikit-build-core and direct `cmake -S .` builds use this subsystem.

When updating a native dependency, keep its version, source declaration,
license entry, and wheel smoke coverage in sync. Validate changes by building a
wheel from the source distribution and running `tests/smoke_wheel.py` from an
environment containing only that wheel and its declared dependencies.
