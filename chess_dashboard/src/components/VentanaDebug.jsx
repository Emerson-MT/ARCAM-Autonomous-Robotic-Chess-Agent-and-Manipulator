import React, { useState } from 'react'
/**
 * @component VentanaDebug
 * @description Panel de diagnóstico (HRI) para la validación del manipulador robótico.
 * Permite el control manual de las articulaciones (Cinemática Directa) y el envío 
 * de comandos espaciales basados en coordenadas de tablero (Cinemática Inversa).
 * @param {Function} alPresionarVolver - Callback para retornar a la vista principal.
 * @param {Boolean} rosConnected - Estado de la conexión con el puente de ROS2.
 * @param {Function} enviarManualJointCommand - Callback para publicar en tópicos de articulaciones.
 * @param {Function} enviarSpatialCommand - Callback para publicar objetivos de movimiento espacial.
 */
function VentanaDebug({
  alPresionarVolver,
  rosConnected,
  enviarManualJointCommand,
  enviarSpatialCommand
}) {
  // Pestaña activa por defecto: 'articular' o 'espacial'
  const [pestana, setPestana] = useState('articular')

  // Mapeo directo a los grados de libertad (DOF) del brazo.
  const [articulaciones, setArticulaciones] = useState({
    base: 0,      // Motor 1: NEMA
    hombro: 0,    // Motor 2: NEMA
    codo: 0,      // Motor 3: NEMA
    muneca: 0,    // Motor 4: Servomotor
    gripper: 0,   // Motor 5: Servomotor (Apertura)
  })

  // Los valores se mantienen en grados/porcentaje para la UI,
  // pero se transforman a radianes antes de su publicación.
  const configMotores = [
    { id: 'base', nombre: 'Base (NEMA)', min: -180, max: 180, unidad: '°' },
    { id: 'hombro', nombre: 'Hombro (NEMA)', min: -90, max: 90, unidad: '°' },
    { id: 'codo', nombre: 'Codo (NEMA)', min: -90, max: 90, unidad: '°' },
    { id: 'muneca', nombre: 'Muñeca (Servo)', min: -90, max: 90, unidad: '°' },
    { id: 'gripper', nombre: 'Gripper (Servo)', min: 0, max: 100, unidad: '%' },
  ]

  /**
   * Utilidad matemática para la conversión de unidades.
   * @param {number} grados - Ángulo en formato sexagesimal.
   * @returns {number} Ángulo equivalente en radianes.
   */
  const gradosARadianes = (grados) => {
    return grados * Math.PI / 180
  }

  const construirComandoArticular = (nuevoEstado) => {
    return [
      gradosARadianes(nuevoEstado.base),
      gradosARadianes(nuevoEstado.hombro),
      gradosARadianes(nuevoEstado.codo),
      gradosARadianes(nuevoEstado.muneca),
      nuevoEstado.gripper / 100
    ]
  }

  // Gestiona la selección de casillas en el tablero 2D (GOTO vs MOVE)
  // 'goto' requiere 1 coordenada (Target)
  // 'move' requiere 2 coordenadas (Source -> Target)
  const [modoEspacial, setModoEspacial] = useState('goto')
  const [casillaDestino, setCasillaDestino] = useState(null)
  const [casillaOrigen, setCasillaOrigen] = useState(null)
  const [casillaMovimientoDestino, setCasillaMovimientoDestino] = useState(null)

  /**
   * Handler para la actualización en tiempo real de los sliders.
   * Genera el payload asíncrono y dispara la publicación del comando al motor.
   * @param {string} joint - Identificador de la articulación (ej. 'base', 'hombro').
   * @param {string|number} valor - Nuevo valor de consigna ingresado por la UI.
   */
  const cambiarAngulo = (joint, valor) => {
    const valorNumerico = parseInt(valor)

    setArticulaciones(prev => {
      const nuevoEstado = {
        ...prev,
        [joint]: valorNumerico
      }

      const comando = construirComandoArticular(nuevoEstado)

      if (enviarManualJointCommand) {
        enviarManualJointCommand(comando)
      }

      return nuevoEstado
    })
  }

  // Simulación de columnas y filas de ajedrez para el tablero de pruebas
  const columnas = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h']
  const filas = [8, 7, 6, 5, 4, 3, 2, 1]

  /**
   * Lógica de enrutamiento para la selección de casillas en la interfaz.
   * Evita selecciones inválidas dependiendo de si el modo activo es GOTO o MOVE.
   */
  const seleccionarCasillaEspacial = (nombreCasilla) => {
    if (modoEspacial === 'goto') {
      setCasillaDestino(nombreCasilla)
      return
    }

    if (!casillaOrigen) {
      setCasillaOrigen(nombreCasilla)
      setCasillaMovimientoDestino(null)
      return
    }

    if (!casillaMovimientoDestino) {
      setCasillaMovimientoDestino(nombreCasilla)
      return
    }

    setCasillaOrigen(nombreCasilla)
    setCasillaMovimientoDestino(null)
  }

  const casillaTelemetria = modoEspacial === 'goto'
  ? casillaDestino || 'e2'
  : casillaMovimientoDestino || casillaOrigen || 'e2'

  /**
   * Empaqueta los parámetros espaciales validados y los publica.
   * El payload incluye el tipo de comando (command_type) y las casillas involucradas.
   */
  const ejecutarComandoEspacial = () => {
    if (!enviarSpatialCommand) {
      console.warn('Función enviarSpatialCommand no disponible')
      return
    }

    if (modoEspacial === 'goto') {
      if (!casillaDestino) {
        console.warn('Falta seleccionar destino')
        return
      }

      enviarSpatialCommand({
        command_type: 'goto',
        target_square: casillaDestino
      })

      console.log('Comando GOTO enviado:', casillaDestino)
      return
    }

    if (!casillaOrigen || !casillaMovimientoDestino) {
      console.warn('Falta seleccionar origen o destino')
      return
    }

    enviarSpatialCommand({
      command_type: 'move',
      source_square: casillaOrigen,
      target_square: casillaMovimientoDestino,
      is_capture: false
    })

    console.log('Comando MOVE enviado:', casillaOrigen, '→', casillaMovimientoDestino)
  }

  return (
    <div className="bg-white p-8 rounded-2xl shadow-xl max-w-5xl w-full border border-gray-100">
      {/* Encabezado */}
      <div className="flex items-center justify-between mb-6 border-b border-gray-150 pb-4">
        <h2 className="text-xl font-black text-gray-800 tracking-wide flex items-center space-x-2">
          <span>🛠️ PANEL DE CALIBRACIÓN Y DIAGNÓSTICO</span>
        </h2>
        <button 
          onClick={alPresionarVolver}
          className="bg-purple-600 hover:bg-purple-700 text-white font-semibold px-4 py-2 rounded-lg shadow-sm transition text-sm"
        >
          ⏮ Volver al Menú
        </button>
      </div>

      {/* Selector de Pestañas HRI */}
      <div className="flex space-x-2 mb-6 bg-slate-100 p-1.5 rounded-xl w-fit">
        <button
          onClick={() => setPestana('articular')}
          className={`px-4 py-2 rounded-lg text-xs font-bold tracking-wider uppercase transition-all ${
            pestana === 'articular' 
              ? 'bg-white text-purple-700 shadow-sm' 
              : 'text-gray-500 hover:text-gray-800'
          }`}
        >
          ⚙️ Control Articular (Sliders)
        </button>
        <button
          onClick={() => setPestana('espacial')}
          className={`px-4 py-2 rounded-lg text-xs font-bold tracking-wider uppercase transition-all ${
            pestana === 'espacial' 
              ? 'bg-white text-purple-700 shadow-sm' 
              : 'text-gray-500 hover:text-gray-800'
          }`}
        >
          🗺️ Control Espacial (Tablero 2D)
        </button>

        {/* Ubicación: Al final del div selector de pestañas */}
        <button
          onClick={() => setPestana('vision')}
          className={`px-4 py-2 rounded-lg text-xs font-bold tracking-wider uppercase transition-all ${
            pestana === 'vision' 
              ? 'bg-white text-purple-700 shadow-sm' 
              : 'text-gray-500 hover:text-gray-800'
          }`}
        >
          👁️ Visión Computacional
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        
        {/* COLUMNA IZQUIERDA Y CENTRAL: CONTENIDO DINÁMICO SEGÚN LA PESTAÑA */}
        <div className={pestana === 'vision' ? "lg:col-span-3" : "lg:col-span-2"}>
          
          {/* PESTAÑA 1: CONTROL ARTICULAR (SLIDERS) */}
          {pestana === 'articular' && (
            <div className="space-y-5 bg-slate-50 p-6 rounded-xl border border-slate-200">
              <div>
                <h3 className="text-sm font-bold text-gray-800">Validación de Cinemática Directa</h3>
                <p className="text-xs text-gray-400 mt-0.5">Mueve los ejes de forma aislada para comprobar el comportamiento físico de los motores.</p>
              </div>
              {configMotores.map((motor) => (
                <div key={motor.id} className="space-y-1">
                  <div className="flex justify-between text-xs font-bold text-gray-600 items-center">
                    <span className="uppercase text-purple-700">{motor.nombre}</span>
                    <span className={`px-2 py-0.5 rounded text-[11px] ${
                      motor.id === 'gripper' 
                        ? 'bg-emerald-100 text-emerald-800' 
                        : 'bg-purple-100 text-purple-800'
                    }`}>
                      {articulaciones[motor.id]}{motor.unidad}
                    </span>
                  </div>
                  <input 
                    type="range" 
                    min={motor.min} 
                    max={motor.max} 
                    value={articulaciones[motor.id]}
                    onChange={(e) => cambiarAngulo(motor.id, e.target.value)}
                    className={`w-full h-2 rounded-lg appearance-none cursor-pointer ${
                      motor.id === 'gripper' ? 'bg-gray-200 accent-emerald-600' : 'bg-gray-200 accent-purple-600'
                    }`}
                  />
                  {/* Pequeña ayuda visual de los límites */}
                  <div className="flex justify-between text-[9px] text-gray-400 font-mono">
                    <span>{motor.min}{motor.unidad}</span>
                    <span>{motor.max}{motor.unidad}</span>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* PESTAÑA 2: CONTROL ESPACIAL (TABLERO DE VALIDACIÓN) */}
          {pestana === 'espacial' && (
            <div className="bg-slate-50 p-6 rounded-xl border border-slate-200 space-y-4">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <h3 className="text-sm font-bold text-gray-800">Validación de cinemática inversa</h3>
                  <p className="text-xs text-gray-400 mt-0.5">
                    Valida posición o movimiento por casillas.
                  </p>
                </div>

                <div className="flex bg-white border border-slate-200 rounded-lg p-1 shadow-sm shrink-0">
                  <button
                    onClick={() => {
                      setModoEspacial('goto')
                      setCasillaDestino(null)
                      setCasillaOrigen(null)
                      setCasillaMovimientoDestino(null)
                    }}
                    className={`px-3 py-1.5 rounded-md text-[10px] font-black uppercase tracking-wider transition ${
                      modoEspacial === 'goto'
                        ? 'bg-purple-600 text-white shadow'
                        : 'text-slate-500 hover:bg-slate-100'
                    }`}
                  >
                    🎯 Ir a casilla
                  </button>

                  <button
                    onClick={() => {
                      setModoEspacial('move')
                      setCasillaDestino(null)
                      setCasillaOrigen(null)
                      setCasillaMovimientoDestino(null)
                    }}
                    className={`px-3 py-1.5 rounded-md text-[10px] font-black uppercase tracking-wider transition ${
                      modoEspacial === 'move'
                        ? 'bg-purple-600 text-white shadow'
                        : 'text-slate-500 hover:bg-slate-100'
                    }`}
                  >
                    ♟️ Mover pieza
                  </button>
                </div>
              </div>
        
              <div className="flex flex-col items-center justify-center mt-2">
                {/* Cuadrícula del Tablero de Ajedrez */}
                <div className="bg-slate-800 p-2 rounded-xl shadow-md border-4 border-slate-700">
                  {filas.map((fila) => (
                    <div key={fila} className="flex">
                      {columnas.map((columna) => {
                        const nombreCasilla = `${columna}${fila}`;
                        const esOscura = (columnas.indexOf(columna) + fila) % 2 === 0;
                        const esDestinoGoto = modoEspacial === 'goto' && casillaDestino === nombreCasilla;
                        const esOrigenMove = modoEspacial === 'move' && casillaOrigen === nombreCasilla;
                        const esDestinoMove = modoEspacial === 'move' && casillaMovimientoDestino === nombreCasilla;

                        return (
                          <button
                            key={nombreCasilla}
                            onClick={() => seleccionarCasillaEspacial(nombreCasilla)}
                            className={`w-8 h-8 md:w-10 md:h-10 text-[10px] font-bold font-mono transition-all flex items-center justify-center ${
                              esOrigenMove
                                ? 'bg-emerald-500 text-white ring-4 ring-emerald-200 z-10 scale-105 rounded-sm'
                                : esDestinoMove || esDestinoGoto
                                  ? 'bg-purple-600 text-white ring-4 ring-purple-300 z-10 scale-105 rounded-sm'
                                  : esOscura 
                                    ? 'bg-slate-600 text-slate-300 hover:bg-purple-100 hover:text-purple-900' 
                                    : 'bg-slate-200 text-slate-700 hover:bg-purple-100 hover:text-purple-900'
                            }`}
                          >
                            {nombreCasilla}
                          </button>
                        );
                      })}
                    </div>
                  ))}
                </div>
                
                <div className="mt-3 bg-purple-50 border border-purple-200 px-3 py-2 rounded-lg w-full max-w-[330px]">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-xs font-medium text-purple-800 truncate">
                      Comando:
                      <span className="ml-1 font-mono font-bold bg-white px-2 py-0.5 border border-purple-300 rounded text-purple-900">
                        {modoEspacial === 'goto'
                          ? casillaDestino
                            ? `GOTO ${casillaDestino.toUpperCase()}`
                            : 'Selecciona destino'
                          : casillaOrigen && casillaMovimientoDestino
                            ? `MOVE ${casillaOrigen.toUpperCase()} → ${casillaMovimientoDestino.toUpperCase()}`
                            : casillaOrigen
                              ? `Origen: ${casillaOrigen.toUpperCase()}`
                              : 'Selecciona origen'}
                      </span>
                    </p>

                    <button
                      onClick={ejecutarComandoEspacial}
                      disabled={
                        (modoEspacial === 'goto' && !casillaDestino) ||
                        (modoEspacial === 'move' && (!casillaOrigen || !casillaMovimientoDestino))
                      }
                      className="bg-purple-600 hover:bg-purple-700 text-white text-[10px] font-black px-2.5 py-1.5 rounded-md shadow transition disabled:opacity-40 disabled:cursor-not-allowed shrink-0"
                    >
                      Ejecutar
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Ubicación: Justo debajo del bloque de pestana === 'espacial' */}
          {pestana === 'vision' && (
            <div className="bg-slate-50 p-5 rounded-xl border border-slate-200 space-y-3">
              <div>
                <h3 className="text-sm font-bold text-gray-800">Pipeline de Percepción Visual</h3>
                <p className="text-xs text-gray-400 mt-0.5">Diagnóstico del estado de la cámara cenital y segmentación de regiones de interés (ROI).</p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Cuadro de Video 1: Live Feed */}
                <div className="bg-slate-900 aspect-video rounded-lg border border-slate-700 flex flex-col justify-between p-3 relative overflow-hidden">
                  <span className="bg-red-500/80 text-white text-[9px] font-mono px-1.5 py-0.5 rounded uppercase font-bold tracking-wider w-fit z-10 animate-pulse">
                    🔴 Live Video Feed
                  </span>
                  <div className="absolute inset-0 flex flex-col items-center justify-center text-slate-600 text-xs">
                    <span className="text-3xl mb-1">📷</span>
                    <p className="font-mono text-[10px]">Overhead_Cam /dev/video0</p>
                  </div>
                  <div className="z-10 bg-black/40 text-slate-300 font-mono text-[9px] p-1 rounded backdrop-blur-sm mt-auto">
                    Resolución: 640x480 @ 30FPS
                  </div>
                </div>

                {/* Cuadro de Video 2: Matriz Transformada */}
                <div className="bg-slate-900 aspect-video rounded-lg border border-slate-700 flex flex-col justify-between p-3 relative overflow-hidden">
                  <span className="bg-indigo-500/80 text-white text-[9px] font-mono px-1.5 py-0.5 rounded uppercase font-bold tracking-wider w-fit z-10">
                    🔲 Homografía (Warped Mat)
                  </span>
                  <div className="absolute inset-0 flex flex-col items-center justify-center text-slate-600 text-xs">
                    <span className="text-3xl mb-1">📐</span>
                    <p className="font-mono text-[10px]">Aislamiento de la Grilla 8x8</p>
                  </div>
                  <div className="z-10 bg-black/40 text-emerald-400 font-mono text-[9px] p-1 rounded backdrop-blur-sm mt-auto">
                    Calibración: STATUS_OK (4 esquinas fijadas)
                  </div>
                </div>
              </div>

              {/* Telemetría de Percepción */}
              <div className="bg-white border border-slate-200 rounded-lg p-4 grid grid-cols-2 gap-4 text-xs font-mono">
                <div>
                  <p className="font-bold text-gray-700 font-sans mb-1">Algoritmos Activos:</p>
                  <p className="text-slate-500 text-[11px]">• Filtro Hough (Líneas: 18)</p>
                  <p className="text-slate-500 text-[11px]">• Clasificador: YOLOv8</p>
                </div>
                <div>
                  <p className="font-bold text-gray-700 font-sans mb-1">Métricas de Concurrencia:</p>
                  <p className="text-slate-500 text-[11px]">Inferencia: 12.4 ms</p>
                  <p className="text-emerald-600 font-bold text-[11px]">Filtro de Luz: Calibrado</p>
                </div>
              </div>
            </div>
          )}

        </div>

        {/* COLUMNA DERECHA: TELEMETRÍA Y SEGURIDAD FIJA */}
        {/* COLUMNA DERECHA: TELEMETRÍA Y SEGURIDAD FIJA */}
        {/* Solo se muestra si NO estamos en la pestaña de visión */}
        {pestana !== 'vision' && (
          <div className="flex flex-col justify-between space-y-6">
            <div className="bg-slate-900 text-emerald-400 p-6 rounded-xl font-mono text-xs shadow-inner space-y-3 flex-grow">
              <h4 className="text-gray-400 font-sans font-bold text-xs tracking-wider uppercase border-b border-gray-700 pb-2">
                📡 COORDENADAS CARTESIANAS
              </h4>
              <p className="text-yellow-400">// Conversión calculada en tiempo real</p>
              
              {pestana === 'articular' ? (
                <>
                  <p className="text-gray-400 font-sans text-[11px] uppercase tracking-wider">// Modo: Cinemática Directa</p>
                  <p>X_pos: <span className="text-white">{(150 + articulaciones.hombro * 0.5).toFixed(2)} mm</span></p>
                  <p>Y_pos: <span className="text-white">{(articulaciones.base * 1.2).toFixed(2)} mm</span></p>
                  <p>Z_pos: <span className="text-white">{(230 - articulaciones.codo * 0.8).toFixed(2)} mm</span></p>
                </>
              ) : (
                <>
                  <p className="text-gray-400 font-sans text-[11px] uppercase tracking-wider">// Modo: Cinemática Inversa</p>
                  <p>X_Target: <span className="text-white">{(120 + casillaTelemetria.charCodeAt(0) * 0.5).toFixed(2)} mm</span></p>
                  <p>Y_Target: <span className="text-white">{(40 + parseInt(casillaTelemetria[1]) * 15).toFixed(2)} mm</span></p>
                  <p>Z_Target: <span className="text-white">10.00 mm (Nivel de Tablero)</span></p>
                </>
              )}

              <div className="pt-4 border-t border-gray-800 text-gray-500">
                <p>Nodo ROS2: <span className="text-purple-400">/kinematics_validator</span></p>
                <p>Status: <span className="text-emerald-500 animate-pulse">● CONECTADO</span></p>
              </div>
            </div>

            <button 
              onClick={() => alert("🚨 ESTOP activado. Motores desenergizados por software.")}
              className="w-full bg-red-600 hover:bg-red-700 text-white font-black py-4 rounded-xl shadow-lg transition transform active:scale-95 text-lg tracking-wider shrink-0"
            >
              🛑 E-STOP
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

export default VentanaDebug