# Native ACVD and OpenVDB build orchestration.

# Boost 1.81's Predef subproject declares CMake 3.0 policy compatibility.
# CMake 4 removed compatibility older than 3.5 and requires callers to provide
# this floor when adding such third-party projects without patching them.
if(CMAKE_VERSION VERSION_GREATER_EQUAL 4.0)
  if(NOT DEFINED CMAKE_POLICY_VERSION_MINIMUM OR CMAKE_POLICY_VERSION_MINIMUM VERSION_LESS 3.5)
    set(CMAKE_POLICY_VERSION_MINIMUM 3.5)
  endif()
endif()

find_package(Python COMPONENTS Interpreter REQUIRED)

set(SIM_ASSET_TOOLS_VTK_VERSION "9.6.2" CACHE STRING "VTK version used by sim-asset-tools")
if(WIN32 AND DEFINED ENV{TEMP})
  string(MD5 SIM_ASSET_TOOLS_BUILD_ID "${CMAKE_BINARY_DIR}")
  file(TO_CMAKE_PATH "$ENV{TEMP}" SIM_ASSET_TOOLS_TEMP_DIR)
  set(SIM_ASSET_TOOLS_VTK_SDK_ROOT_DEFAULT
    "${SIM_ASSET_TOOLS_TEMP_DIR}/sat-vtk-${SIM_ASSET_TOOLS_BUILD_ID}"
  )
else()
  set(SIM_ASSET_TOOLS_VTK_SDK_ROOT_DEFAULT "${CMAKE_BINARY_DIR}/vtk-wheel-sdk")
endif()
set(SIM_ASSET_TOOLS_VTK_SDK_ROOT "${SIM_ASSET_TOOLS_VTK_SDK_ROOT_DEFAULT}" CACHE PATH "Extracted VTK wheel SDK root")
set(SIM_ASSET_TOOLS_VTK_SDK_INFO "${CMAKE_BINARY_DIR}/sim-asset-tools-vtk-sdk.cmake")

execute_process(
  COMMAND
    "${Python_EXECUTABLE}"
    "${CMAKE_CURRENT_SOURCE_DIR}/tools/fetch_vtk_sdk.py"
    "--version" "${SIM_ASSET_TOOLS_VTK_VERSION}"
    "--dest" "${SIM_ASSET_TOOLS_VTK_SDK_ROOT}"
    "--cmake-output" "${SIM_ASSET_TOOLS_VTK_SDK_INFO}"
  WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
  RESULT_VARIABLE SIM_ASSET_TOOLS_VTK_SDK_RESULT
  OUTPUT_VARIABLE SIM_ASSET_TOOLS_VTK_SDK_STDOUT
  ERROR_VARIABLE SIM_ASSET_TOOLS_VTK_SDK_STDERR
)

if(NOT SIM_ASSET_TOOLS_VTK_SDK_RESULT EQUAL 0)
  message(FATAL_ERROR
    "Unable to prepare the VTK ${SIM_ASSET_TOOLS_VTK_VERSION} SDK.\n"
    "stdout:\n${SIM_ASSET_TOOLS_VTK_SDK_STDOUT}\n"
    "stderr:\n${SIM_ASSET_TOOLS_VTK_SDK_STDERR}"
  )
endif()

include("${SIM_ASSET_TOOLS_VTK_SDK_INFO}")

if(NOT EXISTS "${SIM_ASSET_TOOLS_VTK_DIR}/VTKConfig.cmake" AND NOT EXISTS "${SIM_ASSET_TOOLS_VTK_DIR}/vtk-config.cmake")
  message(FATAL_ERROR "VTK package config was not found in the prepared SDK: ${SIM_ASSET_TOOLS_VTK_DIR}")
endif()

# Force ACVD to use the build-managed VTK SDK instead of falling back to a
# system VTK installation.
set(VTK_DIR "${SIM_ASSET_TOOLS_VTK_DIR}" CACHE PATH "VTK package directory from the VTK wheel SDK" FORCE)
set(CMAKE_FIND_PACKAGE_NO_PACKAGE_REGISTRY TRUE)
set(CMAKE_FIND_PACKAGE_NO_SYSTEM_PACKAGE_REGISTRY TRUE)
set(CMAKE_EXPORT_NO_PACKAGE_REGISTRY TRUE)

if(NOT DEFINED SKBUILD_PLATLIB_DIR)
  set(SKBUILD_PLATLIB_DIR "${CMAKE_INSTALL_PREFIX}")
endif()

set(SIM_ASSET_TOOLS_NATIVE_INSTALL_DIR "${SKBUILD_PLATLIB_DIR}/sim_asset_tools/_native")

set(INSTALL_BIN_DIR "${SIM_ASSET_TOOLS_NATIVE_INSTALL_DIR}/bin" CACHE PATH "" FORCE)
set(INSTALL_LIB_DIR "${SIM_ASSET_TOOLS_NATIVE_INSTALL_DIR}/lib" CACHE PATH "" FORCE)
set(INSTALL_INCLUDE_DIR "${SIM_ASSET_TOOLS_NATIVE_INSTALL_DIR}/include" CACHE PATH "" FORCE)
set(INSTALL_CMAKE_DIR "${SIM_ASSET_TOOLS_NATIVE_INSTALL_DIR}/lib/cmake/ACVD" CACHE PATH "" FORCE)
set(INSTALL_DOC_DIR "${SIM_ASSET_TOOLS_NATIVE_INSTALL_DIR}/share/doc/ACVD" CACHE PATH "" FORCE)

# VTK's Linux x86_64 wheel uses the old libstdc++ ABI, while its aarch64
# wheel uses the default modern ABI.
if(UNIX AND NOT APPLE AND CMAKE_SYSTEM_PROCESSOR MATCHES "^(x86_64|amd64|AMD64)$")
  add_compile_definitions(_GLIBCXX_USE_CXX11_ABI=0)
endif()

if(APPLE)
  set(CMAKE_INSTALL_RPATH "@loader_path/../lib;@loader_path/../../../vtkmodules/.dylibs;@loader_path/../../../vtkmodules/.libs;@loader_path/../../../vtkmodules")
elseif(UNIX)
  set(CMAKE_INSTALL_RPATH "$ORIGIN/../lib;$ORIGIN/../../../vtkmodules/.dylibs;$ORIGIN/../../../vtkmodules/.libs;$ORIGIN/../../../vtkmodules")
endif()
set(CMAKE_INSTALL_RPATH_USE_LINK_PATH FALSE)

include("${CMAKE_CURRENT_SOURCE_DIR}/cmake/openvdb.cmake")
include("${CMAKE_CURRENT_SOURCE_DIR}/cmake/acvd.cmake")
