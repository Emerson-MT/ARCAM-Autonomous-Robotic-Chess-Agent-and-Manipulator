import asyncio
import json
import threading

import rclpy
from rclpy.node import Node

from std_msgs.msg import String, Float64MultiArray

from rclpy.action import ActionClient
from chess_interfaces.action import MovePiece

from chess_interfaces.msg import GameFault, GameStatus, ValidatedMove

import websockets


class DashboardGuiNode(Node):
    """
    Nodo Middleware (Puente) entre ROS 2 y el frontend React.

    Responsabilidades:
    - Mantiene un servidor WebSocket para comunicarse con la interfaz web.
    - Convierte los mensajes de ROS 2 a formato JSON y los envía al Dashboard.
    - Recibe comandos desde el Dashboard y los publica en los tópicos de ROS 2.
    - Guarda el último estado conocido para actualizar el Dashboard rápidamente
      cuando se recarga la página.
    """

    def __init__(self):
        super().__init__("dashboard_gui_node")

        # ---------------------------------------------------------------------
        # Configuración WebSocket
        # ---------------------------------------------------------------------
        self.websocket_host = "0.0.0.0"
        self.websocket_port = 8765

        # Usamos asyncio para que la conexión web funcione en paralelo 
        # sin interrumpir el funcionamiento normal de ROS 2.
        self.websocket_loop = asyncio.new_event_loop()
        self.websocket_server = None
        self.connected_clients = set()

        # ---------------------------------------------------------------------
        # Suscriptores ROS 2 → Dashboard
        # ---------------------------------------------------------------------
        self.sub_game_status = self.create_subscription(
            GameStatus,
            "/game_status",
            self.game_status_callback,
            10
        )

        self.sub_game_fault = self.create_subscription(
            GameFault,
            "/game_fault",
            self.game_fault_callback,
            10
        )

        self.sub_validated_board = self.create_subscription(
            String,
            "/validated_boardState",
            self.validated_board_callback,
            10
        )

        self.sub_validated_move = self.create_subscription(
            ValidatedMove,
            "/validated_move",
            self.validated_move_callback,
            10
        )

        # ---------------------------------------------------------------------
        # Publicadores Dashboard → ROS 2
        # ---------------------------------------------------------------------
        self.pub_user_command_speech = self.create_publisher(
            String,
            "/user_command_speech",
            10
        )

        self.pub_manual_joint_command = self.create_publisher(
            Float64MultiArray,
            "/manual_joint_command",
            10
        )

        self.move_arm_client = ActionClient(
            self,
            MovePiece,
            "/move_arm_action"
        )

        self.pub_manual_square_command = self.create_publisher(
            String,
            "/manual_square_command",
            10
        )

        self.pub_engine_difficulty = self.create_publisher(
            String,
            "/engine_difficulty",
            10
        )

        # ---------------------------------------------------------------------
        # Caché de Estados (Últimos valores conocidos)
        # --------------------------------------------------------------------- 
        self.last_game_status = None
        self.last_game_fault = None
        self.last_validated_fen = None
        self.last_validated_move = None

        # ---------------------------------------------------------------------
        # Iniciar servidor WebSocket en hilo separado
        # ---------------------------------------------------------------------
        self.websocket_thread = threading.Thread(
            target=self.start_websocket_server,
            daemon=True
        )
        self.websocket_thread.start()

        self.get_logger().info(
            f"Dashboard GUI Node iniciado. WebSocket en ws://localhost:{self.websocket_port}"
        )

    # -------------------------------------------------------------------------
    # Servidor WebSocket
    # -------------------------------------------------------------------------

    def start_websocket_server(self):
        """
        Inicia el servidor WebSocket en un hilo separado.
        """
        asyncio.set_event_loop(self.websocket_loop)

        self.websocket_loop.run_until_complete(
            self.create_websocket_server()
        )

        self.websocket_loop.run_forever()

    async def create_websocket_server(self):
        """
        Levanta la conexión en el puerto especificado para escuchar al dashboard.
        """
        self.websocket_server = await websockets.serve(
            self.websocket_handler,
            self.websocket_host,
            self.websocket_port
        )

        self.get_logger().info(
            f"Servidor WebSocket activo en puerto {self.websocket_port}"
        )

    async def websocket_handler(self, websocket, path=None):
        """
        Atiende a cada cliente (React) que se conecta y escucha sus mensajes.
        """
        self.connected_clients.add(websocket)
        self.get_logger().info("Cliente dashboard conectado.")

        # Hidratar al cliente con el contexto actual apenas entra
        await self.enviar_estado_inicial(websocket)

        try:
            async for message in websocket:
                await self.procesar_mensaje_frontend(websocket, message)

        except websockets.exceptions.ConnectionClosed:
            pass

        finally:
            self.connected_clients.discard(websocket)
            self.get_logger().info("Cliente dashboard desconectado.")

    async def enviar_estado_inicial(self, websocket):
        """
        Envía los últimos datos conocidos al cliente para que no vea la pantalla
        vacía al conectarse.
        """
        await websocket.send(json.dumps({
            "type": "connection_status",
            "payload": {
                "connected": True,
                "message": "Dashboard conectado a ROS 2"
            }
        }))

        if self.last_game_status is not None:
            await websocket.send(json.dumps({
                "type": "game_status",
                "payload": self.last_game_status
            }))

        if self.last_validated_fen is not None:
            await websocket.send(json.dumps({
                "type": "validated_board_state",
                "payload": self.last_validated_fen
            }))

        if self.last_game_fault is not None:
            await websocket.send(json.dumps({
                "type": "game_fault",
                "payload": self.last_game_fault
            }))

    async def procesar_mensaje_frontend(self, websocket, message):
        """
        Lee los comandos JSON enviados desde React y ejecuta la acción en ROS 2.
        """
        try:
            data = json.loads(message)

        except json.JSONDecodeError:
            await self.enviar_error_frontend(
                websocket,
                "Mensaje JSON inválido."
            )
            return

        message_type = data.get("type")
        payload = data.get("payload", {})

        if message_type == "user_command_speech":
            self.publicar_user_command_speech(payload)

        elif message_type == "manual_joint_command":
            self.publicar_manual_joint_command(payload)

        elif message_type == "spatial_command":
            self.procesar_spatial_command(payload)

        elif message_type == "engine_difficulty":
            self.publicar_engine_difficulty(payload)

        elif message_type == "ping":
            await websocket.send(json.dumps({
                "type": "pong",
                "payload": {
                    "message": "dashboard_gui_node activo"
                }
            }))

        else:
            await self.enviar_error_frontend(
                websocket,
                f"Tipo de mensaje no reconocido: {message_type}"
            )

    async def enviar_error_frontend(self, websocket, error_message):
        """
        Envía un mensaje de error a la interfaz web.
        """
        await websocket.send(json.dumps({
            "type": "dashboard_error",
            "payload": {
                "message": error_message
            }
        }))

    def enviar_a_frontend(self, message_type, payload):
        """
        Prepara un mensaje para enviarlo a todos los clientes web conectados.
        """
        if not self.connected_clients:
            return

        message = json.dumps({
            "type": message_type,
            "payload": payload
        })

        asyncio.run_coroutine_threadsafe(
            self.broadcast(message),
            self.websocket_loop
        )

    async def broadcast(self, message):
        """
        Envía físicamente el mensaje a todos los clientes y desconecta
        automáticamente a los que hayan perdido conexión.
        """
        disconnected_clients = []

        for client in self.connected_clients:
            try:
                await client.send(message)
            except websockets.exceptions.ConnectionClosed:
                disconnected_clients.append(client)

        for client in disconnected_clients:
            self.connected_clients.discard(client)

    # -------------------------------------------------------------------------
    # Callbacks ROS 2 → Dashboard
    # -------------------------------------------------------------------------
    def game_status_callback(self, msg):
        """
        Envía el estado actual de la partida (de quién es el turno) al dashboard.
        """
        payload = {
            "game_state": msg.game_state,
            "current_turn": msg.current_turn,
            "move_number": int(msg.move_number)
        }

        self.last_game_status = payload
        self.enviar_a_frontend("game_status", payload)

    def game_fault_callback(self, msg):
        """
        Avisa al dashboard si el árbitro detectó un movimiento ilegal o falta.
        """
        payload = {
            "error_code": int(msg.error_code),
            "error_message": msg.error_message,
            "faulty_square": msg.faulty_square
        }

        self.last_game_fault = payload
        self.enviar_a_frontend("game_fault", payload)

    def validated_board_callback(self, msg):
        """
        Recibe el tablero validado en formato FEN.
        """
        payload = {
            "fen": msg.data
        }

        self.last_validated_fen = payload
        self.enviar_a_frontend("validated_board_state", payload)

    def validated_move_callback(self, msg):
        """
        Envía la última jugada confirmada para actualizar el historial en la web.
        """
        payload = {
            "uci": msg.uci,
            "san": msg.san,
            "color": msg.color,
            "actor": msg.actor,
            "move_number": int(msg.move_number),
            "is_capture": bool(msg.is_capture),
            "is_check": bool(msg.is_check),
            "is_checkmate": bool(msg.is_checkmate),
            "fen_after": msg.fen_after
        }

        self.last_validated_move = payload
        self.enviar_a_frontend("validated_move", payload)

    # -------------------------------------------------------------------------
    # Comandos Dashboard → ROS 2
    # -------------------------------------------------------------------------

    def publicar_user_command_speech(self, payload):
        """
        Publica comandos de texto enviados desde la interfaz hacia ROS 2.
        """
        command = payload.get("command", "")

        if not command:
            self.get_logger().warning(
                "Comando user_command_speech vacío recibido desde dashboard."
            )
            return

        msg = String()
        msg.data = command

        self.pub_user_command_speech.publish(msg)

        self.get_logger().info(
            f"Comando publicado en /user_command_speech: {command}"
        )

    def publicar_manual_joint_command(self, payload):
        """
        Publica el movimiento manual de los motores proveniente de los sliders 
        del modo Debug en el dashboard.
        """
        joints = payload.get("joints", [])

        if not isinstance(joints, list):
            self.get_logger().warning(
                "manual_joint_command inválido: se esperaba una lista."
            )
            return

        try:
            joint_values = [float(value) for value in joints]

        except ValueError:
            self.get_logger().warning(
                "manual_joint_command contiene valores no numéricos."
            )
            return

        msg = Float64MultiArray()
        msg.data = joint_values

        self.pub_manual_joint_command.publish(msg)

        self.get_logger().info(
            f"Comando publicado en /manual_joint_command: {joint_values}"
        )

    def procesar_spatial_command(self, payload):
        """
        Procesa comandos espaciales desde Debug Mode.
        GOTO se publica como tópico.
        MOVE se envía como action /move_arm_action.
        """
        command_type = payload.get("command_type", "")

        if command_type == "goto":
            self.publicar_manual_square_command(payload)
            return

        if command_type == "move":
            self.enviar_move_piece_action(payload)
            return

        self.get_logger().warning(
            f"spatial_command inválido: command_type={command_type}"
        )

    def publicar_manual_square_command(self, payload):
        """
        Publica una coordenada objetivo para probar la cinemática del brazo (GOTO).
        """
        target_square = payload.get("target_square", "")

        if not target_square:
            self.get_logger().warning(
                "manual_square_command inválido: falta target_square."
            )
            return

        msg = String()
        msg.data = target_square

        self.pub_manual_square_command.publish(msg)

        self.get_logger().info(
            f"Comando publicado en /manual_square_command: GOTO {target_square}"
        )

    def enviar_move_piece_action(self, payload):
        """
        Envía una orden completa de movimiento (agarrar pieza en A y soltar en B)
        al action server /move_arm_action.
        """
        source_square = payload.get("source_square", "")
        target_square = payload.get("target_square", "")
        is_capture = bool(payload.get("is_capture", False))

        if not source_square or not target_square:
            self.get_logger().warning(
                "move_piece_command inválido: falta source_square o target_square."
            )
            return

        if not self.move_arm_client.wait_for_server(timeout_sec=1.0):
            self.get_logger().error(
                "Action server /move_arm_action no disponible."
            )
            return

        goal_msg = MovePiece.Goal()
        goal_msg.source_square = source_square
        goal_msg.target_square = target_square
        goal_msg.is_capture = is_capture

        self.get_logger().info(
            f"Enviando MOVE desde dashboard: {source_square} -> {target_square}, captura={is_capture}"
        )

        send_goal_future = self.move_arm_client.send_goal_async(goal_msg)
        send_goal_future.add_done_callback(self.move_piece_goal_response_callback)

    def move_piece_goal_response_callback(self, future):
        """
        Verifica si el action server aceptó el goal enviado desde dashboard.
        """
        goal_handle = future.result()

        if not goal_handle.accepted:
            self.get_logger().error(
                "El action server rechazó el comando MOVE enviado desde dashboard."
            )
            return

        self.get_logger().info(
            "Comando MOVE aceptado por /move_arm_action. Esperando resultado..."
        )

        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(self.move_piece_result_callback)


    def move_piece_result_callback(self, future):
        """
        Avisa en la terminal de ROS si el brazo terminó el movimiento correctamente.
        """
        try:
            result = future.result().result
            success = bool(result.success)

        except Exception as e:
            self.get_logger().error(
                f"Error recibiendo resultado de /move_arm_action: {e}"
            )
            return

        if success:
            self.get_logger().info(
                "MOVE desde dashboard ejecutado correctamente."
            )
        else:
            self.get_logger().error(
                "MOVE desde dashboard falló."
            )

    def publicar_engine_difficulty(self, payload):
        """
        Publica el nivel de dificultad del motor seleccionado desde el dashboard.
        """
        difficulty = payload.get("difficulty", "")

        if difficulty not in ["1", "5", "15"]:
            self.get_logger().warning(
                f"engine_difficulty inválido recibido: {difficulty}"
            )
            return

        msg = String()
        msg.data = difficulty

        self.pub_engine_difficulty.publish(msg)

        self.get_logger().info(
            f"Dificultad publicada en /engine_difficulty: {difficulty}"
        )

    # -------------------------------------------------------------------------
    # Utilidades
    # -------------------------------------------------------------------------


    # -------------------------------------------------------------------------
    # Cierre seguro
    # -------------------------------------------------------------------------

    def destroy_node(self):
        """
        Cierra servidor WebSocket y destruye el nodo.
        """
        if self.websocket_loop.is_running():
            self.websocket_loop.call_soon_threadsafe(
                self.websocket_loop.stop
            )

        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    nodo_dashboard = DashboardGuiNode()

    try:
        rclpy.spin(nodo_dashboard)

    except KeyboardInterrupt:
        pass

    finally:
        nodo_dashboard.destroy_node()

        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()