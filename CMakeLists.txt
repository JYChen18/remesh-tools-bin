cmake_minimum_required(VERSION 3.22)

project(acvd_bin VERSION 0.1.0 LANGUAGES CXX)

find_package(Python COMPONENTS Interpreter REQUIRED)

set(ACVD_BIN_VTK_VERSION "9.4.0" CACHE STRING "VTK version used by acvd-bin")
set(ACVD_BIN_VTK_SDK_ROOT "${CMAKE_BINARY_DIR}/vtk-wheel-sdk" CACHE PATH "Extracted VTK wheel SDK root")
set(ACVD_BIN_VTK_SDK_INFO "${CMAKE_BINARY_DIR}/acvd-bin-vtk-sdk.cmake")

execute_process(
  COMMAND
    "${Python_EXECUTABLE}"
    "${CMAKE_CURRENT_SOURCE_DIR}/tools/fetch_vtk_sdk.py"
    "--version" "${ACVD_BIN_VTK_VERSION}"
    "--dest" "${ACVD_BIN_VTK_SDK_ROOT}"
    "--cmake-output" "${ACVD_BIN_VTK_SDK_INFO}"
  WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
  RESULT_VARIABLE ACVD_BIN_VTK_SDK_RESULT
  OUTPUT_VARIABLE ACVD_BIN_VTK_SDK_STDOUT
  ERROR_VARIABLE ACVD_BIN_VTK_SDK_STDERR
)

if(NOT ACVD_BIN_VTK_SDK_RESULT EQUAL 0)
  message(FATAL_ERROR
    "Unable to prepare the VTK ${ACVD_BIN_VTK_VERSION} SDK.\n"
    "stdout:\n${ACVD_BIN_VTK_SDK_STDOUT}\n"
    "stderr:\n${ACVD_BIN_VTK_SDK_STDERR}"
  )
endif()

include("${ACVD_BIN_VTK_SDK_INFO}")

if(NOT EXISTS "${ACVD_BIN_VTK_DIR}/VTKConfig.cmake" AND NOT EXISTS "${ACVD_BIN_VTK_DIR}/vtk-config.cmake")
  message(FATAL_ERROR "VTK package config was not found in the prepared SDK: ${ACVD_BIN_VTK_DIR}")
endif()

# Force ACVD to use the uv/build-managed VTK SDK instead of falling back to a
# system VTK installation.
set(VTK_DIR "${ACVD_BIN_VTK_DIR}" CACHE PATH "VTK package directory from the VTK wheel SDK" FORCE)
set(CMAKE_FIND_PACKAGE_NO_PACKAGE_REGISTRY TRUE)
set(CMAKE_FIND_PACKAGE_NO_SYSTEM_PACKAGE_REGISTRY TRUE)

if(NOT DEFINED SKBUILD_PLATLIB_DIR)
  set(SKBUILD_PLATLIB_DIR "${CMAKE_INSTALL_PREFIX}")
endif()

set(ACVD_BIN_NATIVE_DIR "${SKBUILD_PLATLIB_DIR}/acvd_bin/_native")

set(INSTALL_BIN_DIR "${ACVD_BIN_NATIVE_DIR}/bin" CACHE PATH "" FORCE)
set(INSTALL_LIB_DIR "${ACVD_BIN_NATIVE_DIR}/lib" CACHE PATH "" FORCE)
set(INSTALL_INCLUDE_DIR "${ACVD_BIN_NATIVE_DIR}/include" CACHE PATH "" FORCE)
set(INSTALL_CMAKE_DIR "${ACVD_BIN_NATIVE_DIR}/lib/cmake/ACVD" CACHE PATH "" FORCE)
set(INSTALL_DOC_DIR "${ACVD_BIN_NATIVE_DIR}/share/doc/ACVD" CACHE PATH "" FORCE)

set(BUILD_SHARED_LIBS ON CACHE BOOL "" FORCE)
set(BUILD_DOCUMENTATION OFF CACHE BOOL "" FORCE)
set(BUILD_DISCRETEREMESHING ON CACHE BOOL "" FORCE)
set(BUILD_VOLUMEPROCESSING OFF CACHE BOOL "" FORCE)
set(BUILD_EXAMPLES ON CACHE BOOL "" FORCE)

if(UNIX AND NOT APPLE)
  add_compile_definitions(_GLIBCXX_USE_CXX11_ABI=0)
endif()

if(APPLE)
  set(CMAKE_INSTALL_RPATH "@loader_path/../lib;@loader_path/../../../vtkmodules")
elseif(UNIX)
  set(CMAKE_INSTALL_RPATH "$ORIGIN/../lib;$ORIGIN/../../../vtkmodules")
endif()
set(CMAKE_INSTALL_RPATH_USE_LINK_PATH FALSE)

add_subdirectory(third_party/ACVD)
