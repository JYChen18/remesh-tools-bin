include("${PROJECT_SOURCE_DIR}/cmake/deps/openvdb.cmake")

add_executable(OpenVDBSdfRemesh "${PROJECT_SOURCE_DIR}/native/openvdb/openvdb_preprocess.cpp")
target_compile_features(OpenVDBSdfRemesh PRIVATE cxx_std_17)
target_link_libraries(OpenVDBSdfRemesh PRIVATE openvdb_static)

install(
  TARGETS OpenVDBSdfRemesh
  RUNTIME DESTINATION "${INSTALL_BIN_DIR}"
)
