cmake_minimum_required(VERSION 3.0.2)
project(umi_dex)

find_package(catkin REQUIRED COMPONENTS
  rospy
  std_msgs
  sensor_msgs
  message_generation
)

add_message_files(FILES
  HandJointState.msg
)

catkin_python_setup()

generate_messages(DEPENDENCIES
  std_msgs
)

catkin_package(CATKIN_DEPENDS
  rospy
  std_msgs
  sensor_msgs
  message_runtime
)

catkin_install_python(PROGRAMS
  nodes/can_controller_node
  nodes/bag_extract_node
  nodes/interactive_capture_node
  DESTINATION ${CATKIN_PACKAGE_BIN_DESTINATION}
)

install(DIRECTORY launch/ DESTINATION ${CATKIN_PACKAGE_SHARE_DESTINATION}/launch)
install(DIRECTORY config/ DESTINATION ${CATKIN_PACKAGE_SHARE_DESTINATION}/config)
