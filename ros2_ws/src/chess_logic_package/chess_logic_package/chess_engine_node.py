import chess
import chess.engine
import rclpy

from rclpy.node import Node
from rclpy.action import ActionClient
from std_msgs.msg import String

from chess_interfaces.action import MovePiece
from chess_interfaces.msg import RobotTurnResult

class ChessEngineNode(Node):
    """
    Nodo motor de ajedrez.

    Responsabilidades:
    - Recibe el tablero validado en formato FEN desde el árbitro.
    - Usa Stockfish para calcular la jugada del robot.
    - Envía la orden de movimiento al brazo robótico.
    - Publica /robot_turn_completed cuando el brazo termina su acción.
    """
    def __init__(self):
        super().__init__("chess_engine_node")
        # ---------------------------------------------------------------------
        # Parámetros de configuración
        # ---------------------------------------------------------------------
        self.engine_path = "/usr/games/stockfish"
        self.think_time = 0.5
        self.engine_difficulty = "5"

        # Flag para pruebas sin hardware real conectado
        self.SIMULAR_BRAZO = True

        # Memoria de estado para no calcular dos veces la misma jugada
        self.ultimo_fen_procesado = None

        # Seguimiento del movimiento actual en curso
        self.movimiento_pendiente = None
        self.is_capture_pendiente = False

        # Instancia del motor Stockfish
        self.engine = None
        self.stockfish_disponible = False

        # ---------------------------------------------------------------------
        # Suscriptores
        # ---------------------------------------------------------------------
        # Recibe el FEN confiable después de que el sistema de visión lo valida
        self.sub_validated_board = self.create_subscription(
            String,
            "/validated_boardState",
            self.validated_board_callback,
            10
        )

        # Recibe comandos desde la interfaz web (React) para ajustar el nivel
        self.sub_engine_difficulty = self.create_subscription(
            String,
            "/engine_difficulty",
            self.engine_difficulty_callback,
            10
        )

        # ---------------------------------------------------------------------
        # Publicadores y Clientes de Acción (Action Clients)
        # ---------------------------------------------------------------------
        # Avisa al árbitro que el robot ya movió sus piezas físicas
        self.pub_robot_turn_completed = self.create_publisher(
            RobotTurnResult,
            "/robot_turn_completed",
            10
        )

        # Cliente para comunicarse con el controlador del brazo (MoveIt2)
        self.move_arm_clientmove_arm_client = ActionClient(
            self,
            MovePiece,
            "/move_arm_action"
        )
        self.inicializar_stockfish()

    # -------------------------------------------------------------------------
    # Inicialización del motor
    # -------------------------------------------------------------------------

    def inicializar_stockfish(self):
        """
        Levanta el proceso de Stockfish usando el protocolo UCI.
        """
        try:
            self.engine = chess.engine.SimpleEngine.popen_uci(self.engine_path)
            self.stockfish_disponible = True

            self.get_logger().info(
                "Motor Stockfish inicializado. Esperando turno del robot."
            )

        except Exception as e:
            self.stockfish_disponible = False
            self.get_logger().error(
                f"No se pudo cargar Stockfish: {e}. Verifica instalación o ruta."   
            )

    # -------------------------------------------------------------------------
    # Callbacks principales
    # -------------------------------------------------------------------------

    def validated_board_callback(self, msg):
        """
        Recibe el tablero desde el árbitro. 
        Si es el turno del robot (Negras), procede a calcular la jugada.
        """
        fen_state = msg.data

        # Evitar recálculos si la visión publica el mismo estado varias veces
        if fen_state == self.ultimo_fen_procesado:
            return

        self.ultimo_fen_procesado = fen_state

        if not self.stockfish_disponible:
            self.get_logger().error("Stockfish no está disponible.")
            return

        try:
            tablero = chess.Board(fen_state)
        except ValueError:
            self.get_logger().error(f"FEN inválido recibido: {fen_state}")
            return

        if tablero.is_game_over():
            self.get_logger().info("La partida ya terminó. No se calcula jugada.")
            return

        # Lógica de turnos: El humano siempre juega con Blancas
        if tablero.turn == chess.WHITE:
            return

        self.get_logger().info("Turno del robot. Calculando mejor jugada...")

        movimiento = self.calcular_jugada(tablero)

        if movimiento is None:
            self.get_logger().warning("Stockfish no encontró jugada válida.")
            return

        # Iniciar la cadena de movimiento físico
        self.enviar_movimiento_al_brazo(tablero, movimiento)
    
    def engine_difficulty_callback(self, msg):
        """
        Actualiza el nivel de dificultad de Stockfish según lo indicado en el dashboard.
        """
        difficulty = msg.data

        if difficulty not in ["1", "5", "15"]:
            self.get_logger().warning(f"Dificultad inválida recibida: {difficulty}")
            return

        self.engine_difficulty = difficulty

        # Configuración escalonada de dificultad
        if difficulty == "1":
            self.think_time = 0.1
            skill_level = 1
        elif difficulty == "5":
            self.think_time = 0.5
            skill_level = 8
        else:
            self.think_time = 1.0
            skill_level = 15
        
        # Aplicar configuración al motor si está corriendo
        if self.stockfish_disponible and self.engine is not None:
            try:
                self.engine.configure({"Skill Level": skill_level})
            except Exception as e:
                self.get_logger().warning(
                    f"No se pudo configurar Skill Level de Stockfish: {e}"
                )

        self.get_logger().info(
            f"Dificultad actualizada: nivel={difficulty}, "
            f"think_time={self.think_time}s, skill_level={skill_level}"
        )

    # -------------------------------------------------------------------------
    # Cálculo de jugada
    # -------------------------------------------------------------------------

    def calcular_jugada(self, tablero):
        """
        Delega a Stockfish el análisis del tablero y retorna el mejor movimiento.
        """
        try:
            # Límite de tiempo asegura que el robot no se quede 'pensando' infinito
            resultado = self.engine.play(
                tablero,
                chess.engine.Limit(time=self.think_time)
            )
            return resultado.move

        except Exception as e:
            self.get_logger().error(f"Error al calcular jugada con Stockfish: {e}")
            return None

    # -------------------------------------------------------------------------
    # Flujo del Action Client (Envío de movimiento al brazo)
    # -------------------------------------------------------------------------

    def enviar_movimiento_al_brazo(self, tablero, movimiento):
        """
        Traduce el movimiento de ajedrez (ej. e2e4) a casillas origen/destino
        y determina si la trayectoria requiere rutina de captura.
        """
        source_square = chess.square_name(movimiento.from_square)
        target_square = chess.square_name(movimiento.to_square)
        is_capture = tablero.is_capture(movimiento)

        # Guardar en memoria por si se necesita reportar fallo más adelante
        self.movimiento_pendiente = movimiento
        self.is_capture_pendiente = is_capture

        self.get_logger().info(
            f"Jugada decidida por Stockfish: {movimiento.uci()} "
            f"({source_square} -> {target_square}, captura={is_capture})"
        )

        # Bypass para pruebas de software sin hardware conectado
        if self.SIMULAR_BRAZO:
            self.get_logger().info(
                "Modo simulación: se asume que el brazo ejecutó correctamente."
            )
            self.publicar_robot_turn_completed(success=True)
            return

        self.enviar_goal_move_piece(source_square, target_square, is_capture)

    def enviar_goal_move_piece(self, source_square, target_square, is_capture):
        """
        Envía la meta (goal) al servidor de acción del brazo robótico.
        Es una llamada asíncrona para no congelar el nodo mientras el brazo se mueve.
        """
        if not self.move_arm_client.wait_for_server(timeout_sec=2.0):
            self.get_logger().error("Action server /move_arm_action no disponible.")
            self.publicar_robot_turn_completed(success=False)
            return

        # Preparar mensaje del goal
        goal_msg = MovePiece.Goal()
        goal_msg.source_square = source_square
        goal_msg.target_square = target_square
        goal_msg.is_capture = is_capture

        self.get_logger().info("Enviando goal al brazo robótico...")

        # Enviar goal asíncrono y asignar callback para la respuesta inicial
        send_goal_future = self.move_arm_client.send_goal_async(goal_msg)
        send_goal_future.add_done_callback(self.goal_response_callback)

    def goal_response_callback(self, future):
        """
        Se ejecuta cuando el brazo responde si acepta o rechaza intentar el movimiento
        """
        goal_handle = future.result()

        if not goal_handle.accepted:
            self.get_logger().error("El brazo rechazó el goal de movimiento.")
            self.publicar_robot_turn_completed(False)
            return

        self.get_logger().info("Goal aceptado por el brazo. Esperando resultado...")

        # Si aceptó, pedimos el resultado final y asignamos el callback correspondiente
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(self.move_result_callback)

    def move_result_callback(self, future):
        """
        Se ejecuta cuando el brazo termina físicamente su rutina.
        """
        try:
            result = future.result().result
            success = bool(result.success)

        except Exception as e:
            self.get_logger().error(f"Error recibiendo resultado del brazo: {e}")
            success = False

        if success:
            self.get_logger().info("El brazo reportó movimiento completado.")
        else:
            self.get_logger().error("El brazo reportó fallo en el movimiento.")

        self.publicar_robot_turn_completed(success)

    # -------------------------------------------------------------------------
    # Resultado hacia referee_node
    # -------------------------------------------------------------------------

    def publicar_robot_turn_completed(self, success):
        """
        Cierra el ciclo del turno informando al árbitro que el hardware terminó.
        Esto permite al sistema de visión reanudar el escaneo de jugadas del humano.
        """
        if self.movimiento_pendiente is None:
            return

        from_square = chess.square_name(self.movimiento_pendiente.from_square)
        to_square = chess.square_name(self.movimiento_pendiente.to_square)

        msg = RobotTurnResult()
        msg.turn_completed = bool(success)
        msg.from_square = from_square
        msg.to_square = to_square
        msg.is_capture = bool(self.is_capture_pendiente)
        
        self.pub_robot_turn_completed.publish(msg)

        self.get_logger().info(
            f"Publicado /robot_turn_completed: "
            f"{from_square}->{to_square}, success={success}"
        )
        
        # Limpiar variables de estado para el siguiente turno
        self.movimiento_pendiente = None
        self.is_capture_pendiente = False

    # -------------------------------------------------------------------------
    # Cierre seguro
    # -------------------------------------------------------------------------

    def destroy_node(self):
        """
        Cierra Stockfish y libera los recursos al apagar el nodo.
        """
        if self.engine is not None:
            try:
                self.engine.quit()
            except Exception:
                pass

        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    nodo_engine = ChessEngineNode()

    try:
        rclpy.spin(nodo_engine)
    except KeyboardInterrupt:
        pass
    finally:
        nodo_engine.destroy_node()

        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()