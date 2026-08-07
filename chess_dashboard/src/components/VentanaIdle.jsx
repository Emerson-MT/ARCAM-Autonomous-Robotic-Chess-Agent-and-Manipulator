import React from 'react'
/**
 * @component VentanaIdle
 * @description Pantalla de reposo (Idle State) del sistema. Actúa como el estado inicial 
 * de la máquina de estados de la interfaz, esperando la orden del operador para 
 * energizar el sistema y arrancar los nodos principales.
 * @param {Function} alPresionarStart - Callback que desencadena la transición a la secuencia de inicialización.
 */
function VentanaIdle({ alPresionarStart }) {
  return (
    <div className="text-center bg-white p-10 rounded-2xl shadow-xl max-w-md w-full border border-gray-100">
      <h1 className="text-3xl font-black text-gray-800 mb-6 tracking-wider">
        NOMBRE DEL BRAZO
      </h1>
      
      <button 
        onClick={alPresionarStart}
        className="bg-emerald-600 hover:bg-emerald-700 text-white font-bold px-8 py-3 rounded-xl shadow-md hover:shadow-lg transition-all duration-200 flex items-center justify-center mx-auto space-x-2 transform hover:-translate-y-0.5"
      >
        <span>▶ START</span>
      </button>
      
      <div className="mt-8 flex items-center justify-center space-x-3 text-gray-400">
        <div className="animate-spin rounded-full h-4 w-4 border-2 border-purple-500 border-t-transparent"></div>
        <p className="text-sm font-semibold tracking-wide">Loading...</p>
      </div>
    </div>
  )
}

export default VentanaIdle