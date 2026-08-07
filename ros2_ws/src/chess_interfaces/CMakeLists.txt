cmake_minimum_required(VERSION 3.8)
project(chess_interfaces)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# Dependencias necesarias para generar mensajes y acciones
find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)

# Definición de interfaces custom
rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/GameFault.msg"
  "msg/GameStatus.msg"
  "msg/RobotTurnResult.msg"
  "action/MovePiece.action"
  "msg/ValidatedMove.msg"
)

ament_export_dependencies(rosidl_default_runtime)

ament_package()