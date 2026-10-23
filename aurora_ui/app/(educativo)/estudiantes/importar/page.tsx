"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { useVirtualizer } from "@tanstack/react-virtual";
import { apiClient, descargarBlob } from "@/lib/api-client";
import { useAuth } from "@/contexts/AuthContext";
import { TextoError } from "@/components/ui/TextoError";
import { TheadFila, Th } from "@/components/ui/Tabla";
import type {
  ImportacionAccionFila,
  ImportacionConfirmacionResultado,
  ImportacionFilaValidacion,
  ImportacionValidacionResultado,
} from "@/types/api";

const ETIQUETA_ACCION: Record<ImportacionAccionFila, string> = {
  nuevo: "Nuevo",
  actualizado: "Actualizado",
  duplicado: "Duplicado en archivo",
  error: "Error",
};

const ESTILO_BADGE_ACCION: Record<ImportacionAccionFila, string> = {
  nuevo: "bg-teal-600/10 text-teal-900",
  actualizado: "bg-teal-400/20 text-teal-900",
  duplicado: "bg-ink/10 text-ink/70",
  error: "bg-red-100 text-red-700",
};

// "Bloqueante" = la fila nunca se escribe (mismo criterio que el backend:
// solo 'nuevo'/'actualizado' se aplican en /confirmar). 'duplicado' y
// 'error' comparten el mismo tratamiento visual de alerta porque, para
// quien importa, ambos significan lo mismo: "corrige esto antes de seguir".
function filaEsBloqueante(fila: ImportacionFilaValidacion): boolean {
  return fila.accion === "error" || fila.accion === "duplicado";
}

function BadgeAccion({ accion }: { accion: ImportacionAccionFila }) {
  return (
    <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${ESTILO_BADGE_ACCION[accion]}`}>
      {ETIQUETA_ACCION[accion]}
    </span>
  );
}

function Chip({
  etiqueta,
  valor,
  tono,
}: {
  etiqueta: string;
  valor: number;
  tono: "teal" | "teal-suave" | "neutro" | "alerta";
}) {
  const estilo =
    tono === "alerta"
      ? valor > 0
        ? "bg-red-50 text-red-700 border-red-200"
        : "bg-mist text-ink/40 border-border"
      : tono === "teal"
      ? "bg-teal-600/10 text-teal-900 border-teal-600/20"
      : tono === "teal-suave"
      ? "bg-teal-400/15 text-teal-900 border-teal-400/30"
      : "bg-mist text-ink/70 border-border";
  return (
    <div className={`rounded-card border px-3.5 py-2 min-w-[92px] ${estilo}`}>
      <div className="font-display text-xl font-semibold leading-none">{valor}</div>
      <div className="mt-1 text-xs">{etiqueta}</div>
    </div>
  );
}

function PasoCard({
  numero,
  titulo,
  descripcion,
  children,
}: {
  numero: number;
  titulo: string;
  descripcion?: string;
  children: React.ReactNode;
}) {
  return (
    <section>
      <div className="flex items-start gap-3 mb-4">
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-teal-600 text-sm font-semibold text-white">
          {numero}
        </span>
        <div>
          <h2 className="font-display text-lg font-semibold text-teal-900">{titulo}</h2>
          {descripcion && <p className="mt-0.5 text-sm text-ink/60">{descripcion}</p>}
        </div>
      </div>
      <div className="ml-10 rounded-card border border-border bg-white p-6 shadow-sm">{children}</div>
    </section>
  );
}

export default function ImportarEstudiantesPage() {
  const { sesion } = useAuth();
  const [inputKey, setInputKey] = useState(0);

  const [descargandoPlantilla, setDescargandoPlantilla] = useState(false);
  const [errorPlantilla, setErrorPlantilla] = useState<string | null>(null);

  const [archivo, setArchivo] = useState<File | null>(null);
  const [archivoValidado, setArchivoValidado] = useState<File | null>(null);
  const [validando, setValidando] = useState(false);
  const [errorValidar, setErrorValidar] = useState<string | null>(null);
  const [resultado, setResultado] = useState<ImportacionValidacionResultado | null>(null);

  const [confirmando, setConfirmando] = useState(false);
  const [errorConfirmar, setErrorConfirmar] = useState<string | null>(null);
  const [resultadoConfirmacion, setResultadoConfirmacion] = useState<ImportacionConfirmacionResultado | null>(null);

  // 🆕 Virtualización de la vista previa (hallazgo de escala, docs/gaps-
  // pendientes.md) — un archivo real puede traer hasta FILAS_MAXIMAS=2000
  // filas; renderizar las 2000 como <tr> reales degradaba el navegador
  // mucho antes de llegar al tope. El hook es incondicional (regla de
  // hooks de React) aunque `resultado` todavía sea null al montar — por
  // eso cuenta sobre `resultado?.filas.length ?? 0`, nunca sobre `resultado!`.
  const filasPreviewRef = useRef<HTMLDivElement>(null);
  const virtualizadorFilas = useVirtualizer({
    count: resultado?.filas.length ?? 0,
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
    } catch (err: any) {
      setErrorPlantilla(err.message || "No se pudo descargar la plantilla.");
    } finally {
      setDescargandoPlantilla(false);
    }
  }

  function elegirArchivo(e: React.ChangeEvent<HTMLInputElement>) {
    const elegido = e.target.files?.[0] ?? null;
    setArchivo(elegido);
    // Un archivo nuevo invalida cualquier vista previa/confirmación anterior:
    // confirmar siempre debe corresponder al último archivo validado.
    setArchivoValidado(null);
    setResultado(null);
    setResultadoConfirmacion(null);
    setErrorValidar(null);
    setErrorConfirmar(null);
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
    } catch (err: any) {
      setErrorValidar(err.message || "No se pudo validar el archivo.");
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
    } catch (err: any) {
      setErrorConfirmar(err.message || "No se pudo confirmar la importación.");
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
    setInputKey((k) => k + 1);
  }

  const puedeConfirmar = archivoValidado !== null && resultado !== null && !resultadoConfirmacion;

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
      <div className="max-w-5xl mx-auto px-6 py-8">
        <TextoError>Esta sección es solo para psicólogos y administradores de tu institución.</TextoError>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto px-6 py-8 space-y-10">
      {/* Cabecera */}
      <div>
        <Link href="/estudiantes" className="text-sm font-medium text-teal-600 hover:text-teal-900">
          ← Volver al padrón
        </Link>
        <h1 className="mt-2 font-display text-3xl font-semibold text-teal-900 tracking-tight">
          Importar estudiantes desde Excel
        </h1>
        <p className="mt-1 max-w-2xl text-sm text-ink/60">
          Da de alta o actualiza estudiantes en bloque. Nada se guarda hasta que confirmes — puedes validar el
          archivo cuantas veces necesites mientras corriges los datos.
        </p>
      </div>

      <PasoCard
        numero={1}
        titulo="Descarga la plantilla"
        descripcion="Incluye ejemplos y, en una segunda hoja, la estructura académica ya creada en tu institución."
      >
        <button
          onClick={descargarPlantilla}
          disabled={descargandoPlantilla}
          className="rounded-card bg-teal-600 px-4 py-2 text-sm font-medium text-white hover:bg-teal-900 transition-colors shadow-sm disabled:opacity-60"
        >
          {descargandoPlantilla ? "Descargando…" : "Descargar plantilla .xlsx"}
        </button>
        {errorPlantilla && <p className="mt-3 text-sm text-red-700">{errorPlantilla}</p>}
      </PasoCard>

      <PasoCard
        numero={2}
        titulo="Sube y valida tu archivo"
        descripcion="Validar nunca escribe nada en la base — repítelo tantas veces como quieras mientras corriges el Excel."
      >
        <div className="flex flex-wrap items-center gap-3">
          <input
            key={inputKey}
            type="file"
            accept=".xlsx"
            onChange={elegirArchivo}
            className="cursor-pointer text-sm text-ink file:mr-3 file:cursor-pointer file:rounded-card file:border-0 file:bg-mist file:px-3 file:py-2 file:text-sm file:font-medium file:text-ink hover:file:bg-border/60"
          />
          <button
            onClick={validarArchivo}
            disabled={!archivo || validando}
            className="rounded-card bg-teal-600 px-4 py-2 text-sm font-medium text-white hover:bg-teal-900 transition-colors shadow-sm disabled:cursor-not-allowed disabled:opacity-40"
          >
            {validando ? "Validando…" : "Validar archivo"}
          </button>
          {(archivo || resultado) && (
            <button onClick={reiniciar} className="text-sm text-ink/50 hover:text-ink hover:underline">
              Empezar de nuevo
            </button>
          )}
        </div>
        {errorValidar && <p className="mt-3 text-sm text-red-700">{errorValidar}</p>}
      </PasoCard>

      {resultado && (
        <PasoCard numero={3} titulo="Revisa la vista previa" descripcion={`${resultado.total_filas} filas leídas del archivo.`}>
          <div className="mb-5 flex flex-wrap gap-3">
            <Chip etiqueta="Nuevos" valor={resultado.resumen.nuevos} tono="teal" />
            <Chip etiqueta="Actualizados" valor={resultado.resumen.actualizados} tono="teal-suave" />
            <Chip etiqueta="Duplicados" valor={resultado.resumen.duplicados} tono="neutro" />
            <Chip etiqueta="Errores" valor={resultado.resumen.errores} tono="alerta" />
            <Chip etiqueta="Datos incompletos" valor={resultado.filas_con_datos_incompletos} tono="neutro" />
          </div>

          <div ref={filasPreviewRef} className="max-h-150 overflow-auto rounded-card border border-border">
            <table className="w-full border-collapse text-sm">
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
                  const fila = resultado.filas[item.index];
                  const bloqueante = filaEsBloqueante(fila);
                  const incompleta = !bloqueante && fila.datos_incompletos.length > 0;
                  return (
                    <tr
                      key={fila.fila}
                      data-index={item.index}
                      ref={virtualizadorFilas.measureElement}
                      className={`border-b border-l-4 border-border last:border-b-0 ${
                        bloqueante
                          ? "border-l-red-400 bg-red-50/50"
                          : incompleta
                          ? "border-l-ink/20 bg-mist/40"
                          : "border-l-transparent"
                      }`}
                    >
                      <td className="px-4 py-2.5 font-mono text-xs text-ink/50">{fila.fila}</td>
                      <td className="px-4 py-2.5">
                        <BadgeAccion accion={fila.accion} />
                      </td>
                      <td className="px-4 py-2.5 font-mono text-xs text-ink/70">
                        {fila.codigo_institucional || "—"}
                      </td>
                      <td className="px-4 py-2.5 text-ink">
                        {[fila.nombres, fila.apellidos].filter(Boolean).join(" ") || "—"}
                      </td>
                      <td className="px-4 py-2.5 text-ink/70">
                        {fila.estructura_academica
                          ? [fila.estructura_academica.nivel, fila.estructura_academica.grado, fila.estructura_academica.seccion]
                              .filter(Boolean)
                              .join(" · ") || "—"
                          : "—"}
                      </td>
                      <td className="px-4 py-2.5">
                        {fila.errores.length > 0 && (
                          <ul className="space-y-1">
                            {fila.errores.map((e, i) => (
                              <li key={i} className="text-xs text-red-700">
                                <span className="font-medium">{e.campo}:</span> {e.correccion_esperada}
                              </li>
                            ))}
                          </ul>
                        )}
                        {incompleta && (
                          <span className="text-xs text-ink/50">Faltan: {fila.datos_incompletos.join(", ")}</span>
                        )}
                        {!bloqueante && !incompleta && <span className="text-xs text-ink/30">—</span>}
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
        </PasoCard>
      )}

      {resultado && !resultadoConfirmacion && (
        <PasoCard
          numero={4}
          titulo="Confirma la importación"
          descripcion="Aplica en una sola operación todas las filas 'Nuevo' y 'Actualizado'. Las filas duplicadas o con error nunca se escriben."
        >
          <button
            onClick={confirmarImportacion}
            disabled={!puedeConfirmar || confirmando}
            className="rounded-card bg-teal-600 px-4 py-2 text-sm font-medium text-white hover:bg-teal-900 transition-colors shadow-sm disabled:cursor-not-allowed disabled:opacity-40"
          >
            {confirmando
              ? "Aplicando…"
              : `Confirmar importación (${resultado.resumen.nuevos + resultado.resumen.actualizados} filas)`}
          </button>
          {errorConfirmar && <p className="mt-3 text-sm text-red-700">{errorConfirmar}</p>}
        </PasoCard>
      )}

      {resultadoConfirmacion && (
        <PasoCard numero={5} titulo="Importación aplicada">
          <div className="mb-5 flex flex-wrap gap-3">
            <Chip etiqueta="Nuevos" valor={resultadoConfirmacion.resumen.nuevos} tono="teal" />
            <Chip etiqueta="Actualizados" valor={resultadoConfirmacion.resumen.actualizados} tono="teal-suave" />
          </div>
          <div className="flex items-center gap-4">
            <Link
              href="/estudiantes"
              className="rounded-card bg-teal-600 px-4 py-2 text-sm font-medium text-white hover:bg-teal-900 transition-colors shadow-sm"
            >
              Ver en el padrón
            </Link>
            <button onClick={reiniciar} className="text-sm font-medium text-teal-600 hover:text-teal-900 hover:underline">
              Importar otro archivo
            </button>
          </div>
        </PasoCard>
      )}
    </div>
  );
}
