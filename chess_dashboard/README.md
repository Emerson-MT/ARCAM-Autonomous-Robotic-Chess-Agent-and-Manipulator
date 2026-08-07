# ARCAM - Chess Dashboard (HRI)

Interfaz web de usuario (HRI - Human-Robot Interaction) para la monitorización, diagnóstico y control del sistema **ARCAM** (Autonomous Robotic Chess Agent and Manipulator).

Este frontend actúa como el panel de control principal, comunicándose de forma bidireccional con el backend de ROS 2 a través de WebSockets, permitiendo la visualización del estado del motor de ajedrez, telemetría de los actuadores y el feed del pipeline de percepción visual.

## 🚀 Tecnologías

* **Framework:** React + Vite
* **Estilos:** Tailwind CSS
* **Renderizado 3D:** Three.js / React Three Fiber (Gemelo Digital)
* **Lógica de Ajedrez:** chess.js + react-chessboard
* **Comunicación:** WebSockets (Integración con `dashboard_gui_node` en ROS 2)

## ⚙️ Características Principales

1. **Modo de Operación (Play Mode):** Sincronización en tiempo real del estado de la partida contra el motor Stockfish, gestión de turnos y visualización del tablero validado por la cámara cenital.
2. **Herramienta de Diagnóstico (Debug Tool):** 
   * Control manual de cinemática directa (sliders por articulación).
   * Pruebas de cinemática inversa (movimientos GOTO y MOVE por casillas).
   * Monitoreo del pipeline de visión computacional y segmentación de imágenes.
3. **Secuencia de Arranque (Boot Sequence):** Panel de validación de hardware y *sanity checks* previos a la habilitación del interlock de seguridad.

## 🛠️ Instalación y Uso

Asegúrate de tener [Node.js](https://nodejs.org/) instalado en tu sistema.

1. Instala las dependencias del proyecto:
   ```bash
   npm install
   ```

2. Inicia el servidor de desarrollo local:
   ```bash
   npm run dev
   ```

3. Abre tu navegador en la ruta indicada (usualmente `http://localhost:5173`).

> **Nota:** Para que la telemetría y los comandos funcionen, asegúrate de tener el workspace de ROS 2 compilado y el nodo puente de WebSockets (`dashboard_gui_node`) en ejecución.