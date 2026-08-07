import json
import chess
import rclpy
from rclpy.node import Node
from std_msgs.msg import Int8MultiArray, String

from chess_interfaces.msg import GameFault, GameStatus, RobotTurnResult, ValidatedMove

class RefereeNode(Node):
    """
    Nodo Árbitro.

    Responsabilidades:
    - Recibe la cuadrícula de ocupación (64 valores) desde la cámara.
    - Compara los cambios físicos con las reglas del ajedrez (python-chess).
    - Mantiene el turno oficial de la partida.
    - Avisa al dashboard si detecta jugadas ilegales o movimientos extraños.
    - Verifica que el robot realmente dejó la pieza donde dijo que lo haría.
    """

    def __init__(self):
        super().__init__("referee_node")

        # ---------------------------------------------------------------------
        # Suscriptores
        # ---------------------------------------------------------------------
        self.sub_board_state = self.create_subscription(
            Int8MultiArray,
            "/board_state",
            self.board_state_callback,
            10
        )

        self.sub_robot_result = self.create_subscription(
            RobotTurnResult,
            "/robot_turn_completed",
            self.robot_turn_completed_callback,
            10
        )

        # ---------------------------------------------------------------------
        # Publicadores
        # ---------------------------------------------------------------------
        self.pub_game_fault = self.create_publisher(
            GameFault,
            "/game_fault",
            10
        )

        self.pub_game_status = self.create_publisher(
            GameStatus,
            "/game_status",
            10
        )

        self.pub_validated_board = self.create_publisher(
            String,
            "/validated_boardState",
            10
        )

        self.pub_validated_move = self.create_publisher(
            ValidatedMove,
            "/validated_move",
            10
        )

        # ---------------------------------------------------------------------
        # Estado lógico del juego
        # ---------------------------------------------------------------------
        # Tablero virtual que dictamina qué es legal y qué no
        self.tablero_logico = chess.Board()

        # Mapeo para traducir los 64 índices del arreglo a casillas reales (a8, h1...)
        self.columnas = ["a", "b", "c", "d", "e", "f", "g", "h"]
        self.filas = ["8", "7", "6", "5", "4", "3", "2", "1"]
        self.idx_a_algebraico = [
            columna + fila
            for fila in self.filas
            for columna in self.columnas
        ]

        self.estado_anterior = self.estado_ocupacion_desde_board(self.tablero_logico)

        # Máquina de estados principal:
        # WAITING_HUMAN, ROBOT_MOVING, VERIFYING_ROBOT, GAME_OVER
        self.estado_partida = "WAITING_HUMAN"

        # Movimiento que el robot debía ejecutar.
        self.movimiento_robot_esperado = None

        # Evita repetir exactamente el mismo error muchas veces.
        self.ultimo_error = None

        # Variables para confirmar que la visión de la cámara es estable 
        # (evita validar mientras una mano está cruzando el tablero)
        self.estado_pendiente = None
        self.contador_estado_pendiente = 0
        self.LECTURAS_ESTABLES_REQUERIDAS = 3

        self.get_logger().info("Árbitro iniciado. Esperando movimiento humano.")
        self.publicar_game_status()

    # -------------------------------------------------------------------------
    # Callbacks principales
    # -------------------------------------------------------------------------

    def board_state_callback(self, msg):
        """
        Recibe lo que la cámara está viendo en tiempo real (1 = ocupado, 0 = vacío).
        """
        if len(msg.data) != 64:
            self.lanzar_error(
                10,
                "Estado de tablero inválido: se esperaban 64 valores.",
                "board_state"
            )
            return

        estado_actual = list(msg.data)
        
        # Mientras el robot se mueve, la cámara puede ver sombras, brazo o gripper.
        # Por seguridad, se ignora la visión hasta recibir /robot_turn_completed.
        if self.estado_partida == "ROBOT_MOVING":
            return

        # Espera a que la imagen se quede quieta antes de procesarla
        if not self.estado_es_estable(estado_actual):
            return

        if self.estado_partida == "VERIFYING_ROBOT":
            self.verificar_movimiento_robot(estado_actual)
            return

        if self.estado_partida == "WAITING_HUMAN":
            self.procesar_movimiento_humano(estado_actual)
            return

        if self.estado_partida == "GAME_OVER":
            return

    def robot_turn_completed_callback(self, msg):
        """
        Recibe confirmación de que el robot terminó su trayectoria y salió
        de la zona del tablero.
        """
        resultado = self.extraer_resultado_robot(msg)

        if resultado is None:
            self.lanzar_error(
                20,
                "Mensaje /robot_turn_completed inválido.",
                "robot_turn_completed"
            )
            return

        turn_completed, from_square, to_square, is_capture = resultado

        if not turn_completed:
            return

        if not from_square or not to_square:
            self.lanzar_error(
                21,
                "El robot terminó, pero no informó movimiento esperado.",
                "robot_turn_completed"
            )
            return

        uci = f"{from_square}{to_square}"

        try:
            movimiento = chess.Move.from_uci(uci)
        except ValueError:
            self.lanzar_error(
                22,
                f"Movimiento del robot inválido: {uci}",
                uci
            )
            return

        if movimiento not in self.tablero_logico.legal_moves:
            self.lanzar_error(
                23,
                f"El robot reportó un movimiento ilegal: {uci}",
                uci
            )
            return
            
        # Cambia el estado a verificación para que la cámara revise el tablero
        self.movimiento_robot_esperado = movimiento
        self.estado_partida = "VERIFYING_ROBOT"
        self.estado_pendiente = None
        self.contador_estado_pendiente = 0

        self.get_logger().info(
            f"Robot terminó trayectoria. Verificando por visión: {uci}"
        )

        self.publicar_game_status()

    # -------------------------------------------------------------------------
    # Procesamiento de jugadas
    # -------------------------------------------------------------------------

    def procesar_movimiento_humano(self, estado_actual):
        """
        Deduce y valida el movimiento humano a partir del nuevo estado físico.
        """
        jugadas_candidatas = self.buscar_jugadas_legales_compatibles(estado_actual)

        if len(jugadas_candidatas) == 0:
            self.lanzar_error(
                1,
                "Movimiento humano no reconocido o ilegal.",
                "desconocida",
                estado_actual
            )
            return

        movimiento = self.resolver_jugada_candidata(jugadas_candidatas)

        if movimiento is None:
            candidatas_uci = [mov.uci() for mov in jugadas_candidatas]

            self.lanzar_error(
                2,
                f"Movimiento ambiguo detectado por ocupación: {candidatas_uci}",
                "ambigua",
                estado_actual
            )
            return
        self.aplicar_movimiento_validado(movimiento, estado_actual, origen="humano")

        if self.tablero_logico.is_game_over():
            self.estado_partida = "GAME_OVER"
        else:
            self.estado_partida = "ROBOT_MOVING"

        self.publicar_game_status()

    def verificar_movimiento_robot(self, estado_actual):
        """
        Verifica mediante visión que el robot ejecutó el movimiento esperado.
        """
        if self.movimiento_robot_esperado is None:
            self.lanzar_error(
                30,
                "No existe movimiento esperado del robot para verificar.",
                "robot"
            )
            return

        tablero_temporal = self.tablero_logico.copy(stack=False)
        tablero_temporal.push(self.movimiento_robot_esperado)

        estado_esperado = self.estado_ocupacion_desde_board(tablero_temporal)

        if estado_actual != estado_esperado:
            detalle_extra = self.describir_cambios_extra(
                estado_esperado,
                estado_actual
            )

        self.lanzar_error(
            31,
            f"La visión no coincide con el movimiento esperado del robot: "
            f"{self.movimiento_robot_esperado.uci()}. "
            f"{detalle_extra}",
            self.movimiento_robot_esperado.uci(),
            estado_actual
        )
        return

        self.aplicar_movimiento_validado(
            self.movimiento_robot_esperado,
            estado_actual,
            origen="robot"
        )

        self.movimiento_robot_esperado = None

        if self.tablero_logico.is_game_over():
            self.estado_partida = "GAME_OVER"
        else:
            self.estado_partida = "WAITING_HUMAN"

        self.publicar_game_status()

    def aplicar_movimiento_validado(self, movimiento, estado_actual, origen):
        """
        Aplica una jugada legal al tablero lógico, actualiza el estado visual
        y publica el FEN y la jugada validada.
        """
        color = "white" if self.tablero_logico.turn == chess.WHITE else "black"
        san = self.tablero_logico.san(movimiento)
        is_capture = self.tablero_logico.is_capture(movimiento)
        move_number = self.tablero_logico.fullmove_number

        self.tablero_logico.push(movimiento)

        self.estado_anterior = list(estado_actual)
        self.ultimo_error = None
        self.estado_pendiente = None
        self.contador_estado_pendiente = 0

        self.get_logger().info(
            f"Jugada legal validada ({origen}): {movimiento.uci()}"
        )

        self.publicar_fen_validado()
        self.publicar_jugada_validada(
            movimiento=movimiento,
            san=san,
            color=color,
            actor=origen,
            move_number=move_number,
            is_capture=is_capture
        )

    # -------------------------------------------------------------------------
    # Deducción de jugadas
    # -------------------------------------------------------------------------

    def buscar_jugadas_legales_compatibles(self, estado_actual):
        """
        Busca qué jugadas legales producen exactamente el estado físico observado.

        Ventaja:
        - Soporta movimientos normales.
        - Soporta capturas simples.
        - Soporta enroque.
        - Soporta en passant.
        - Detecta ambigüedad en promoción o capturas indistinguibles por ocupación.
        """
        jugadas_compatibles = []

        for movimiento in self.tablero_logico.legal_moves:
            tablero_temporal = self.tablero_logico.copy(stack=False)
            tablero_temporal.push(movimiento)

            estado_resultante = self.estado_ocupacion_desde_board(tablero_temporal)

            if estado_resultante == estado_actual:
                jugadas_compatibles.append(movimiento)

        return jugadas_compatibles

    def estado_ocupacion_desde_board(self, board):
        """
        Convierte un tablero python-chess a arreglo de ocupación de 64 valores.

        Orden:
        índice 0  = a8
        índice 7  = h8
        índice 56 = a1
        índice 63 = h1
        """
        estado = []

        for casilla_alg in self.idx_a_algebraico:
            square = chess.parse_square(casilla_alg)
            pieza = board.piece_at(square)

            estado.append(1 if pieza is not None else 0)

        return estado

    def resolver_jugada_candidata(self, jugadas_candidatas):
        """
        Resuelve una lista de jugadas compatibles.

        Si hay varias promociones posibles con la misma ocupación,
        para el MVP se asume promoción automática a dama.
        """
        if len(jugadas_candidatas) == 1:
            return jugadas_candidatas[0]

        promociones = [
            mov for mov in jugadas_candidatas
            if mov.promotion is not None
        ]

        if promociones:
            for mov in promociones:
                if mov.promotion == chess.QUEEN:
                    return mov

        return None

    # -------------------------------------------------------------------------
    # Publicadores
    # -------------------------------------------------------------------------

    def publicar_fen_validado(self):
        """
        Publica el tablero lógico validado en formato FEN.
        """
        msg = String()
        msg.data = self.tablero_logico.fen()
        self.pub_validated_board.publish(msg)

    def publicar_jugada_validada(
    self,
    movimiento,
    san,
    color,
    actor,
    move_number,
    is_capture
    ):
        """
        Publica la última jugada validada para el historial del dashboard.
        """
        msg = ValidatedMove()
        msg.uci = movimiento.uci()
        msg.san = san
        msg.color = color
        msg.actor = actor
        msg.move_number = int(move_number)
        msg.is_capture = bool(is_capture)
        msg.is_check = self.tablero_logico.is_check()
        msg.is_checkmate = self.tablero_logico.is_checkmate()
        msg.fen_after = self.tablero_logico.fen()

        self.pub_validated_move.publish(msg)

    def publicar_game_status(self):
        """
        Publica el estado general de la partida.
        """
        current_turn = "white" if self.tablero_logico.turn == chess.WHITE else "black"
        move_number = self.tablero_logico.fullmove_number

        msg = GameStatus()
        msg.game_state = self.estado_partida
        msg.current_turn = current_turn
        msg.move_number = move_number

        self.pub_game_status.publish(msg)

    def lanzar_error(self, codigo, mensaje, casilla, estado_actual=None):
        """"
        Alerta sobre faltas (ej. mover fuera de turno o mover dos piezas).
        Evita enviar el mismo error en bucle para no colapsar la pantalla.
        """
        firma_error = (
            codigo,
            mensaje,
            casilla,
            tuple(estado_actual) if estado_actual is not None else None
        )

        if firma_error == self.ultimo_error:
            return

        self.ultimo_error = firma_error

        self.get_logger().error(f"FALTA: {mensaje}")

        msg = GameFault()
        msg.error_code = codigo
        msg.error_message = mensaje
        msg.faulty_square = casilla

        self.pub_game_fault.publish(msg)

    # -------------------------------------------------------------------------
    # Utilidades
    # -------------------------------------------------------------------------

    def obtener_diferencias_estados(self, estado_base, estado_observado):
        """
        Compara dos estados de ocupación y devuelve casillas vaciadas y llenadas.
        """
        casillas_vaciadas = []
        casillas_llenadas = []

        for i in range(64):
            if estado_base[i] == 1 and estado_observado[i] == 0:
                casillas_vaciadas.append(self.idx_a_algebraico[i])
            elif estado_base[i] == 0 and estado_observado[i] == 1:
                casillas_llenadas.append(self.idx_a_algebraico[i])

        return casillas_vaciadas, casillas_llenadas

    def describir_cambios_extra(self, estado_esperado, estado_observado):
        """
        Describe qué cambios adicionales existen entre el estado esperado
        y el estado observado por visión.
        """
        extras_vaciadas, extras_llenadas = self.obtener_diferencias_estados(
            estado_esperado,
            estado_observado
        )

        if len(extras_vaciadas) == 1 and len(extras_llenadas) == 1:
            return (
                f"Movimiento extra detectado fuera de turno: "
                f"{extras_vaciadas[0]}{extras_llenadas[0]}"
            )

        if len(extras_vaciadas) == 1 and len(extras_llenadas) == 0:
            return (
                f"Posible captura o retiro extra fuera de turno desde "
                f"{extras_vaciadas[0]}"
            )

        if len(extras_vaciadas) > 0 or len(extras_llenadas) > 0:
            return (
                f"Cambios extra no autorizados. "
                f"Vaciadas: {extras_vaciadas}, Llenadas: {extras_llenadas}"
            )

        return "No se detectaron cambios extra."
    
    def estado_es_estable(self, estado_actual):
        """
        Verifica si el nuevo estado físico se mantiene estable durante varias lecturas.
        Evita validar movimientos mientras la pieza aún está siendo movida.
        """
        if estado_actual == self.estado_anterior:
            self.estado_pendiente = None
            self.contador_estado_pendiente = 0
            return False

        if self.estado_pendiente == estado_actual:
            self.contador_estado_pendiente += 1
        else:
            self.estado_pendiente = list(estado_actual)
            self.contador_estado_pendiente = 1

        return self.contador_estado_pendiente >= self.LECTURAS_ESTABLES_REQUERIDAS

    def extraer_resultado_robot(self, msg):
        """
        Desempaqueta los datos del mensaje del robot.
        """
        return (
            msg.turn_completed,
            msg.from_square,
            msg.to_square,
            msg.is_capture
        )


def main(args=None):
    rclpy.init(args=args)
    nodo_arbitro = RefereeNode()

    try:
        rclpy.spin(nodo_arbitro)
    except KeyboardInterrupt:
        pass
    finally:
        nodo_arbitro.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()