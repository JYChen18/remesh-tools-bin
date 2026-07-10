if(TARGET openvdb_static)
  return()
endif()

include(FetchContent)

set(REMESH_TOOLS_BIN_OPENVDB_VERSION "v8.2.0" CACHE STRING "OpenVDB version used by remesh-tools-bin")
set(REMESH_TOOLS_BIN_TBB_VERSION "v2022.0.0" CACHE STRING "oneTBB version used by remesh-tools-bin")
set(REMESH_TOOLS_BIN_BOOST_VERSION "1.81.0" CACHE STRING "Boost version used by remesh-tools-bin")

set(CMAKE_POSITION_INDEPENDENT_CODE ON CACHE BOOL "" FORCE)

if(POLICY CMP0167)
  cmake_policy(SET CMP0167 NEW)
endif()

set(Boost_USE_STATIC_LIBS ON CACHE BOOL "" FORCE)
set(
  BOOST_INCLUDE_LIBRARIES
  algorithm
  any
  interprocess
  iostreams
  numeric/conversion
  system
  uuid
  CACHE STRING "" FORCE
)
set(BOOST_IOSTREAMS_ENABLE_ZSTD OFF CACHE BOOL "" FORCE)
set(BOOST_IOSTREAMS_ENABLE_LZMA OFF CACHE BOOL "" FORCE)
set(BOOST_IOSTREAMS_ENABLE_BZIP2 OFF CACHE BOOL "" FORCE)

if(WIN32)
  set(REMESH_TOOLS_BIN_BOOST_ARCHIVE "boost-${REMESH_TOOLS_BIN_BOOST_VERSION}.zip")
  set(REMESH_TOOLS_BIN_BOOST_HASH "MD5=375693214b89309d2003f5296422c0a8")
else()
  set(REMESH_TOOLS_BIN_BOOST_ARCHIVE "boost-${REMESH_TOOLS_BIN_BOOST_VERSION}.tar.gz")
  set(REMESH_TOOLS_BIN_BOOST_HASH "MD5=ffac94fbdd92d6bc70a897052022eeba")
endif()

find_package(Boost QUIET COMPONENTS iostreams system)
if(Boost_FOUND)
  message(STATUS "Boost found, skipping source fetch.")
else()
  FetchContent_Declare(
    boost
    URL "https://github.com/boostorg/boost/releases/download/boost-${REMESH_TOOLS_BIN_BOOST_VERSION}/${REMESH_TOOLS_BIN_BOOST_ARCHIVE}"
    URL_HASH "${REMESH_TOOLS_BIN_BOOST_HASH}"
    OVERRIDE_FIND_PACKAGE
    EXCLUDE_FROM_ALL
  )
  FetchContent_MakeAvailable(boost)
endif()

set(TBB_TEST OFF CACHE BOOL "" FORCE)
set(TBB_EXAMPLES OFF CACHE BOOL "" FORCE)
set(TBB_STRICT OFF CACHE BOOL "" FORCE)
set(TBBMALLOC_BUILD OFF CACHE BOOL "" FORCE)
set(TBBMALLOC_PROXY_BUILD OFF CACHE BOOL "" FORCE)
set(TBB4PY_BUILD OFF CACHE BOOL "" FORCE)
set(TBB_INSTALL OFF CACHE BOOL "" FORCE)
set(TBB_FIND_PACKAGE OFF CACHE BOOL "" FORCE)

set(BUILD_SHARED_LIBS ON CACHE BOOL "" FORCE)
FetchContent_Declare(
  tbb
  GIT_REPOSITORY https://github.com/oneapi-src/oneTBB.git
  GIT_TAG "${REMESH_TOOLS_BIN_TBB_VERSION}"
  EXCLUDE_FROM_ALL
)
FetchContent_MakeAvailable(tbb)

if(TARGET tbb)
  install(
    TARGETS tbb
    RUNTIME DESTINATION "${INSTALL_BIN_DIR}"
    LIBRARY DESTINATION "${INSTALL_LIB_DIR}"
    ARCHIVE DESTINATION "${INSTALL_LIB_DIR}"
  )
endif()

if(WIN32 AND NOT TARGET Boost::disable_autolinking)
  add_library(remesh_tools_bin_boost_disable_autolinking INTERFACE)
  target_compile_definitions(
    remesh_tools_bin_boost_disable_autolinking
    INTERFACE BOOST_ALL_NO_LIB
  )
  add_library(Boost::disable_autolinking ALIAS remesh_tools_bin_boost_disable_autolinking)
endif()

set(BUILD_SHARED_LIBS OFF CACHE BOOL "" FORCE)
set(OPENVDB_BUILD_CORE ON CACHE BOOL "" FORCE)
set(OPENVDB_CORE_STATIC ON CACHE BOOL "" FORCE)
set(OPENVDB_CORE_SHARED OFF CACHE BOOL "" FORCE)
set(OPENVDB_BUILD_BINARIES OFF CACHE BOOL "" FORCE)
set(OPENVDB_BUILD_PYTHON_MODULE OFF CACHE BOOL "" FORCE)
set(OPENVDB_BUILD_UNITTESTS OFF CACHE BOOL "" FORCE)
set(OPENVDB_BUILD_DOCS OFF CACHE BOOL "" FORCE)
set(OPENVDB_BUILD_HOUDINI_PLUGIN OFF CACHE BOOL "" FORCE)
set(OPENVDB_BUILD_HOUDINI_ABITESTS OFF CACHE BOOL "" FORCE)
set(OPENVDB_BUILD_AX OFF CACHE BOOL "" FORCE)
set(OPENVDB_BUILD_AX_BINARIES OFF CACHE BOOL "" FORCE)
set(OPENVDB_BUILD_AX_UNITTESTS OFF CACHE BOOL "" FORCE)
set(OPENVDB_BUILD_MAYA_PLUGIN OFF CACHE BOOL "" FORCE)
set(OPENVDB_INSTALL_CMAKE_MODULES OFF CACHE BOOL "" FORCE)
set(OPENVDB_ENABLE_UNINSTALL OFF CACHE BOOL "" FORCE)
set(OPENVDB_FUTURE_DEPRECATION OFF CACHE BOOL "" FORCE)
set(OPENVDB_CXX_STRICT OFF CACHE BOOL "" FORCE)
set(USE_BLOSC OFF CACHE BOOL "" FORCE)
set(USE_ZLIB OFF CACHE BOOL "" FORCE)
set(USE_LOG4CPLUS OFF CACHE BOOL "" FORCE)
set(USE_IMATH_HALF OFF CACHE BOOL "" FORCE)
set(USE_STATIC_DEPENDENCIES ON CACHE BOOL "" FORCE)
set(USE_PKGCONFIG OFF CACHE BOOL "" FORCE)

FetchContent_Declare(
  openvdb
  GIT_REPOSITORY https://github.com/AcademySoftwareFoundation/openvdb.git
  GIT_TAG "${REMESH_TOOLS_BIN_OPENVDB_VERSION}"
  PATCH_COMMAND
    "${Python_EXECUTABLE}" "${PROJECT_SOURCE_DIR}/cmake/scripts/patch_openvdb_cmake.py"
    "<SOURCE_DIR>/openvdb/openvdb/CMakeLists.txt"
  EXCLUDE_FROM_ALL
)
FetchContent_MakeAvailable(openvdb)

set_target_properties(openvdb_static PROPERTIES POSITION_INDEPENDENT_CODE ON)

# Boost's modular CMake targets expose only their own and declared dependency
# include directories. OpenVDB 8 also includes these header-only libraries
# directly, so restore the include propagation provided by classic FindBoost.
foreach(
  REMESH_TOOLS_BIN_BOOST_HEADER_COMPONENT
  IN ITEMS algorithm any interprocess numeric_conversion uuid
)
  if(TARGET "Boost::${REMESH_TOOLS_BIN_BOOST_HEADER_COMPONENT}")
    target_link_libraries(
      openvdb_static
      PUBLIC "Boost::${REMESH_TOOLS_BIN_BOOST_HEADER_COMPONENT}"
    )
  endif()
endforeach()
