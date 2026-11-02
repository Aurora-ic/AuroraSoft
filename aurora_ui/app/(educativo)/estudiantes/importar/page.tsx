"use client";

import { useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useVirtualizer } from "@tanstack/react-virtual";
import {
  FileSpreadsheet,
  Download,
  UploadCloud,
  UserPlus,
  UserCheck,
  RefreshCw,
  Copy,
  XCircle,
  FileWarning,
  CheckCircle2,
  RotateCcw,
  Check,
  Users,
  Sheet,
} from "lucide-react";
import { apiClient, descargarBlob } from "@/lib/api-client";
import { useAuth } from "@/contexts/AuthContext";
import { TextoError } from "@/components/ui/TextoError";
import { TheadFila, Th } from "@/components/ui/Tabla";
import { Boton, claseBoton } from "@/components/ui/Boton";
import { Migas } from "@/components/ui/Migas";
import { EncabezadoPagina, TarjetaKpi, claseBotonBanner, CLASE_CONTENEDOR_SECCION } from "@/components/ui/Encabezado";
import type {
  ImportacionAccionFila,
  ImportacionConfirmacionResultado,
  ImportacionFilaValidacion,
  ImportacionValidacionResultado,
} from "@/types/api";

// 🆕 Rediseño (sesión 2026-10-31) — misma lógica y mismas 3 llamadas
// (plantilla / validar / confirmar) que antes; cambia la presentación:
// encabezado destacado del Padrón, indicador de pasos, zona para arrastrar
// el archivo, KPIs que FILTRAN la vista previa (con 2000 filas, buscar los
// errores a ojo no era práctico) y una barra de confirmación con el resumen
// de lo que se escribe y lo que no. Rojo = problema operativo (error,
// duplicado), nunca ámbar (reservado a riesgo clínico, docs/frontend.md).

const ETIQUETA_ACCION: Record<ImportacionAccionFila, string> = {
  nuevo: "Nuevo",
  actualizado: "Actualizado",
  duplicado: "Duplicado en archivo",
  error: "Error",
};

const ESTILO_BADGE_ACCION: Record<ImportacionAccionFila, string> = {
  nuevo: "bg-teal-600/10 text-teal-900 dark:text-ink-dark",
  actualizado: "bg-teal-400/20 text-teal-900 dark:text-ink-dark",
  duplicado: "bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-300",
  error: "bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-300",
};

// "Bloqueante" = la fila nunca se escribe (mismo criterio que el backend:
// solo 'nuevo'/'actualizado' se aplican en /confirmar). 'duplicado' y
// 'error' comparten el mismo tratamiento visual de alerta porque, para
// quien importa, ambos significan lo mismo: "corrige esto antes de seguir".
function filaEsBloqueante(fila: ImportacionFilaValidacion): boolean {
  return fila.accion === "error" || fila.accion === "duplicado";
}

type FiltroFilas = "todas" | ImportacionAccionFila | "incompletas";

function BadgeAccion({ accion }: { accion: ImportacionAccionFila }) {
  return (
    <span className={`inline-block whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium ${ESTILO_BADGE_ACCION[accion]}`}>
      {ETIQUETA_ACCION[accion]}
    </span>
  );
}

function tamanoLegible(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// Indicador de pasos — solo informativo (no navega): el flujo real lo
// marcan los botones de cada tarjeta.
const PASOS = ["Plantilla", "Subir y validar", "Revisar", "Confirmar"];

function IndicadorPasos({ actual, terminado }: { actual: number; terminado: boolean }) {
  return (
    <ol className="m-0 grid grid-cols-2 sm:grid-cols-4 gap-3 list-none p-0" aria-label="Progreso de la importación">
      {PASOS.map((paso, i) => {
        const n = i + 1;
        const hecho = terminado || n < actual;
        const enCurso = !terminado && n === actual;
        return (
          <li
            key={paso}
            aria-current={enCurso ? "step" : undefined}
            className={`flex items-center gap-2.5 rounded-xl border px-3 py-2.5 transition-colors ${
              enCurso
                ? "border-teal-600 bg-teal-600/[0.06] dark:border-teal-accent-dark dark:bg-teal-accent-dark/10"
                : hecho
                  ? "border-teal-600/25 bg-teal-600/[0.04] dark:border-teal-accent-dark/20 dark:bg-teal-accent-dark/[0.05]"
                  : "border-border bg-surface dark:border-border-dark dark:bg-surface-dark"
            }`}
          >
            <span
              className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[12px] font-bold ${
                hecho
                  ? "bg-teal-600 text-white dark:bg-teal-accent-dark dark:text-mist-dark"
                  : enCurso
                    ? "bg-teal-900 text-white dark:bg-teal-accent-dark/30 dark:text-teal-accent-dark"
                    : "bg-border/70 text-ink/45 dark:bg-border-dark dark:text-ink-dark/45"
              }`}
            >
              {hecho ? <Check size={14} strokeWidth={3} aria-hidden="true" /> : n}
            </span>
            <span className={`text-[12.5px] font-semibold ${enCurso || hecho ? "text-teal-900 dark:text-ink-dark" : "text-ink/45 dark:text-ink-dark/45"}`}>
              {paso}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

function TarjetaPaso({
  numero,
  titulo,
  descripcion,
  icono: Icono,
  children,
  className = "",
}: {
  numero: number;
  titulo: string;
  descripcion?: string;
  icono: typeof Download;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-xl border border-teal-600/15 dark:border-teal-accent-dark/20 bg-teal-600/[0.035] dark:bg-teal-accent-dark/[0.05] shadow-sm overflow-hidden flex flex-col ${className}`}>
      <header className="flex items-center gap-2.5 px-4 py-3 bg-teal-600/[0.08] dark:bg-teal-accent-dark/[0.08] border-b border-teal-600/15 dark:border-teal-accent-dark/20">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-teal-600 text-white dark:bg-teal-accent-dark dark:text-mist-dark">
          <Icono size={16} aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <h2 className="m-0 text-[14px] font-bold text-teal-900 dark:text-ink-dark">
            <span className="text-ink/40 dark:text-ink-dark/40 mr-1">{numero}.</span>
            {titulo}
          </h2>
          {descripcion && <p className="m-0 text-[12px] text-ink/50 dark:text-ink-dark/50">{descripcion}</p>}
        </div>
      </header>
      <div className="p-5 flex-1">{children}</div>
    </section>
  );
}

export default function ImportarEstudiantesPage() {
  const { sesion } = useAuth();
  const [inputKey, setInputKey] = useState(0);

  const [descargandoPlantilla, setDescargandoPlantilla] = useState(false);
  const [plantillaDescargada, setPlantillaDescargada] = useState(false);
  const [errorPlantilla, setErrorPlantilla] = useState<string | null>(null);

  const [archivo, setArchivo] = useState<File | null>(null);
  const [arrastrando, setArrastrando] = useState(false);
  const [archivoValidado, setArchivoValidado] = useState<File | null>(null);
  const [validando, setValidando] = useState(false);
  const [errorValidar, setErrorValidar] = useState<string | null>(null);
  const [resultado, setResultado] = useState<ImportacionValidacionResultado | null>(null);
  const [filtroFilas, setFiltroFilas] = useState<FiltroFilas>("todas");

  const [confirmando, setConfirmando] = useState(false);
  const [errorConfirmar, setErrorConfirmar] = useState<string | null>(null);
  const [resultadoConfirmacion, setResultadoConfirmacion] = useState<ImportacionConfirmacionResultado | null>(null);

  // Filas visibles según el KPI elegido — la virtualización cuenta sobre
  // ESTA lista, no sobre todas las filas.
  const filasVisibles = useMemo(() => {
    if (!resultado) return [];
    if (filtroFilas === "todas") return resultado.filas;
    if (filtroFilas === "incompletas") return resultado.filas.filter((f) => !filaEsBloqueante(f) && f.datos_incompletos.length > 0);
    return resultado.filas.filter((f) => f.accion === filtroFilas);
  }, [resultado, filtroFilas]);

  // 🆕 Virtualización de la vista previa (hallazgo de escala, docs/gaps-
  // pendientes.md) — un archivo real puede traer hasta FILAS_MAXIMAS=2000
  // filas; renderizar las 2000 como <tr> reales degradaba el navegador
  // mucho antes de llegar al tope. El hook es incondicional (regla de
  // hooks de React) aunque `resultado` todavía sea null al montar — por
  // eso cuenta sobre `filasVisibles.length` (vacía hasta validar).
  const filasPreviewRef = useRef<HTMLDivElement>(null);
  const virtualizadorFilas = useVirtualizer({
    count: filasVisibles.length,
    getScrollElement: () => filasPreviewRef.current,
    estimateSize: () => 45,
    overscan: 10,
  });

  async function descargarPlantilla() {
    setDescargandoPlantilla(true);
    setErrorPlantilla(null);
    try {
      const blob = await apiClient.descargarArchivo("/admin/personas/importar/plantilla");
      descargarBlob(blob, "plantilla_estudiantes_aurorasoft.xlsx");
      setPlantillaDescargada(true);
    } catch (err) {
      setErrorPlantilla((err instanceof Error && err.message) || "No se pudo descargar la plantilla.");
    } finally {
      setDescargandoPlantilla(false);
    }
  }

  function tomarArchivo(elegido: File | null) {
    if (elegido && !elegido.name.toLowerCase().endsWith(".xlsx")) {
      setErrorValidar("El archivo debe ser un Excel .xlsx (usa la plantilla descargada).");
      return;
    }
    setArchivo(elegido);
    // Un archivo nuevo invalida cualquier vista previa/confirmación anterior:
    // confirmar siempre debe corresponder al último archivo validado.
    setArchivoValidado(null);
    setResultado(null);
    setResultadoConfirmacion(null);
    setErrorValidar(null);
    setErrorConfirmar(null);
    setFiltroFilas("todas");
  }

  function soltarArchivo(e: React.DragEvent<HTMLLabelElement>) {
    e.preventDefault();
    setArrastrando(false);
    tomarArchivo(e.dataTransfer.files?.[0] ?? null);
  }

  async function validarArchivo() {
    if (!archivo) return;
    setValidando(true);
    setErrorValidar(null);
    setResultadoConfirmacion(null);
    try {
      const formData = new FormData();
      formData.append("archivo", archivo);
      const datos = await apiClient.postForm<ImportacionValidacionResultado>(
        "/admin/personas/importar/validar",
        formData,
      );
      setResultado(datos);
      setArchivoValidado(archivo);
      setFiltroFilas("todas");
    } catch (err) {
      setErrorValidar((err instanceof Error && err.message) || "No se pudo validar el archivo.");
      setResultado(null);
      setArchivoValidado(null);
    } finally {
      setValidando(false);
    }
  }

  async function confirmarImportacion() {
    if (!archivoValidado) return;
    setConfirmando(true);
    setErrorConfirmar(null);
    try {
      const formData = new FormData();
      formData.append("archivo", archivoValidado);
      const datos = await apiClient.postForm<ImportacionConfirmacionResultado>(
        "/admin/personas/importar/confirmar",
        formData,
      );
      setResultadoConfirmacion(datos);
    } catch (err) {
      setErrorConfirmar((err instanceof Error && err.message) || "No se pudo confirmar la importación.");
    } finally {
      setConfirmando(false);
    }
  }

  function reiniciar() {
    setArchivo(null);
    setArchivoValidado(null);
    setResultado(null);
    setResultadoConfirmacion(null);
    setErrorValidar(null);
    setErrorConfirmar(null);
    setFiltroFilas("todas");
    setInputKey((k) => k + 1);
  }

  const puedeConfirmar = archivoValidado !== null && resultado !== null && !resultadoConfirmacion;
  const filasAplicables = resultado ? resultado.resumen.nuevos + resultado.resumen.actualizados : 0;
  const filasDescartadas = resultado ? resultado.resumen.duplicados + resultado.resumen.errores : 0;
  const pasoActual = resultadoConfirmacion ? 4 : resultado ? 3 : archivo || plantillaDescargada ? 2 : 1;
  const alternarFiltro = (f: FiltroFilas) => setFiltroFilas((actual) => (actual === f ? "todas" : f));

  // 🔧 Mismo candado que campanas/nueva/page.tsx: el backend ya rechaza esto
  // con 403 (los 3 endpoints de /importar/* dependen de permisos.STAFF_CLINICO,
  // que excluye "colegio"), pero esta página no tenía su propio aviso —
  // desde que (educativo)/layout.tsx deja entrar a "colegio" (antes lo
  // expulsaba por error), ese rol podía llegar hasta acá, subir un Excel y
  // validar la vista previa, para recién enterarse al confirmar de que no
  // tiene permiso.
  const puedeImportar = sesion?.rol === "psicologo" || sesion?.rol === "admin" || sesion?.rol === "superadmin";
  if (!puedeImportar) {
    return (
      <div className="max-w-5xl mx-auto">
        <TextoError>Esta sección es solo para psicólogos y administradores de tu institución.</TextoError>
      </div>
    );
  }

  return (
    <div className={CLASE_CONTENEDOR_SECCION}>
      <Migas sinMargen items={[{ label: "Padrón", href: "/estudiantes" }, { label: "Importar desde Excel" }]} />

      <EncabezadoPagina
        variante="destacado"
        icono={FileSpreadsheet}
        acento="teal"
        titulo="Importar estudiantes"
        descripcion="Da de alta o actualiza estudiantes en bloque. Nada se guarda hasta que confirmes: valida el archivo cuantas veces necesites mientras corriges los datos."
        acciones={
          <Link href="/estudiantes/nuevo" className={claseBotonBanner("secundario")}>
            <UserPlus size={15} aria-hidden="true" />
            Registrar uno a uno
          </Link>
        }
      />

      <IndicadorPasos actual={pasoActual} terminado={!!resultadoConfirmacion} />

      {/* =================== Importación aplicada =================== */}
      {resultadoConfirmacion ? (
        <section className="rounded-2xl border border-teal-600/25 dark:border-teal-accent-dark/20 bg-teal-600/[0.05] dark:bg-teal-accent-dark/[0.05] shadow-sm overflow-hidden">
          <div className="h-1.5 bg-gradient-to-r from-teal-900 via-teal-600 to-teal-400 dark:from-teal-accent-dark/60 dark:to-teal-accent-dark/20" />
          <div className="p-6 flex flex-col sm:flex-row sm:items-center gap-5">
            <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-teal-600/10 text-teal-700 dark:bg-teal-accent-dark/15 dark:text-teal-accent-dark">
              <CheckCircle2 size={28} aria-hidden="true" />
            </span>
            <div className="min-w-0 flex-1">
              <h2 className="m-0 font-display text-[20px] font-bold text-teal-900 dark:text-ink-dark">Importación aplicada</h2>
              <p className="m-0 mt-1 text-sm text-ink/60 dark:text-ink-dark/60">
                <strong className="text-teal-800 dark:text-teal-accent-dark">{resultadoConfirmacion.resumen.nuevos}</strong> estudiante(s) nuevo(s) y{" "}
                <strong className="text-teal-800 dark:text-teal-accent-dark">{resultadoConfirmacion.resumen.actualizados}</strong> actualizado(s).
                {resultadoConfirmacion.filas_con_datos_incompletos > 0 &&
                  ` ${resultadoConfirmacion.filas_con_datos_incompletos} quedaron con datos incompletos: puedes completarlos desde el padrón.`}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Link href="/estudiantes" className={claseBoton("primario", "inline-flex items-center gap-2")}>
                <Users size={15} aria-hidden="true" />
                Ver en el padrón
              </Link>
              <Boton variante="secundario" onClick={reiniciar} className="inline-flex items-center gap-2">
                <RotateCcw size={15} aria-hidden="true" />
                Importar otro archivo
              </Boton>
            </div>
          </div>
        </section>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)] gap-6 items-stretch">
          {/* =================== 1. Plantilla =================== */}
          <TarjetaPaso numero={1} icono={Download} titulo="Descarga la plantilla" descripcion="Úsala siempre: el sistema lee sus columnas por nombre.">
            <ul className="m-0 mb-4 list-none p-0 space-y-2 text-[12.5px] text-ink/70 dark:text-ink-dark/70">
              <li className="flex items-start gap-2">
                <Sheet size={14} aria-hidden="true" className="mt-0.5 shrink-0 text-teal-600 dark:text-teal-accent-dark" />
                Hoja de estudiantes con filas de ejemplo y qué columnas son obligatorias.
              </li>
              <li className="flex items-start gap-2">
                <Sheet size={14} aria-hidden="true" className="mt-0.5 shrink-0 text-teal-600 dark:text-teal-accent-dark" />
                Segunda hoja con la estructura académica (niveles, grados y secciones) ya creada en tu institución.
              </li>
            </ul>
            <Boton onClick={descargarPlantilla} disabled={descargandoPlantilla} className="inline-flex items-center gap-2">
              {plantillaDescargada ? <Check size={15} aria-hidden="true" /> : <Download size={15} aria-hidden="true" />}
              {descargandoPlantilla ? "Descargando…" : plantillaDescargada ? "Descargar de nuevo" : "Descargar plantilla .xlsx"}
            </Boton>
            <TextoError className="mt-3 text-sm">{errorPlantilla}</TextoError>
          </TarjetaPaso>

          {/* =================== 2. Subir y validar =================== */}
          <TarjetaPaso
            numero={2}
            icono={UploadCloud}
            titulo="Sube y valida tu archivo"
            descripcion="Validar nunca escribe nada en la base: repítelo mientras corriges el Excel."
          >
            <label
              onDragOver={(e) => {
                e.preventDefault();
                setArrastrando(true);
              }}
              onDragLeave={() => setArrastrando(false)}
              onDrop={soltarArchivo}
              className={`flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-4 py-6 text-center transition-colors focus-within:ring-2 focus-within:ring-teal-400 ${
                arrastrando
                  ? "border-teal-600 bg-teal-600/[0.06] dark:border-teal-accent-dark dark:bg-teal-accent-dark/10"
                  : archivo
                    ? "border-teal-600/40 bg-teal-600/[0.03] dark:border-teal-accent-dark/40"
                    : "border-border hover:border-teal-400 hover:bg-mist/50 dark:border-border-dark dark:hover:bg-surface-raised-dark"
              }`}
            >
              <input key={inputKey} type="file" accept=".xlsx" onChange={(e) => tomarArchivo(e.target.files?.[0] ?? null)} className="sr-only" />
              {archivo ? (
                <>
                  <FileSpreadsheet size={28} aria-hidden="true" className="text-teal-600 dark:text-teal-accent-dark" />
                  <span className="max-w-full truncate text-sm font-semibold text-teal-900 dark:text-ink-dark">{archivo.name}</span>
                  <span className="text-[12px] text-ink/50 dark:text-ink-dark/50">
                    {tamanoLegible(archivo.size)} · {archivoValidado === archivo ? "validado" : "listo para validar"} · haz clic para cambiarlo
                  </span>
                </>
              ) : (
                <>
                  <UploadCloud size={28} aria-hidden="true" className="text-ink/35 dark:text-ink-dark/35" />
                  <span className="text-sm font-semibold text-ink/75 dark:text-ink-dark/75">Arrastra tu Excel aquí o haz clic para elegirlo</span>
                  <span className="text-[12px] text-ink/45 dark:text-ink-dark/45">Solo archivos .xlsx · hasta 2000 filas</span>
                </>
              )}
            </label>

            <div className="mt-3 flex flex-wrap items-center gap-3">
              <Boton onClick={validarArchivo} disabled={!archivo || validando} className="inline-flex items-center gap-2">
                <RefreshCw size={15} aria-hidden="true" className={validando ? "animate-spin" : ""} />
                {validando ? "Validando…" : resultado ? "Validar de nuevo" : "Validar archivo"}
              </Boton>
              {(archivo || resultado) && (
                <button type="button" onClick={reiniciar} className="text-sm text-ink/50 dark:text-ink-dark/50 hover:text-ink dark:hover:text-ink-dark hover:underline">
                  Empezar de nuevo
                </button>
              )}
            </div>
            <TextoError className="mt-3 text-sm">{errorValidar}</TextoError>
          </TarjetaPaso>
        </div>
      )}

      {/* =================== 3. Revisar =================== */}
      {resultado && !resultadoConfirmacion && (
        <section className="rounded-xl border border-teal-600/15 dark:border-teal-accent-dark/20 bg-teal-600/[0.035] dark:bg-teal-accent-dark/[0.05] shadow-sm overflow-hidden">
          <header className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 bg-teal-600/[0.08] dark:bg-teal-accent-dark/[0.08] border-b border-teal-600/15 dark:border-teal-accent-dark/20">
            <div>
              <h2 className="m-0 text-[14px] font-bold text-teal-900 dark:text-ink-dark">
                <span className="text-ink/40 dark:text-ink-dark/40 mr-1">3.</span>
                Revisa la vista previa
              </h2>
              <p className="m-0 text-[12px] text-ink/50 dark:text-ink-dark/50">
                {resultado.total_filas} filas leídas del archivo · toca una tarjeta para filtrar la tabla.
              </p>
            </div>
            {filtroFilas !== "todas" && (
              <button type="button" onClick={() => setFiltroFilas("todas")} className="text-xs font-semibold text-teal-700 dark:text-teal-accent-dark hover:underline">
                Ver todas las filas
              </button>
            )}
          </header>

          <div className="p-5 space-y-5">
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
              <TarjetaKpi icono={UserPlus} etiqueta="Nuevos" valor={resultado.resumen.nuevos} activa={filtroFilas === "nuevo"} onClick={() => alternarFiltro("nuevo")} />
              <TarjetaKpi
                icono={UserCheck}
                etiqueta="Actualizados"
                valor={resultado.resumen.actualizados}
                activa={filtroFilas === "actualizado"}
                onClick={() => alternarFiltro("actualizado")}
              />
              <TarjetaKpi
                icono={Copy}
                tono="neutro"
                etiqueta="Duplicados"
                valor={resultado.resumen.duplicados}
                activa={filtroFilas === "duplicado"}
                onClick={() => alternarFiltro("duplicado")}
              />
              <TarjetaKpi
                icono={XCircle}
                tono="neutro"
                etiqueta="Errores"
                valor={<span className={resultado.resumen.errores > 0 ? "text-red-700 dark:text-red-300" : ""}>{resultado.resumen.errores}</span>}
                activa={filtroFilas === "error"}
                onClick={() => alternarFiltro("error")}
              />
              <TarjetaKpi
                icono={FileWarning}
                tono="neutro"
                etiqueta="Datos incompletos"
                valor={resultado.filas_con_datos_incompletos}
                activa={filtroFilas === "incompletas"}
                onClick={() => alternarFiltro("incompletas")}
              />
            </div>

            <div ref={filasPreviewRef} className="max-h-150 overflow-auto rounded-xl border border-border dark:border-border-dark">
              <table className="w-full min-w-[44rem] border-collapse text-sm">
                <thead className="sticky top-0 z-10">
                  <TheadFila>
                    <Th className="px-4 py-2.5">Fila</Th>
                    <Th className="px-4 py-2.5">Acción</Th>
                    <Th className="px-4 py-2.5">Código</Th>
                    <Th className="px-4 py-2.5">Nombre</Th>
                    <Th className="px-4 py-2.5">Sección</Th>
                    <Th className="px-4 py-2.5">Observaciones</Th>
                  </TheadFila>
                </thead>
                <tbody>
                  {filasVisibles.length === 0 && (
                    <tr>
                      <td colSpan={6} className="px-4 py-8 text-center text-sm text-ink/40 dark:text-ink-dark/40">
                        Ninguna fila en esta categoría.
                      </td>
                    </tr>
                  )}
                  {/* 🆕 Fila-colchón de arriba: el espacio de las filas virtuales
                      todavía no renderizadas antes de la ventana visible — el
                      truco estándar de TanStack Virtual para tablas HTML reales
                      (nunca position:absolute sobre <tr>, que rompe el layout
                      de tabla nativo). */}
                  {virtualizadorFilas.getVirtualItems().length > 0 && (
                    <tr style={{ height: virtualizadorFilas.getVirtualItems()[0].start }} aria-hidden>
                      <td colSpan={6} />
                    </tr>
                  )}
                  {virtualizadorFilas.getVirtualItems().map((item) => {
                    const fila = filasVisibles[item.index];
                    const bloqueante = filaEsBloqueante(fila);
                    const incompleta = !bloqueante && fila.datos_incompletos.length > 0;
                    return (
                      <tr
                        key={fila.fila}
                        data-index={item.index}
                        ref={virtualizadorFilas.measureElement}
                        className={`border-b border-l-4 border-border dark:border-border-dark last:border-b-0 ${
                          bloqueante
                            ? "border-l-red-400 bg-red-50/50 dark:bg-red-500/[0.06]"
                            : incompleta
                              ? "border-l-ink/20 bg-mist/40 dark:bg-surface-raised-dark"
                              : "border-l-transparent"
                        }`}
                      >
                        <td className="px-4 py-2.5 font-mono text-xs text-ink/50 dark:text-ink-dark/50">{fila.fila}</td>
                        <td className="px-4 py-2.5">
                          <BadgeAccion accion={fila.accion} />
                        </td>
                        <td className="px-4 py-2.5 font-mono text-xs text-ink/70 dark:text-ink-dark/70">{fila.codigo_institucional || "—"}</td>
                        <td className="px-4 py-2.5 font-medium text-ink dark:text-ink-dark">
                          {[fila.nombres, fila.apellidos].filter(Boolean).join(" ") || "—"}
                        </td>
                        <td className="px-4 py-2.5 text-ink/70 dark:text-ink-dark/70">
                          {fila.estructura_academica
                            ? [fila.estructura_academica.nivel, fila.estructura_academica.grado, fila.estructura_academica.seccion]
                                .filter(Boolean)
                                .join(" · ") || "—"
                            : "—"}
                        </td>
                        <td className="px-4 py-2.5">
                          {fila.errores.length > 0 && (
                            <ul className="m-0 list-none p-0 space-y-1">
                              {fila.errores.map((e, i) => (
                                <li key={i} className="text-xs text-red-700 dark:text-red-300">
                                  <span className="font-medium">{e.campo}:</span> {e.correccion_esperada}
                                </li>
                              ))}
                            </ul>
                          )}
                          {incompleta && <span className="text-xs text-ink/50 dark:text-ink-dark/50">Faltan: {fila.datos_incompletos.join(", ")}</span>}
                          {!bloqueante && !incompleta && <span className="text-xs text-ink/30 dark:text-ink-dark/30">—</span>}
                        </td>
                      </tr>
                    );
                  })}
                  {/* 🆕 Fila-colchón de abajo: espacio de las filas virtuales
                      todavía no renderizadas después de la ventana visible. */}
                  {virtualizadorFilas.getVirtualItems().length > 0 && (
                    <tr
                      style={{
                        height:
                          virtualizadorFilas.getTotalSize() -
                          virtualizadorFilas.getVirtualItems()[virtualizadorFilas.getVirtualItems().length - 1].end,
                      }}
                      aria-hidden
                    >
                      <td colSpan={6} />
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* =================== 4. Confirmar =================== */}
          <div className="sticky bottom-0 border-t border-border dark:border-border-dark bg-surface/95 dark:bg-surface-dark/95 backdrop-blur px-4 py-3 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <div className="text-[12.5px] text-ink/65 dark:text-ink-dark/65">
              <p className="m-0">
                <span className="text-ink/40 dark:text-ink-dark/40 font-bold mr-1">4.</span>
                Se aplicarán <strong className="text-teal-800 dark:text-teal-accent-dark">{filasAplicables}</strong> fila(s) en una sola operación
                {filasDescartadas > 0 && (
                  <>
                    {" "}
                    · <strong className="text-red-700 dark:text-red-300">{filasDescartadas}</strong> duplicada(s) o con error no se escribirán
                  </>
                )}
                .
              </p>
              <TextoError className="mt-1 text-sm">{errorConfirmar}</TextoError>
            </div>
            <Boton
              onClick={confirmarImportacion}
              disabled={!puedeConfirmar || confirmando || filasAplicables === 0}
              className="inline-flex items-center justify-center gap-2 shrink-0"
            >
              <CheckCircle2 size={15} aria-hidden="true" />
              {confirmando ? "Aplicando…" : `Confirmar importación (${filasAplicables} filas)`}
            </Boton>
          </div>
        </section>
      )}
    </div>
  );
}
