import React, { useEffect, useRef, useState } from 'react'
import VentanaIdle from './components/VentanaIdle'
import VentanaInicializacion from './components/VentanaInicializacion'
import VentanaSelectorModo from './components/VentanaSelectorModo'
import VentanaDebug from './components/VentanaDebug'
import VentanaPlayMode from './components/VentanaPlayMode'
/**
 * @component App (Root)
 * @description Contenedor principal de la aplicación ARCAM Dashboard.
 * Actúa como orquestador de la máquina de estados de la interfaz
 * y mantiene el cliente WebSocket para la comunicación bidireccional 
 * persistente con el nodo puente de ROS 2 (dashboard_gui_node).
 */
function App() {
  const [ventana, setVentana] = useState(0)
  const websocketRef = useRef(null)

  // ==========================================
  // ESTADO GLOBAL ROS
  // ==========================================
  // Estos estados se hidratan exclusivamente con los payloads recibidos desde el backend.
  // Cualquier componente hijo debe consumir esta información como solo-lectura.
  const [rosConnected, setRosConnected] = useState(false)
  const [boardState, setBoardState] = useState(null)
  const [gameStatus, setGameStatus] = useState(null)
  const [gameFault, setGameFault] = useState(null)
  const [validatedFen, setValidatedFen] = useState(null)
  const [moveHistory, setMoveHistory] = useState([])

  // ==========================================
  // PROTOCOLO DE COMUNICACIÓN
  // ==========================================
  // Gestiona el ciclo de vida de la conexión con reconexión automática.
  // Multiplexa los mensajes entrantes actualizando el estado global correspondiente
  // según el identificador de 'type' definido en el puente de Python.
  useEffect(() => {
    let socket = null
    let reconnectTimer = null
    let shouldReconnect = true

    const conectarWebSocket = () => {
      socket = new WebSocket('ws://localhost:8765')
      websocketRef.current = socket

      socket.onopen = () => {
        console.log('[ROS WS] Conectado al dashboard_gui_node')
        setRosConnected(true)
      }

      socket.onclose = () => {
        console.warn('[ROS WS] Conexión cerrada')
        setRosConnected(false)

        if (shouldReconnect) {
          reconnectTimer = setTimeout(conectarWebSocket, 2000)
        }
      }

      socket.onerror = (error) => {
        console.error('[ROS WS] Error de conexión:', error)
        setRosConnected(false)
      }

      socket.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data)
          const { type, payload } = message

          switch (type) {
            case 'connection_status':
              setRosConnected(Boolean(payload.connected))
              break

            case 'board_state':
              setBoardState(payload)
              break

            case 'game_status':
              setGameStatus(payload)
              break

            case 'game_fault':
              setGameFault(payload)
              break

            case 'validated_board_state':
              setValidatedFen(payload)
              break

            case 'validated_move':
              setMoveHistory(prev => [...prev, payload])
              break

            default:
              console.warn('[ROS WS] Tipo de mensaje no reconocido:', type)
              break
          }
        } catch (error) {
          console.error('[ROS WS] Mensaje inválido:', event.data, error)
        }
      }
    }

    conectarWebSocket()

    return () => {
      shouldReconnect = false

      if (reconnectTimer) {
        clearTimeout(reconnectTimer)
      }

      if (socket) {
        socket.close()
      }
    }
  }, [])

  const ejecutarHoming = () => {
    alert("Enviando comando de Homing al brazo robótico...")
    setVentana(2)
  }

  const manejarSeleccionModo = (modo) => {
    if (modo === 'play') {
      setVentana(3)
    } else if (modo === 'debug') {
      setVentana(4)
    }
  }

  // ==========================================
  // EMISORES DE TELECOMANDOS (RPC to ROS2)
  // ==========================================
  // Funciones inyectadas a los componentes hijos para encapsular la lógica de envío.
  // Validan la integridad del socket antes de despachar el payload JSON.
  const enviarManualJointCommand = (joints) => {
    if (!websocketRef.current || websocketRef.current.readyState !== WebSocket.OPEN) {
      console.warn('[ROS WS] No se pudo enviar manual_joint_command: WebSocket no conectado')
      return
    }

    websocketRef.current.send(JSON.stringify({
      type: 'manual_joint_command',
      payload: {
        joints: joints
      }
    }))
  }

  const enviarSpatialCommand = (command) => {
    if (!websocketRef.current || websocketRef.current.readyState !== WebSocket.OPEN) {
      console.warn('[ROS WS] No se pudo enviar spatial_command: WebSocket no conectado')
      return
    }

    websocketRef.current.send(JSON.stringify({
      type: 'spatial_command',
      payload: command
    }))
  }

  const enviarEngineDifficulty = (difficulty) => {
    if (!websocketRef.current || websocketRef.current.readyState !== WebSocket.OPEN) {
      console.warn('[ROS WS] No se pudo enviar engine_difficulty: WebSocket no conectado')
      return
    }

    websocketRef.current.send(JSON.stringify({
      type: 'engine_difficulty',
      payload: {
        difficulty: difficulty
      }
    }))
  }

  // RENDERIZADO CONDICIONAL (CLIENT-SIDE ROUTING)
  // Implementación de un router ligero basado en enteros (0: Idle -> 4: Debug)
  // para transicionar entre los distintos contextos operativos del sistema.
  return (
    <div className="min-h-screen bg-slate-50 flex flex-col items-center justify-center p-6 select-none">
      {ventana === 0 && (
        <VentanaIdle alPresionarStart={() => setVentana(1)} />
      )}

      {ventana === 1 && (
        <VentanaInicializacion
          alPresionarVolver={() => setVentana(0)}
          alPresionarHoming={ejecutarHoming}
        />
      )}

      {ventana === 2 && (
        <VentanaSelectorModo
          alPresionarVolver={() => setVentana(1)}
          alSeleccionarModo={manejarSeleccionModo}
        />
      )}

      {ventana === 3 && (
        <VentanaPlayMode
          alPresionarVolver={() => setVentana(2)}
          rosConnected={rosConnected}
          boardState={boardState}
          gameStatus={gameStatus}
          gameFault={gameFault}
          validatedFen={validatedFen}
          moveHistory={moveHistory}
          enviarEngineDifficulty={enviarEngineDifficulty}
        />
      )}

      {ventana === 4 && (
        <VentanaDebug
          alPresionarVolver={() => setVentana(2)}
          rosConnected={rosConnected}
          enviarManualJointCommand={enviarManualJointCommand}
          enviarSpatialCommand={enviarSpatialCommand}
        />
      )}
    </div>
  )
}

export default App