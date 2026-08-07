import React from 'react'

/**
 * @component VentanaSelectorModo
 * @description Enrutador principal de la interfaz.
 * Se activa únicamente tras superar los "Sanity Checks" de inicialización.
 * Permite bifurcar la lógica entre la autonomía del motor de ajedrez y 
 * el control manual de bajo nivel.
 * @param {Function} alSeleccionarModo - Callback para montar el componente/nodo de trabajo respectivo.
 * @param {Function} alPresionarVolver - Callback para abortar y regresar al Boot Sequence.
 */

function VentanaSelectorModo({ alSeleccionarModo, alPresionarVolver }) {
  return (
    <div className="bg-white p-10 rounded-2xl shadow-xl max-w-3xl w-full border border-gray-100 text-center">
      {/* Botón Volver */}
      <div className="text-left mb-4">
        <button 
          onClick={alPresionarVolver}
          className="bg-purple-600 hover:bg-purple-700 text-white font-semibold px-4 py-2 rounded-lg shadow-sm transition text-sm"
        >
          ⏮ Back
        </button>
      </div>

      <h2 className="text-2xl font-black text-gray-800 mb-2 tracking-wide">
        SELECCIONAR MODO DE OPERACIÓN
      </h2>
      <p className="text-gray-500 mb-8 font-medium">
        El sistema de control y el brazo robótico se encuentran inicializados correctamente.
      </p>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">

        {/* Tarjeta Modo Juego */}
        <button 
          onClick={() => alSeleccionarModo('play')}
          className="group bg-slate-50 hover:bg-purple-50 p-6 rounded-2xl border-2 border-slate-200 hover:border-purple-500 transition-all duration-300 text-left shadow-sm flex flex-col justify-between min-h-[13rem] transform hover:-translate-y-1"
        >
          <div>
            <div className="text-3xl mb-3">♟️</div>
            <h3 className="text-lg font-bold text-gray-800 group-hover:text-purple-700 transition-colors">
              PLAY MODE
            </h3>
            <p className="text-sm text-gray-500 mt-2 font-normal leading-relaxed">
              Partida de ajedrez contra motor IA. Control automatizado de trayectorias.
            </p>
          </div>
          <span className="text-xs font-bold text-purple-600 group-hover:translate-x-1 transition-transform inline-block mt-4">
            INGRESAR →
          </span>
        </button>

        {/* Tarjeta Debug Tool */}
        <button 
          onClick={() => alSeleccionarModo('debug')}
          className="group bg-slate-50 hover:bg-purple-50 p-6 rounded-2xl border-2 border-slate-200 hover:border-purple-500 transition-all duration-300 text-left shadow-sm flex flex-col justify-between min-h-[13rem] transform hover:-translate-y-1"
        >
          <div>
            <div className="text-3xl mb-3">🛠️</div>
            <h3 className="text-lg font-bold text-gray-800 group-hover:text-purple-700 transition-colors">
              DEBUG TOOL
            </h3>
            <p className="text-sm text-gray-500 mt-2 font-normal leading-relaxed">
              Calibración manual de hardware y movimiento aislado de actuadores.
            </p>
          </div>
          <span className="text-xs font-bold text-purple-600 group-hover:translate-x-1 transition-transform inline-block mt-4">
            INGRESAR →
          </span>
        </button>
      </div>
    </div>
  )
}

export default VentanaSelectorModo