include_directories(
    ${VTK_INCLUDE_DIR}
    ${VTKSURFACE_INCLUDE_DIR}
    ${VTKDISCRETEREMESHING_INCLUDE_DIR}
)

set(DISCRETEREMESHING_EXAMPLES
ACVD
ACVDP
ACVDQ
ACVDQP
AnisotropicRemeshing
AnisotropicRemeshingQ
AnisotropicRemeshingQP
VolumeAnalysis
)

# The parallel remeshers use vtkMultiThreader. Enabling OpenMP globally only
# parallelizes an optional statistics loop, while adding a libgomp dependency
# to every executable. Keeping that pragma serial avoids an unnecessary
# runtime library and lets auditwheel leave the executable ELF files intact.

foreach(loop_var ${DISCRETEREMESHING_EXAMPLES})
  add_executable(${loop_var} ${loop_var}.cxx)
  vtk_module_autoinit(TARGETS ${loop_var} MODULES "${VTK_LIBRARIES}")
  target_link_libraries(${loop_var} vtkSurface ${VTK_LIBRARIES} )
endforeach(loop_var)

install( TARGETS ${DISCRETEREMESHING_EXAMPLES}
  EXPORT ACVDTargets
  RUNTIME DESTINATION ${INSTALL_BIN_DIR}
  LIBRARY DESTINATION ${INSTALL_LIB_DIR}
  ARCHIVE DESTINATION ${INSTALL_LIB_DIR}
)
