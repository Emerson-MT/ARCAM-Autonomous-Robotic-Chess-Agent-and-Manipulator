import React, { useState, useEffect } from 'react'
/**
 * @component VentanaInicializacion
 * @description Secuencia de arranque y diagnóstico del sistema ARCAM.
 * Supervisa la conexión secuencial de los nodos ROS2 de hardware y percepción
 * antes de liberar el interlock de seguridad para permitir el Homing.
 * @param {Function} alPresionarVolver - Callback para abortar el arranque y volver al estado Idle.
 * @param {Function} alPresionarHoming - Callback para ejecutar la calibración (Homing) tras validación.
 */
function VentanaInicializacion({ alPresionarVolver, alPresionarHoming }) {
  
  // Gestiona la progresión del checklist de hardware y el log de la terminal virtual.
  const [pasoActual, setPasoActual] = useState(0);
  const [logs, setLogs] = useState(["[SYSTEM] Iniciando protocolo de diagnóstico..."]);
  const [diagnosticoCompleto, setDiagnosticoCompleto] = useState(false);

  const checks = [
    "Cámara", "Motores", "Sensores", 
    "Unidad de procesamiento", "Módulo de control", "Enlace de comunicación"
  ]

  // Simulación de lectura de nodos (Se reemplazará con roslibjs)
  useEffect(() => {
    if (pasoActual < checks.length) {
      const timer = setTimeout(() => {
        setLogs(prev => [...prev, `[OK] ${checks[pasoActual]} en línea.`]);
        setPasoActual(prev => prev + 1);
      }, 800);
      return () => clearTimeout(timer);
    } else if (pasoActual === checks.length && !diagnosticoCompleto) {
      setTimeout(() => {
        setLogs(prev => [...prev, "[READY] Sistemas nominales. Validación física requerida."]);
        setDiagnosticoCompleto(true);
      }, 500);
    }
  }, [pasoActual, checks.length, diagnosticoCompleto]);

  return (
    <div className="bg-white p-8 rounded-2xl shadow-xl max-w-3xl w-full border border-gray-100">
      {/* Botón Volver estilo tu maqueta */}
      <button 
        onClick={alPresionarVolver}
        className="bg-purple-600 hover:bg-purple-700 text-white font-semibold px-4 py-2 rounded-lg shadow-sm transition mb-6 flex items-center space-x-1 text-sm"
      >
        <span>⏮ Back</span>
      </button>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8 items-stretch">
        {/* Lado Izquierdo: Diagnóstico */}
        <div>
          <h2 className="text-lg font-bold text-gray-800 mb-4 tracking-wide flex items-center space-x-2">
            <span>DIÁGNOSTICO DE HARDWARE</span>
          </h2>

          <div className="space-y-2">
            {checks.map((item, index) => {
              const estaCompletado = index < pasoActual;
              const estaCargando = index === pasoActual;
              
              return (
                <div 
                  key={index} 
                  className={`flex items-center space-x-3 font-semibold p-2.5 rounded-xl border transition-all duration-300 ${
                    estaCompletado 
                      ? 'bg-slate-50 border-slate-200 text-gray-800' 
                      : estaCargando 
                        ? 'bg-purple-50/50 border-purple-200 text-purple-700 shadow-sm' 
                        : 'bg-white border-transparent text-gray-400'
                  }`}
                >
                  {/* Icono de estado dinámico */}
                  <div className="w-5 h-5 flex items-center justify-center shrink-0">
                    {estaCompletado ? (
                      // ESTADO FINAL: Cuadrado verde
                      <div className="w-4 h-4 bg-emerald-500 rounded-[3px] flex items-center justify-center shadow-sm">
                        <span className="text-white text-[9px] font-bold">✓</span>
                      </div>
                    ) : estaCargando ? (
                      // ESTADO ACTIVO: Círculo de carga (Spinner)
                      <div className="w-4 h-4 border-2 border-purple-500 border-t-transparent rounded-full animate-spin"></div>
                    ) : (
                      // ESTADO PENDIENTE: Círculo vacío
                      <div className="w-4 h-4 border-2 border-gray-300 rounded-full bg-white"></div>
                    )}
                  </div>
                  <span className="text-xs sm:text-sm uppercase tracking-wide">{item}</span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Lado Derecho: Estado de Visión / Botón Homing */}
        <div className="flex flex-col h-full space-y-4">
          
          {/* Espaciador invisible que imita la altura exacta del título izquierdo (28px) */}
          <div className="h-7 hidden md:block w-full"></div>
          
          {/* Feed de Cámara Físico (Sanity Check) */}
          <div className="w-full flex-grow bg-slate-900 rounded-xl border border-slate-700 flex flex-col items-center justify-center text-slate-400 font-mono text-xs shadow-inner relative overflow-hidden">
            <div className="absolute top-3 left-3 bg-slate-800/80 border border-slate-700 px-2 py-0.5 rounded text-[9px] text-slate-400 tracking-wider uppercase font-bold">
              Camera Link: CAM0
            </div>
            <span className="text-2xl mb-2 opacity-40">📷</span>
            <span className="tracking-wider text-[11px] uppercase opacity-70">Feed de Cámara (Próximamente)</span>
          </div>
          
          {/* Botón Homing con Interlock de Seguridad */}
          <button 
            onClick={alPresionarHoming}
            disabled={!diagnosticoCompleto}
            className={`w-full font-bold py-4 rounded-xl shadow-md transition transform flex items-center justify-center space-x-2 text-lg tracking-widest
              ${diagnosticoCompleto 
                ? 'bg-purple-500 hover:bg-purple-600 text-white hover:-translate-y-0.5 cursor-pointer' 
                : 'bg-slate-200 text-slate-400 cursor-not-allowed'}`}
          >
            <span>{diagnosticoCompleto ? '🏠 EJECUTAR HOMING' : 'ESPERANDO SISTEMAS...'}</span>
          </button>
        </div>
      </div>
      {/* NUEVA UBICACIÓN: Terminal de Arranque (Ancho Completo en la parte inferior) */}
      <div className="mt-8 w-full h-32 bg-slate-900 rounded-xl border border-slate-700 p-4 font-mono text-[10px] sm:text-xs overflow-y-auto flex flex-col shadow-inner">
        <div className="text-slate-500 mb-2 border-b border-slate-700 pb-1 uppercase tracking-wider text-[9px] flex justify-between">
          <span>Terminal de Inicialización</span>
          <span className={`${diagnosticoCompleto ? 'text-purple-400' : 'text-emerald-500 animate-pulse'}`}>
            {diagnosticoCompleto ? 'STATUS: STANDBY' : 'STATUS: BOOTING...'}
          </span>
        </div>
        <div className="flex flex-col space-y-1">
          {logs.map((log, i) => (
            <div key={i} className={`${log.includes('[OK]') ? 'text-emerald-400' : log.includes('[READY]') ? 'text-purple-400 font-bold' : 'text-slate-300'}`}>
              {log}
            </div>
          ))}
          {!diagnosticoCompleto && <div className="text-slate-500 animate-pulse">_</div>}
        </div>
      </div>
    </div>
  )
}

export default VentanaInicializacion