import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    # Obtener la ruta del paquete instalado en el share
    pkg_share = get_package_share_directory('my_arm_description')
    urdf_file = os.path.join(pkg_share, 'urdf', 'my_arm.urdf')

    # Leer el archivo URDF
    with open(urdf_file, 'r') as infp:
        robot_desc = infp.read()

    return LaunchDescription([
        # Publicador del estado del robot (procesa el URDF y genera las TF)
        Node(
            package='robot_state_publisher',
            executable='robot_state_publisher',
            name='robot_state_publisher',
            output='screen',
            parameters=[{'robot_description': robot_desc}]
        ),
        # Interfaz gráfica para mover los joints manualmente con barras deslizantes
        Node(
            package='joint_state_publisher_gui',
            executable='joint_state_publisher_gui',
            name='joint_state_publisher_gui'
        ),
        # RViz2 para la visualización 3D
        Node(
            package='rviz2',
            executable='rviz2',
            name='rviz2',
            output='screen'
        )
    ])