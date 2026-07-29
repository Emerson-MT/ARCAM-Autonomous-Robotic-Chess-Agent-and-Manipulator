#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
import time

# Importamos los mensajes de acción y servicios necesarios
from moveit_msgs.action import MoveGroup
from moveit_msgs.msg import Constraints, JointConstraint
from moveit_msgs.srv import GetPositionIK
from moveit_msgs.msg import PositionIKRequest
from control_msgs.action import GripperCommand

class ChessArmController(Node):

    def __init__(self):
        super().__init__('chess_arm_controller_node')
        self.get_logger().info('Chess Arm Brain Node has been initialized!')
        
        # 1. Action Client para mover las articulaciones del brazo
        self._arm_action_client = ActionClient(self, MoveGroup, 'move_action')
        
        # 2. Action Client para el Gripper
        self._gripper_action_client = ActionClient(self, GripperCommand, 'gripper_controller/gripper_cmd')

        # 3. Cliente del Servicio de Cinemática Inversa (/compute_ik)
        self._ik_client = self.create_client(GetPositionIK, 'compute_ik')

    def move_to_home(self):
        self.get_logger().info('Sending ARM to HOME position...')
        home_joints = [0.0, 0.0, 0.0, 0.0]
        joint_names = ['joint_1', 'joint_2', 'joint_3', 'joint_4']
        self.move_to_joint_targets(joint_names, home_joints)

    def move_to_cartesian_pose(self, x, y, z):
        self.get_logger().info(f'Calculando IK para posición cartesiana: X={x}, Y={y}, Z={z}')
        
        # Esperamos al servicio de IK
        if not self._ik_client.wait_for_service(timeout_sec=5.0):
            self.get_logger().error('¡El servicio /compute_ik no está disponible!')
            return

        # 1. Armamos la petición de IK directa
        srv_req = GetPositionIK.Request()
        ik_req = PositionIKRequest()
        ik_req.group_name = 'arm'
        ik_req.ik_link_name = 'link_4'
        ik_req.avoid_collisions = True

        ik_req.pose_stamped.header.frame_id = 'base_link'
        ik_req.pose_stamped.header.stamp = self.get_clock().now().to_msg()
        ik_req.pose_stamped.pose.position.x = float(x)
        ik_req.pose_stamped.pose.position.y = float(y)
        ik_req.pose_stamped.pose.position.z = float(z)

        # Inyectamos la orientación física real que tiene tu efector final
        ik_req.pose_stamped.pose.orientation.x = 0.0
        ik_req.pose_stamped.pose.orientation.y = 0.724
        ik_req.pose_stamped.pose.orientation.z = 0.0
        ik_req.pose_stamped.pose.orientation.w = 0.690

        srv_req.ik_request = ik_req

        # 2. Consultamos la solución de forma asíncrona
        future = self._ik_client.call_async(srv_req)
        rclpy.spin_until_future_complete(self, future)
        response = future.result()

        # 3. Verificamos si existe solución
        if response.error_code.val != 1:
            self.get_logger().error(f'Fallo al calcular IK. Código de error: {response.error_code.val}')
            return

        # 4. Extraemos los ángulos calculados por el solver
        joint_names = response.solution.joint_state.name
        joint_positions = response.solution.joint_state.position

        self.get_logger().info('¡IK Resuelta exitosamente! Enviando trayectoria de articulaciones...')

        # 5. Mandamos a ejecutar el movimiento en el espacio de articulaciones
        self.move_to_joint_targets(joint_names, joint_positions)

    def move_to_joint_targets(self, names, positions):
        if not self._arm_action_client.wait_for_server(timeout_sec=5.0):
            self.get_logger().error('¡El servidor /move_action no está disponible!')
            return

        goal_msg = MoveGroup.Goal()
        goal_msg.request.group_name = 'arm'
        
        joint_constraints = Constraints()
        for name, pos in zip(names, positions):
            if name in ['joint_1', 'joint_2', 'joint_3', 'joint_4']:
                c = JointConstraint()
                c.joint_name = name
                c.position = pos
                c.tolerance_above = 0.01
                c.tolerance_below = 0.01
                c.weight = 1.0
                joint_constraints.joint_constraints.append(c)

        goal_msg.request.goal_constraints.append(joint_constraints)
        goal_msg.planning_options.plan_only = False

        send_goal_future = self._arm_action_client.send_goal_async(goal_msg)
        rclpy.spin_until_future_complete(self, send_goal_future)
        
        goal_handle = send_goal_future.result()
        if not goal_handle.accepted:
            self.get_logger().error('Goal rechazado por MoveIt!')
            return

        get_result_future = goal_handle.get_result_async()
        rclpy.spin_until_future_complete(self, get_result_future)
        self.get_logger().info('¡Movimiento completado con éxito!')

    def control_gripper(self, open_gripper=True):
        if not self._gripper_action_client.wait_for_server(timeout_sec=5.0):
            self.get_logger().error('Servidor gripper_cmd no disponible!')
            return

        goal_msg = GripperCommand.Goal()
        
        if open_gripper:
            self.get_logger().info('Abriendo Gripper...')
            goal_msg.command.position = 0.0
        else:
            self.get_logger().info('Cerrando Gripper...')
            goal_msg.command.position = 0.52
            
        goal_msg.command.max_effort = -1.0

        send_goal_future = self._gripper_action_client.send_goal_async(goal_msg)
        rclpy.spin_until_future_complete(self, send_goal_future)
        
        goal_handle = send_goal_future.result()
        if not goal_handle.accepted:
            self.get_logger().error('Comando del gripper rechazado!')
            return

        get_result_future = goal_handle.get_result_async()
        rclpy.spin_until_future_complete(self, get_result_future)
        self.get_logger().info('Gripper llegó a la posición deseada!')

def main(args=None):
    rclpy.init(args=args)
    node = ChessArmController()
    
    try:
        print("\n==============================================")
        print("    STARTING INTERACTIVE CARTESIAN CONTROL    ")
        print("==============================================\n")
        
        print("[INIT] Opening gripper...")
        node.control_gripper(open_gripper=True)
        time.sleep(1.0)
        
        print("[INIT] Moving arm to HOME position...")
        node.move_to_home()
        time.sleep(1.0)
        
        print("\n--> Initialization complete. System ready.\n")
        
        while rclpy.ok():
            print("----------------------------------------------")
            print("Enter target Cartesian coordinates (in meters):")
            
            try:
                user_x = input("Target X (e.g., 0.061): ")
                user_y = input("Target Y (e.g., 0.0):   ")
                user_z = input("Target Z (e.g., 0.531): ")
                
                x = float(user_x)
                y = float(user_y)
                z = float(user_z)
                
                print(f"\n[COMMAND] Moving to X={x} m, Y={y} m, Z={z} m")
                node.move_to_cartesian_pose(x=x, y=y, z=z)
                time.sleep(0.5)
                
            except ValueError:
                print("\n[ERROR] Entradas inválidas. Introduce solo números.")
                continue

    except KeyboardInterrupt:
        node.get_logger().info('Apagando nodo...')
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()