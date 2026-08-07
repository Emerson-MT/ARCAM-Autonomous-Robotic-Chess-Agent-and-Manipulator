import rclpy
from rclpy.node import Node
from std_msgs.msg import Int8MultiArray
import cv2
import numpy as np

class ChessVisionNode(Node):
    """
    Nodo de Visión Computacional.

    Funciones principales:
    - Calibra automáticamente la zona jugable 8x8 usando las esquinas internas del tablero.
    - Rectifica la imagen mediante homografía.
    - Compara el tablero actual contra un fondo vacío.
    - Publica un arreglo de 64 valores en /board_state:
        0 = casilla vacía
        1 = casilla ocupada
    """

    def __init__(self):
        super().__init__("vision_node_xcorners")

        # -----------------------------
        # Configuración ROS 2
        # -----------------------------
        self.publisher_ = self.create_publisher(Int8MultiArray, "/board_state", 10)
        self.timer_period = 1.0

        # -----------------------------
        # Configuración de fuente de imagen
        # -----------------------------
        self.MODO_SIMULACION = True

        # Rutas de las imágenes de prueba cuando no hay hardware conectado
        self.ruta_vacio = (
            "/home/vladix/ros2_ws/src/chess_logic_package/"
            "chess_logic_package/tablero_vacio.jpeg"
        )

        self.ruta_pieza = (
            "/home/vladix/ros2_ws/src/chess_logic_package/"
            "chess_logic_package/tablero_con_pieza.jpeg"
        )

        self.CAMARA_URL = "http://192.168.1.35:8080/video"
        self.cap = None

        if not self.MODO_SIMULACION:
            self.cap = cv2.VideoCapture(self.CAMARA_URL)

        # -----------------------------
        # Parámetros del tablero
        # -----------------------------
        self.TAMANO_TABLERO = 400
        self.CASILLAS_POR_LADO = 8
        self.TAMANO_CASILLA = self.TAMANO_TABLERO // self.CASILLAS_POR_LADO

        self.COLUMNAS = ["a", "b", "c", "d", "e", "f", "g", "h"]
        self.FILAS = ["8", "7", "6", "5", "4", "3", "2", "1"]

        # -----------------------------
        # Parámetros de detección
        # -----------------------------
        # Evita analizar los bordes exactos de la casilla para ignorar líneas divisorias
        self.MARGEN_CASILLA = 0.20

        self.TH_GRIS_BIN = 18
        self.TH_COLOR_BIN = 25

        # Umbrales para decidir si hay una pieza basándose en qué tanto cambió la imagen
        self.TH_SCORE_COLOR = 0.035
        self.TH_SCORE_GRIS = 0.20
        self.TH_SCORE_BORDE = 0.040
        self.TH_COLOR_APOYO_BORDE = 0.015
        self.TH_GRIS_APOYO_BORDE = 0.08

        # -----------------------------
        # Flags de depuración
        # -----------------------------
        self.MOSTRAR_DEBUG = False
        self.IMPRIMIR_DEBUG = True
        self.ultimo_estado_debug = None

        # -----------------------------
        # Variables internas
        # -----------------------------
        self.matriz_homografia = None
        self.fondo_referencia_gris = None
        self.fondo_referencia_lab = None
        self.fondo_referencia_edges = None
        self.calibracion_lista = False

        self.get_logger().info(
            "Iniciando nodo de visión con calibración automática."
        )

        self.ejecutar_calibracion_inicial()

        if self.calibracion_lista:
            self.get_logger().info(
                "Calibración exitosa. Publicando estado del tablero en /board_state."
            )
            self.timer = self.create_timer(self.timer_period, self.procesar_y_publicar)
        else:
            self.get_logger().error("Fallo en la calibración inicial.")

    # -------------------------------------------------------------------------
    # Captura y preparación de imagen
    # -------------------------------------------------------------------------

    def obtener_frame_actual(self):
        """
        Obtiene el frame actual desde imagen simulada o cámara.
        """
        if self.MODO_SIMULACION:
            return cv2.imread(self.ruta_pieza)

        if self.cap is None or not self.cap.isOpened():
            self.get_logger().warning("La cámara no está disponible.")
            return None

        ret, frame = self.cap.read()

        if not ret:
            self.get_logger().warning("No se pudo leer frame desde la cámara.")
            return None

        return frame

    def obtener_frame_vacio(self):
        """
        Obtiene la imagen del tablero vacío usada para calibración y fondo.
        """
        if self.MODO_SIMULACION:
            return cv2.imread(self.ruta_vacio)

        frame = self.obtener_frame_actual()

        if frame is None:
            self.get_logger().warning(
                "No se pudo capturar tablero vacío desde cámara."
            )

        return frame

    def redimensionar_imagen(self, img, ancho_objetivo=600):
        """
        Redimensiona manteniendo la proporción.
        """
        alto, ancho = img.shape[:2]
        nuevo_alto = int((ancho_objetivo / ancho) * alto)
        return cv2.resize(img, (ancho_objetivo, nuevo_alto))

    # -------------------------------------------------------------------------
    # Calibración automática
    # -------------------------------------------------------------------------

    def detectar_esquinas_zona_jugable(self, img):
        """
        Detecta las 49 esquinas internas del tablero y extrapola las 4 esquinas
        externas de la zona jugable 8x8.
        """
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        patron = (7, 7)

        encontrado, esquinas = self.detectar_esquinas_internas(gray, patron)

        if not encontrado:
            self.get_logger().error(
                "No se detectaron las 7x7 esquinas internas del tablero."
            )
            return None

        puntos_imagen = esquinas.reshape(-1, 2).astype(np.float32)
        puntos_modelo = self.generar_puntos_modelo_7x7()

        h_modelo_a_imagen, _ = cv2.findHomography(
            puntos_modelo,
            puntos_imagen,
            cv2.RANSAC,
            2.0
        )

        if h_modelo_a_imagen is None:
            self.get_logger().error("No se pudo calcular homografía con RANSAC.")
            return None

        pts_src = self.extrapolar_esquinas_8x8(h_modelo_a_imagen)

        if self.MOSTRAR_DEBUG:
            self.mostrar_calibracion(img, pts_src)

        return pts_src

    def detectar_esquinas_internas(self, gray, patron):
        """
        Detecta las esquinas internas del patrón ajedrezado.
        Usa findChessboardCornersSB si está disponible.
        """
        if hasattr(cv2, "findChessboardCornersSB"):
            flags = cv2.CALIB_CB_EXHAUSTIVE | cv2.CALIB_CB_ACCURACY
            return cv2.findChessboardCornersSB(gray, patron, flags)

        flags = cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE
        encontrado, esquinas = cv2.findChessboardCorners(gray, patron, flags)

        if encontrado:
            criterios = (
                cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
                30,
                0.001,
            )
            esquinas = cv2.cornerSubPix(
                gray,
                esquinas,
                (5, 5),
                (-1, -1),
                criterios
            )

        return encontrado, esquinas

    def generar_puntos_modelo_7x7(self):
        """
        Genera coordenadas ideales de las 49 esquinas internas.
        Las esquinas internas están en coordenadas (1..7, 1..7).
        """
        puntos_modelo = []

        for y in range(1, 8):
            for x in range(1, 8):
                puntos_modelo.append([x, y])

        return np.array(puntos_modelo, dtype=np.float32)

    def extrapolar_esquinas_8x8(self, h_modelo_a_imagen):
        """
        Extrapola las 4 esquinas externas de la zona jugable 8x8.
        """
        esquinas_externas_modelo = np.array(
            [
                [[0, 0]],
                [[8, 0]],
                [[8, 8]],
                [[0, 8]],
            ],
            dtype=np.float32,
        )

        esquinas_externas_imagen = cv2.perspectiveTransform(
            esquinas_externas_modelo,
            h_modelo_a_imagen
        )

        return esquinas_externas_imagen.reshape(4, 2).astype(np.float32)

    def ejecutar_calibracion_inicial(self):
        """
        Calibra el tablero y guarda la imagen de referencia del tablero vacío.
        """
        img_vacio = self.obtener_frame_vacio()

        if img_vacio is None:
            self.get_logger().error("No se pudo cargar/capturar tablero vacío.")
            return

        img_vacio = self.redimensionar_imagen(img_vacio)
        pts_src = self.detectar_esquinas_zona_jugable(img_vacio)

        if pts_src is None:
            return

        pts_dst = np.array(
            [
                [0, 0],
                [self.TAMANO_TABLERO, 0],
                [self.TAMANO_TABLERO, self.TAMANO_TABLERO],
                [0, self.TAMANO_TABLERO],
            ],
            dtype=np.float32,
        )

        self.matriz_homografia = cv2.getPerspectiveTransform(pts_src, pts_dst)

        vacio_rect = cv2.warpPerspective(
            img_vacio,
            self.matriz_homografia,
            (self.TAMANO_TABLERO, self.TAMANO_TABLERO)
        )

        self.guardar_fondos_referencia(vacio_rect)
        self.calibracion_lista = True

        if self.MOSTRAR_DEBUG:
            cv2.imshow("Referencia rectificada 400x400", vacio_rect)
            cv2.waitKey(1500)
            cv2.destroyAllWindows()

    def guardar_fondos_referencia(self, vacio_rect):
        """
        Guarda referencias del tablero vacío en diferentes filtros (gris, color, bordes).
        """
        fondo_gris = cv2.cvtColor(vacio_rect, cv2.COLOR_BGR2GRAY)
        fondo_gris = cv2.GaussianBlur(fondo_gris, (5, 5), 0)

        fondo_lab = cv2.cvtColor(vacio_rect, cv2.COLOR_BGR2LAB)

        fondo_edges = cv2.Canny(fondo_gris, 50, 120)
        fondo_edges = cv2.dilate(fondo_edges, np.ones((3, 3), np.uint8), iterations=1)

        self.fondo_referencia_gris = fondo_gris
        self.fondo_referencia_lab = fondo_lab
        self.fondo_referencia_edges = fondo_edges

    # -------------------------------------------------------------------------
    # Procesamiento del tablero actual
    # -------------------------------------------------------------------------

    def procesar_y_publicar(self):
        """
        Procesa el frame actual, estima ocupación de las 64 casillas y publica
        el resultado en /board_state.
        """
        frame_actual = self.obtener_frame_actual()

        if frame_actual is None:
            self.get_logger().warning("No se pudo obtener frame actual.")
            return

        frame_actual = self.redimensionar_imagen(frame_actual)
        frame_rect = self.rectificar_tablero(frame_actual)

        diferencias = self.calcular_diferencias(frame_rect)
        estado_tablero, scores_detectados = self.estimar_ocupacion(diferencias)

        if self.MOSTRAR_DEBUG:
            self.mostrar_debug_visual(frame_rect, diferencias)

        if self.IMPRIMIR_DEBUG:
            self.imprimir_debug_si_cambia(estado_tablero, scores_detectados)

        self.publicar_estado(estado_tablero)

    def rectificar_tablero(self, frame):
        """
        Aplica la homografía para obtener vista superior normalizada 400x400.
        """
        return cv2.warpPerspective(
            frame,
            self.matriz_homografia,
            (self.TAMANO_TABLERO, self.TAMANO_TABLERO)
        )

    def calcular_diferencias(self, frame_rect):
        """
        Calcula diferencias entre el tablero actual y el fondo vacío.
        """
        frame_gris = cv2.cvtColor(frame_rect, cv2.COLOR_BGR2GRAY)
        frame_gris = cv2.GaussianBlur(frame_gris, (5, 5), 0)

        diferencia_gris = cv2.absdiff(self.fondo_referencia_gris, frame_gris)

        frame_lab = cv2.cvtColor(frame_rect, cv2.COLOR_BGR2LAB)
        diferencia_lab = cv2.absdiff(self.fondo_referencia_lab, frame_lab)
        diferencia_color = np.max(diferencia_lab, axis=2).astype(np.uint8)

        edges_actual = cv2.Canny(frame_gris, 50, 120)
        edges_actual = cv2.dilate(
            edges_actual,
            np.ones((3, 3), np.uint8),
            iterations=1
        )

        diferencia_edges = cv2.absdiff(self.fondo_referencia_edges, edges_actual)

        return {
            "gris": diferencia_gris,
            "color": diferencia_color,
            "edges": diferencia_edges,
        }

    def estimar_ocupacion(self, diferencias):
        """
        Evalúa cada casilla y determina si está vacía u ocupada.
        """
        estado_tablero = [0] * 64
        scores_detectados = []

        for fila in range(self.CASILLAS_POR_LADO):
            for columna in range(self.CASILLAS_POR_LADO):
                indice = fila * self.CASILLAS_POR_LADO + columna
                casilla = self.indice_a_casilla(fila, columna)

                score_gris, score_color, score_edges = self.calcular_scores_casilla(
                    diferencias,
                    fila,
                    columna
                )

                if self.casilla_ocupada(score_gris, score_color, score_edges):
                    estado_tablero[indice] = 1
                    scores_detectados.append(
                        f"{casilla} -> gris={score_gris:.3f}, "
                        f"color={score_color:.3f}, edges={score_edges:.3f}"
                    )

        return estado_tablero, scores_detectados

    def calcular_scores_casilla(self, diferencias, fila, columna):
        """
        Calcula scores de cambio en gris, color y bordes para una casilla.
        """
        margen = int(self.TAMANO_CASILLA * self.MARGEN_CASILLA)

        x1 = columna * self.TAMANO_CASILLA
        y1 = fila * self.TAMANO_CASILLA
        x2 = x1 + self.TAMANO_CASILLA
        y2 = y1 + self.TAMANO_CASILLA

        roi_gris = diferencias["gris"][y1 + margen:y2 - margen, x1 + margen:x2 - margen]
        roi_color = diferencias["color"][y1 + margen:y2 - margen, x1 + margen:x2 - margen]
        roi_edges = diferencias["edges"][y1 + margen:y2 - margen, x1 + margen:x2 - margen]

        _, mask_gris = cv2.threshold(
            roi_gris,
            self.TH_GRIS_BIN,
            255,
            cv2.THRESH_BINARY
        )

        _, mask_color = cv2.threshold(
            roi_color,
            self.TH_COLOR_BIN,
            255,
            cv2.THRESH_BINARY
        )

        score_gris = cv2.countNonZero(mask_gris) / roi_gris.size
        score_color = cv2.countNonZero(mask_color) / roi_color.size
        score_edges = cv2.countNonZero(roi_edges) / roi_edges.size

        return score_gris, score_color, score_edges

    def casilla_ocupada(self, score_gris, score_color, score_edges):
        """
        Evalúa los resultados de la casilla para determinar si la diferencia
        es realmente una pieza o simplemente una sombra o reflejo falso.
        """
        detectada_por_color = score_color > self.TH_SCORE_COLOR
        detectada_por_gris = score_gris > self.TH_SCORE_GRIS

        detectada_por_borde_apoyado = (
            score_edges > self.TH_SCORE_BORDE
            and (
                score_color > self.TH_COLOR_APOYO_BORDE
                or score_gris > self.TH_GRIS_APOYO_BORDE
            )
        )

        return (
            detectada_por_color
            or detectada_por_gris
            or detectada_por_borde_apoyado
        )

    # -------------------------------------------------------------------------
    # Publicación y depuración
    # -------------------------------------------------------------------------

    def publicar_estado(self, estado_tablero):
        """
        Publica el estado de ocupación del tablero como arreglo de 64 elementos.
        """
        msg = Int8MultiArray()
        msg.data = estado_tablero
        self.publisher_.publish(msg)

        ocupadas = sum(estado_tablero)
        self.get_logger().info(
            f"Publicado en /board_state: {ocupadas}/64 casillas detectadas."
        )

    def imprimir_debug_si_cambia(self, estado_tablero, scores_detectados):
        """
        Imprime el estado detectado solo cuando cambia respecto al último estado.
        """
        if self.ultimo_estado_debug is not None:
            if estado_tablero == self.ultimo_estado_debug:
                return

        casillas_ocupadas = self.obtener_casillas_ocupadas(estado_tablero)
        falsas_ocupadas, falsas_vacias = self.comparar_con_estado_inicial(estado_tablero)

        print("\n==============================")
        print("NUEVO ESTADO DETECTADO")
        print("==============================")

        for linea in scores_detectados:
            print(linea)

        print("\nEstado detectado:")
        self.imprimir_matriz_estado(estado_tablero)

        print("    a b c d e f g h")
        print("Ocupadas:", casillas_ocupadas)
        print("Total:", len(casillas_ocupadas))
        print("Falsas ocupadas respecto al inicio:", falsas_ocupadas)
        print("Falsas vacías respecto al inicio:", falsas_vacias)

        self.ultimo_estado_debug = list(estado_tablero)

    def mostrar_debug_visual(self, frame_rect, diferencias):
        """
        Muestra ventanas de depuración visual.
        """
        debug_rect = frame_rect.copy()

        for i in range(9):
            p = i * self.TAMANO_CASILLA
            cv2.line(debug_rect, (p, 0), (p, self.TAMANO_TABLERO), (0, 255, 0), 1)
            cv2.line(debug_rect, (0, p), (self.TAMANO_TABLERO, p), (0, 255, 0), 1)

        _, mascara_gris = cv2.threshold(
            diferencias["gris"],
            self.TH_GRIS_BIN,
            255,
            cv2.THRESH_BINARY
        )

        _, mascara_color = cv2.threshold(
            diferencias["color"],
            self.TH_COLOR_BIN,
            255,
            cv2.THRESH_BINARY
        )

        mascara_total = cv2.bitwise_or(mascara_gris, mascara_color)
        mascara_total = cv2.bitwise_or(mascara_total, diferencias["edges"])

        cv2.imshow("Tablero rectificado", frame_rect)
        cv2.imshow("Tablero rectificado con grilla", debug_rect)
        cv2.imshow("Diferencia gris", diferencias["gris"])
        cv2.imshow("Diferencia color", diferencias["color"])
        cv2.imshow("Diferencia bordes", diferencias["edges"])
        cv2.imshow("Mascara combinada", mascara_total)
        cv2.waitKey(1)

    def mostrar_calibracion(self, img, pts_src):
        """
        Muestra la zona jugable detectada durante calibración.
        """
        img_debug = img.copy()

        cv2.polylines(
            img_debug,
            [pts_src.astype(np.int32)],
            True,
            (0, 255, 0),
            2
        )

        for punto in pts_src:
            cv2.circle(img_debug, tuple(punto.astype(int)), 5, (0, 0, 255), -1)

        cv2.imshow("Calibracion automatica - zona jugable detectada", img_debug)
        cv2.waitKey(1500)
        cv2.destroyAllWindows()

    # -------------------------------------------------------------------------
    # Utilidades
    # -------------------------------------------------------------------------

    def indice_a_casilla(self, fila, columna):
        """
        Convierte la posición numérica de la matriz a ajedrez (a8).
        """
        return self.COLUMNAS[columna] + self.FILAS[fila]

    def obtener_casillas_ocupadas(self, estado_tablero):
        """
        Devuelve lista de casillas ocupadas en notación algebraica.
        """
        casillas = []

        for fila in range(8):
            for columna in range(8):
                indice = fila * 8 + columna

                if estado_tablero[indice] == 1:
                    casillas.append(self.indice_a_casilla(fila, columna))

        return casillas

    def generar_estado_inicial(self):
        """
        Estado inicial esperado: filas 8, 7, 2 y 1 ocupadas.
        """
        estado = [0] * 64

        for i in range(16):
            estado[i] = 1

        for i in range(48, 64):
            estado[i] = 1

        return estado

    def comparar_con_estado_inicial(self, estado_tablero):
        """
        Compara el estado actual contra la posición inicial.
        Útil solo para depuración.
        """
        estado_inicial = self.generar_estado_inicial()

        falsas_ocupadas = []
        falsas_vacias = []

        for i in range(64):
            fila = i // 8
            columna = i % 8
            casilla = self.indice_a_casilla(fila, columna)

            if estado_inicial[i] == 0 and estado_tablero[i] == 1:
                falsas_ocupadas.append(casilla)

            elif estado_inicial[i] == 1 and estado_tablero[i] == 0:
                falsas_vacias.append(casilla)

        return falsas_ocupadas, falsas_vacias

    def imprimir_matriz_estado(self, estado_tablero):
        """
        Imprime el estado como matriz 8x8.
        """
        for fila in range(8):
            fila_txt = ""

            for columna in range(8):
                indice = fila * 8 + columna
                fila_txt += str(estado_tablero[indice]) + " "

            print(self.FILAS[fila], "|", fila_txt)

    def destroy_node(self):
        """
        Libera recursos antes de cerrar el nodo.
        """
        if self.cap is not None:
            self.cap.release()

        cv2.destroyAllWindows()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    nodo_vision = ChessVisionNode()

    try:
        rclpy.spin(nodo_vision)
    except KeyboardInterrupt:
        pass
    finally:
        nodo_vision.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()