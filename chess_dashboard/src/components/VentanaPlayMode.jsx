import React, { useEffect, useState } from 'react'
import { Chessboard } from 'react-chessboard'
import { Chess } from 'chess.js'
import { Canvas } from '@react-three/fiber'
import { OrbitControls, Environment, Grid } from '@react-three/drei'
/**
 * @component VentanaPlayMode
 * @description Interfaz Principal de Operación Autónoma (Game Loop)}.
 * Gestiona el ciclo de juego asimétrico (Humano vs Robot), actuando
 * como puente entre el motor Stockfish y el gemelo digital en WebGL.
 * Suscribe y reacciona a los tópicos de estado de partida (GameStatus),
 * validación de tablero (ValidatedMove/FEN) e incidencias (GameFault).
 * 
 * @param {Function} alPresionarVolver - Aborta la partida y regresa al selector de modos.
 * @param {Boolean} rosConnected - Estado del puente de comunicación WebSocket.
 * @param {Object} gameStatus - Objeto con el estado actual de la máquina finita del árbitro.
 * @param {Object} gameFault - Objeto de advertencia cuando se detecta un movimiento ilegal.
 * @param {Object} validatedFen - Payload con la notación FEN validada por la cámara cenital.
 * @param {Array} moveHistory - Registro histórico de jugadas procesado desde el backend.
 * @param {Function} enviarEngineDifficulty - Callback para reconfigurar la profundidad de Stockfish.
 */
function VentanaPlayMode({
  alPresionarVolver,
  rosConnected,
  gameStatus,
  gameFault,
  validatedFen,
  moveHistory = [],
  enviarEngineDifficulty
}) {

  const [verCamara, setVerCamara] = useState(false)

  // --- ESTADOS LÓGICOS DEL JUEGO ---
  const [game, setGame] = useState(new Chess());
  const [turnoHumano, setTurnoHumano] = useState(true); 
  const [mensajeCerebro, setMensajeCerebro] = useState("Esperando tu movimiento en el tablero físico...");
  const [engineDifficulty, setEngineDifficulty] = useState("5")

  // SINCRONIZACIÓN DE PERCEPCIÓN (FEN):
  // El tablero 2D es un visor pasivo. No se permite interacción web directa; 
  // su estado depende exclusivamente de la validación física (Cámara -> Árbitro -> FEN).
  useEffect(() => {
    if (!validatedFen?.fen) return

    try {
      const gameCopy = new Chess()
      gameCopy.load(validatedFen.fen)
      setGame(gameCopy)
    } catch (error) {
      console.error('FEN inválido recibido desde ROS:', validatedFen.fen, error)
    }
  }, [validatedFen])

  // SUPERVISOR DEL GAME LOOP:
  // Decodifica el estado emitido por `referee_node.py` y actualiza 
  // la semáforización (Turnos, Interlock, Final de partida).
  useEffect(() => {
    if (!gameStatus) return

    const esTurnoHumano = gameStatus.game_state === 'WAITING_HUMAN'

    setTurnoHumano(esTurnoHumano)

    if (esTurnoHumano) {
      setMensajeCerebro('Esperando tu movimiento en el tablero físico...')
    } else if (gameStatus.game_state === 'GAME_OVER') {
      setMensajeCerebro('Partida finalizada.')
    } else {
      setMensajeCerebro('Turno del robot. Mantén las manos alejadas del tablero.')
    }
  }, [gameStatus])

  // Muestra faltas o errores detectados por el árbitro
  useEffect(() => {
    if (!gameFault) return

    setMensajeCerebro(`FALTA: ${gameFault.error_message}`)
  }, [gameFault])

  /**
   * @todo DEPRECATE FOR PRODUCTION
   * Función mock para inyectar jugadas sin hardware conectado. 
   */
  const simularInteraccion = () => {
    if (!turnoHumano) return;

    const gameCopy = new Chess();
    gameCopy.loadPgn(game.pgn());

    const possibleMoves = gameCopy.moves();
    if (possibleMoves.length === 0) return;

    const jugadaHumano = possibleMoves[Math.floor(Math.random() * possibleMoves.length)];
    gameCopy.move(jugadaHumano);

    setGame(gameCopy);
    setTurnoHumano(false);
    setMensajeCerebro(`Cámara: Movimiento detectado (${jugadaHumano}). Planificando trayectoria en MoveIt2...`);

    setTimeout(() => {
      const robotGameCopy = new Chess();
      robotGameCopy.loadPgn(gameCopy.pgn());

      const robotMoves = robotGameCopy.moves();

      if (robotMoves.length > 0) {
        const jugadaRobot = robotMoves[Math.floor(Math.random() * robotMoves.length)];
        robotGameCopy.move(jugadaRobot);

        setGame(robotGameCopy);
        setTurnoHumano(true);
        setMensajeCerebro(`Brazo posicionado con éxito (${jugadaRobot}). Esperando tu siguiente movimiento...`);
      }
    }, 2500);
  };

  // --- FORMATEAR HISTORIAL PARA LA INTERFAZ ---
  const paresDeMovimientos = []

  moveHistory.forEach((move) => {
    const index = move.move_number - 1

    if (!paresDeMovimientos[index]) {
      paresDeMovimientos[index] = {
        turno: move.move_number,
        blancas: "...",
        negras: "..."
      }
    }

    if (move.color === "white") {
      paresDeMovimientos[index].blancas = move.san
    } else if (move.color === "black") {
      paresDeMovimientos[index].negras = move.san
    }
  })

  const cambiarDificultad = (event) => {
    const nuevaDificultad = event.target.value

    setEngineDifficulty(nuevaDificultad)

    if (enviarEngineDifficulty) {
      enviarEngineDifficulty(nuevaDificultad)
    }

    setMensajeCerebro(`Dificultad del motor actualizada a nivel ${nuevaDificultad}.`)
  }

  return (
    <div className="bg-white p-6 md:p-8 rounded-2xl shadow-xl max-w-7xl w-full border border-gray-100 flex flex-col h-[90vh]">
      {/* Encabezado */}
      <div className="flex items-center justify-between mb-6 border-b border-gray-200 pb-4">
        <h2 className="text-2xl font-black text-gray-800 tracking-wide flex items-center space-x-3">
          <span className="text-purple-600">♟️</span>
          <span>PARTIDA EN CURSO (PLAY MODE)</span>
        </h2>
        <button 
          onClick={alPresionarVolver}
          className="bg-purple-600 hover:bg-purple-700 text-white font-semibold px-5 py-2 rounded-lg shadow-sm transition text-sm"
        >
          ⏮ Salir de la partida
        </button>
      </div>

      {/* BANNER DE TURNO */} 
      <div className={`mb-6 text-white text-center py-2 rounded-lg shadow-sm flex items-center justify-center space-x-2 transition-colors duration-500 ${turnoHumano ? 'bg-emerald-500' : 'bg-red-600'}`}>
        <div className={`w-2.5 h-2.5 bg-white rounded-full ${turnoHumano ? 'animate-pulse' : 'animate-bounce'} shadow-[0_0_8px_rgba(255,255,255,0.8)]`}></div>
        <span className="text-sm font-bold tracking-widest uppercase">
          {turnoHumano ? 'Tu Turno: Mueve una pieza en el tablero físico' : 'Turno del Robot: Mantén las manos alejadas'}
        </span>
      </div>

      <div className="flex-grow grid grid-cols-1 lg:grid-cols-2 gap-8 min-h-0">
        
        {/* COLUMNA IZQUIERDA */}
        <div className="flex flex-col space-y-4 min-h-0">
          
          {/* Fila 1: Status del Motor y Configuración */}
          <div className="bg-slate-50 py-2.5 px-4 rounded-xl border border-slate-200 shadow-sm flex justify-between items-center shrink-0">
            <div>
              <p className="text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-0.5">Motor de Decisión</p>
              <div className="flex items-center space-x-3">
                <p className="text-sm font-bold text-gray-800">Stockfish 16.1</p>
                
                <select 
                  className="bg-white border border-slate-300 text-gray-700 text-xs font-bold rounded px-2 py-1 focus:outline-none focus:ring-2 focus:ring-purple-500 cursor-pointer shadow-sm hover:border-purple-400 transition-colors"
                  value={engineDifficulty}
                  onChange={cambiarDificultad}
                  disabled={!rosConnected}
                >
                  <option value="1">Dificultad: Principiante (Depth 1)</option>
                  <option value="5">Dificultad: Intermedio (Depth 5)</option>
                  <option value="15">Dificultad: Avanzado (Depth 15)</option>
                </select>
              </div>
            </div>
            <div className={`flex items-center space-x-2 px-3 py-1 rounded-full border ${
              rosConnected
                ? 'bg-emerald-100 border-emerald-200'
                : 'bg-red-100 border-red-200'
            }`}>
              <div className={`w-2 h-2 rounded-full ${
                rosConnected ? 'bg-emerald-500 animate-pulse' : 'bg-red-500'
              }`}></div>
              <span className={`text-xs font-bold ${
                rosConnected ? 'text-emerald-700' : 'text-red-700'
              }`}>
                {rosConnected ? 'ROS ONLINE' : 'ROS OFFLINE'}
              </span>
            </div>
          </div>

          {/* Fila 2: Chatlog (Cerebro Robótico) */}
          <div className="bg-purple-50 border border-purple-200 rounded-xl py-2.5 px-4 shadow-sm shrink-0 flex justify-between items-center">
            <div>
              <p className="text-[10px] font-black text-purple-800 uppercase tracking-wider mb-0.5">Cerebro Robótico:</p>
              <p className="text-xs text-gray-700 italic">
                "{mensajeCerebro}"
              </p>
            </div>
            {/* BOTÓN DE PRUEBA HRI (Se borrará en la versión final) */}
            <button 
              onClick={simularInteraccion}
              disabled={!turnoHumano || rosConnected}
              className="bg-purple-200 hover:bg-purple-300 text-purple-800 text-[10px] font-bold py-1 px-3 rounded shadow-sm disabled:opacity-50 transition-all"
            >
              {rosConnected ? 'ROS activo' : 'Simular Cámara 🎥'}
            </button>
          </div>

          {/* Fila 3: Sub-división Asimétrica (Tablero 2D Libre + Historial) */}
          <div className="flex-grow grid grid-cols-1 md:grid-cols-[1.2fr_1fr] gap-6 min-h-0">
            
            {/* Sub-columna A: Monitor del Tablero 2D (Marco ajustado) */}
            <div className="flex justify-center items-center min-h-0">
              {/* Marco que imita el estilo del Historial pero abrazando el tablero */}
              <div className="h-full aspect-square bg-slate-50 border border-slate-200 rounded-xl shadow-sm p-2.5 md:p-3">
                <div className="w-full h-full rounded-md overflow-hidden flex items-center justify-center">
                  <Chessboard 
                    options={{
                      position: game.fen(),
                      allowDragging: false,
                      animationDurationInMs: 300,
                    }}
                  />
                </div>
              </div>
            </div>

            {/* Sub-columna B: Historial de Movimientos */}
            <div className="bg-slate-50 p-4 rounded-xl border border-slate-200 shadow-sm flex flex-col min-h-0">
              <h3 className="text-[11px] font-bold text-gray-500 uppercase tracking-wider mb-2 border-b border-slate-200 pb-2 shrink-0">
                Historial de Partida
              </h3>
              {/* Contenedor con scroll interno */}
              <div className="overflow-y-auto flex-grow pr-2 custom-scrollbar">
                {paresDeMovimientos.length === 0 ? (
                  <p className="text-xs text-slate-400 italic text-center mt-4">Esperando jugada de apertura...</p>
                ) : (
                  <div className="flex flex-col gap-y-2 text-xs font-mono text-gray-700">
                    {paresDeMovimientos.map((par, index) => (
                      <div key={index} className="grid grid-cols-3 gap-2 border-b border-slate-100 pb-1">
                        <div className="text-slate-400">{par.turno}.</div>
                        <div className="font-semibold">{par.blancas}</div>
                        <div className="text-purple-600 font-bold">{par.negras}</div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

          </div>
        </div>

        {/* Columna Derecha: Gemelo Digital 3D */}
        <div className="bg-slate-900 rounded-xl border-2 border-slate-800 flex flex-col overflow-hidden relative shadow-inner">
          
          {/* Overlay de telemetría superior */}
          <div className="absolute top-0 left-0 w-full p-4 flex justify-between items-start z-10 pointer-events-none">
            <div className="bg-black/50 backdrop-blur-sm border border-emerald-500/30 px-3 py-1 rounded text-xs font-mono text-emerald-400 shadow-[0_0_10px_rgba(16,185,129,0.2)]">
              WebGL Render: ON
            </div>
            <div className="bg-black/50 backdrop-blur-sm border border-white/10 px-3 py-1 rounded text-xs font-mono text-yellow-400 text-right">
              <p>Robot Status: IDLE</p>
              <p>Target: --</p>
            </div>
          </div>

          {/* ÁREA DEL CANVAS 3D (Three.js) */}
          <div className="flex-grow w-full h-full relative cursor-move">
            <Canvas camera={{ position: [2, 2, 2], fov: 45 }}>
              {/* Iluminación básica industrial */}
              <ambientLight intensity={0.5} />
              <directionalLight position={[10, 10, 5]} intensity={1.5} castShadow />
              <Environment preset="city" /> {/* Reflejos metálicos realistas */}
              
              {/* Suelo del entorno (Grilla) */}
              <Grid 
                infiniteGrid 
                fadeDistance={10} 
                sectionColor="#4f46e5" 
                cellColor="#1e293b" 
                cellSize={0.2} 
                sectionSize={1}
              />

              {/* Controles para girar, hacer zoom y pan */}
              <OrbitControls makeDefault />

              {/* AQUÍ INYECTAREMOS EL URDF DEL ROBOT EN EL SIGUIENTE PASO */}
            </Canvas>
          </div>
        </div>

      </div>
    </div>
  )
}

export default VentanaPlayMode