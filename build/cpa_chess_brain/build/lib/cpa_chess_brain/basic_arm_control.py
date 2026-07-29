#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
import time

# Importamos los mensajes de accion necesarios
from moveit_msgs.action import MoveGroup
from moveit_msgs.msg import Constraints, PositionConstraint, JointConstraint, OrientationConstraint
from control_msgs.action import GripperCommand
from geometry_msgs.msg import PoseStamped
from shape_msgs.msg import SolidPrimitive
from moveit_msgs.msg import MotionPlanRequest

class ChessArmController(Node):

    def __init__(self):
        super().__init__('chess_arm_controller_node')
        self.get_logger().info('Chess Arm Brain Node has been initialized!')
        
        # 1. Action Client for MoveIt (Arm joints 1 to 4)
        self._arm_action_client = ActionClient(self, MoveGroup, 'move_action')
        
        # 2. Action Client for the Gripper (Left finger joint)
        self._gripper_action_client = ActionClient(self, GripperCommand, 'gripper_controller/gripper_cmd')

    def move_to_home(self):
        self.get_logger().info('Sending ARM to HOME position...')
        
        # Wait for the action server to be available
        if not self._arm_action_client.wait_for_server(timeout_sec=5.0):
            self.get_logger().error('Action server /move_action not available!')
            return

        # Build the goal message for MoveIt
        goal_msg = MoveGroup.Goal()
        goal_msg.request.group_name = 'arm'
        
        # Define target joint positions for HOME (all 4 joints to 0.0 radians)
        home_joints = [0.0, 0.0, 0.0, 0.0]
        joint_names = ['joint_1', 'joint_2', 'joint_3', 'joint_4']
        
        joint_constraints = Constraints()
        for name, position in zip(joint_names, home_joints):
            constraint = JointConstraint()
            constraint.joint_name = name
            constraint.position = position
            constraint.tolerance_above = 0.01
            constraint.tolerance_below = 0.01
            constraint.weight = 1.0
            joint_constraints.joint_constraints.append(constraint)
            
        goal_msg.request.goal_constraints.append(joint_constraints)
        
        # We only want to plan and execute immediately
        goal_msg.planning_options.plan_only = False

        # Send the goal asynchronously
        self.get_logger().info('Planning and executing home trajectory...')
        send_goal_future = self._arm_action_client.send_goal_async(goal_msg)
        rclpy.spin_until_future_complete(self, send_goal_future)
        
        goal_handle = send_goal_future.result()
        if not goal_handle.accepted:
            self.get_logger().error('Home trajectory goal rejected by MoveIt!')
            return

        self.get_logger().info('Trajectory accepted, moving...')
        get_result_future = goal_handle.get_result_async()
        rclpy.spin_until_future_complete(self, get_result_future)
        self.get_logger().info('ARM successfully arrived HOME!')
    
    def move_to_cartesian_pose(self, x, y, z):
        self.get_logger().info(f'Planning trajectory to Cartesian Position: X={x}, Y={y}, Z={z}')
        
        if not self._arm_action_client.wait_for_server(timeout_sec=5.0):
            self.get_logger().error('Action server /move_action not available!')
            return

        goal_msg = MoveGroup.Goal()
        
        # 1. Configurar la petición básica del planificador
        request = MotionPlanRequest()
        request.group_name = 'arm'
        request.num_planning_attempts = 10     # Más intentos para asegurar
        request.allowed_planning_time = 5.0      # Más tiempo para pensar
        request.max_velocity_scaling_factor = 0.5
        request.max_acceleration_scaling_factor = 0.5

        # 2. Configurar la pose objetivo de forma limpia
        target_pose = PoseStamped()
        target_pose.header.frame_id = 'base_link'
        target_pose.header.stamp = self.get_clock().now().to_msg()
        target_pose.pose.position.x = x
        target_pose.pose.position.y = y
        target_pose.pose.position.z = z
        
        # IMPORTANTE: Usamos un quaternion neutro (identidad) para que MoveIt 
        # decida libremente la mejor orientación que le sea cómoda a tu estructura de 4 GDL
        target_pose.pose.orientation.x = 0.0
        target_pose.pose.orientation.y = 0.0  
        target_pose.pose.orientation.z = 0.0
        target_pose.pose.orientation.w = 1.0

        # 3. Formatear las restricciones de la forma más limpia aceptada por OMPL
        global_constraints = Constraints()
        global_constraints.name = "simple_cartesian_target"

        # Construimos una restricción de posición directa
        from moveit_msgs.msg import PositionConstraint
        pos_con = PositionConstraint()
        pos_con.header.frame_id = "base_link"
        pos_con.link_name = "link_4"
        pos_con.weight = 1.0
        
        # Definimos una caja de tolerancia de 1 cm centrada EXACTAMENTE en la pose destino
        box_primitive = SolidPrimitive()
        box_primitive.type = SolidPrimitive.BOX
        box_primitive.dimensions = [0.01, 0.01, 0.01] 
        
        pos_con.constraint_region.primitives.append(box_primitive)
        pos_con.constraint_region.primitive_poses.append(target_pose.pose) # Esto amarra la caja al destino
        
        global_constraints.position_constraints.append(pos_con)
        request.goal_constraints.append(global_constraints)
        
        # Suministrar el estado inicial actual (Muy recomendado por el log anterior)
        request.start_state.is_diff = True 
        
        goal_msg.request = request
        goal_msg.planning_options.plan_only = False

        # 4. Enviar meta de forma asíncrona
        self.get_logger().info('Sending optimized Cartesian Request to MoveIt Core...')
        send_goal_future = self._arm_action_client.send_goal_async(goal_msg)
        rclpy.spin_until_future_complete(self, send_goal_future)
        
        goal_handle = send_goal_future.result()
        if not goal_handle.accepted:
            self.get_logger().error('Cartesian Goal was REJECTED by MoveIt!')
            return

        self.get_logger().info('Trajectory accepted by OMPL! Executing...')
        get_result_future = goal_handle.get_result_async()
        rclpy.spin_until_future_complete(self, get_result_future)
        
        # Analizamos el resultado final de la acción
        result = get_result_future.result()
        if result.result.error_code.val == 1: # 1 es el código de SUCCESS en MoveIt
            self.get_logger().info('ARM successfully arrived at the Cartesian coordinate!')
        else:
            self.get_logger().error(f'Planning failed with MoveIt error code: {result.result.error_code.val}')
        

    def control_gripper(self, open_gripper=True):
        # Wait for the gripper action server
        if not self._gripper_action_client.wait_for_server(timeout_sec=5.0):
            self.get_logger().error('Action server gripper_cmd not available!')
            return

        goal_msg = GripperCommand.Goal()
        
        if open_gripper:
            self.get_logger().info('Sending order: OPEN Gripper...')
            goal_msg.command.position = 0.0  # 0.0 rad means fully open
        else:
            self.get_logger().info('Sending order: CLOSE Gripper...')
            goal_msg.command.position = 0.52 # 0.52 rad means closed/gripping
            
        goal_msg.command.max_effort = -1.0 # Max effort limits (-1.0 uses default)

        # Send goal and wait for execution
        send_goal_future = self._gripper_action_client.send_goal_async(goal_msg)
        rclpy.spin_until_future_complete(self, send_goal_future)
        
        goal_handle = send_goal_future.result()
        if not goal_handle.accepted:
            self.get_logger().error('Gripper command rejected!')
            return

        get_result_future = goal_handle.get_result_async()
        rclpy.spin_until_future_complete(self, get_result_future)
        self.get_logger().info('Gripper target position reached!')

def main(args=None):
    rclpy.init(args=args)
    node = ChessArmController()
    
    try:
        print("\n==============================================")
        print("    STARTING INTERACTIVE CARTESIAN CONTROL    ")
        print("==============================================\n")
        
        # 1. Secuencia de Inicialización obligatoria
        print("[INIT] Opening gripper...")
        node.control_gripper(open_gripper=True)
        time.sleep(1.0)
        
        print("[INIT] Moving arm to HOME position...")
        node.move_to_home()
        time.sleep(1.0)
        
        print("\n--> Initialization complete. System ready.")
        print("--> You can exit the program at any time using Ctrl+C.\n")
        
        # 2. Loop constante interactivo
        while rclpy.ok():
            print("----------------------------------------------")
            print("Enter target Cartesian coordinates (in meters):")
            
            try:
                # Capturamos las entradas del usuario por consola
                user_x = input("Target X (e.g., 0.18): ")
                user_y = input("Target Y (e.g., 0.0):  ")
                user_z = input("Target Z (e.g., 0.10): ")
                
                # Convertimos los strings a flotantes numéricos
                x = float(user_x)
                y = float(user_y)
                z = float(user_z)
                
                print(f"\n[COMMAND] Sending target to node: X={x} m, Y={y} m, Z={z} m")
                
                # Ejecutamos el movimiento cartesiano a través de la API
                node.move_to_cartesian_pose(x=x, y=y, z=z)
                
                # Pequeño delay de asentamiento antes de pedir la siguiente coordenada
                time.sleep(0.5)
                
            except ValueError:
                print("\n[ERROR] Invalid input! Please enter numeric values only (e.g., 0.15).")
                print("Let's try again...\n")
                continue

    except KeyboardInterrupt:
        print("\n\n==============================================")
        node.get_logger().info('KeyboardInterrupt detected. Shutting down Chess Arm Node safely.')
        print("==============================================\n")
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()