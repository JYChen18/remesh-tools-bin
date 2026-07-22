include("${CMAKE_CURRENT_LIST_DIR}/openvdb_dependencies.cmake")

add_executable(
  OpenVDBSdfRemesh
  "${CMAKE_CURRENT_LIST_DIR}/../src/openvdb_sdf_remesh.cpp"
)
target_compile_features(OpenVDBSdfRemesh PRIVATE cxx_std_17)
target_link_libraries(OpenVDBSdfRemesh PRIVATE openvdb_static)

if(MSVC)
  target_compile_options(OpenVDBSdfRemesh PRIVATE /bigobj)
endif()

install(
  TARGETS OpenVDBSdfRemesh
  RUNTIME DESTINATION "${INSTALL_BIN_DIR}"
)
