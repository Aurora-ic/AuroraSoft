"use client";

import { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { apiClient, descargarBlob, ApiError } from "@/lib/api-client";
import { Boton } from "@/components/ui/Boton";
import { TextoError } from "@/components/ui/TextoError";
import type {
  RegistroAlumnoDemograficos,
  IntakeExamen,
  AsentimientoInformadoTextoPublico,
  CampoSociodemografico,
  PreguntaExamen,
  ProgresoExamen,
  DiagnosticoAlumno,
  EstadoResultadosAlumno,
} from "@/types/api";

// Flujo público, sin sesión: 1) datos sociodemográficos + asentimiento
// (comenzar-test, también reanuda un examen "En Progreso") — primero se
// consulta /intake para no volver a pedir lo que el colegio ya cargó al
// matricular por padrón, 2) campos sociodemográficos propios de la
// institución (si tiene alguno configurado — la mayoría no), 3) preguntas
// con autoguardado por respuesta (resumible: progreso ya contestado se
// precarga), 4) finalizar y mostrar el estado de revisión / descargar el
// informe si ya está liberado.
type Fase = "intake" | "socio" | "preguntas" | "finalizado" | "error_terminal";

// 🆕 Lo que el alumno respondió para UNA pregunta: un opcion_id (opción
// múltiple) o una lista de números (ítem "numerico", ver PreguntaExamen.
// tipo_respuesta/cantidad_valores_numericos en types/api.ts).
type RespuestaValor = number | number[];

export default function ExamenPage() {
  const params = useParams<{ token: string }>();
  const token = params.token;

  const [fase, setFase] = useState<Fase>("intake");
  const [errorTerminal, setErrorTerminal] = useState<string | null>(null);

  // --- Fase 1: intake (demográficos + asentimiento) ---
  const [intake, setIntake] = useState<RegistroAlumnoDemograficos>({
    nombre_completo: "",
    edad: 0,
    sexo: "Masculino",
    poblacion: "Secundaria",
    acepta_terminos: false,
    informante_nombre: "",
    informante_relacion: "",
  });
  const [intakePrevio, setIntakePrevio] = useState<IntakeExamen | null>(null);
  const [cargandoIntakePrevio, setCargandoIntakePrevio] = useState(true);
  const [enviandoIntake, setEnviandoIntake] = useState(false);
  const [errorIntake, setErrorIntake] = useState<string | null>(null);

  // 🆕 Texto real del asentimiento informado (ver GET .../asentimiento-texto
  // en el backend) -- reemplaza la constante fija que vivía acá antes,
  // configurable y versionada por institución (o global por defecto). A
  // diferencia de /intake, un fallo SÍ se muestra como error visible: sin
  // texto que mostrar no hay nada que el alumno esté aceptando de verdad.
  const [asentimientoTexto, setAsentimientoTexto] = useState<AsentimientoInformadoTextoPublico | null>(null);
  const [errorAsentimientoTexto, setErrorAsentimientoTexto] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    apiClient
      .get<AsentimientoInformadoTextoPublico>(`/educativo/examen/${token}/asentimiento-texto`)
      .then(setAsentimientoTexto)
      .catch((err: any) =>
        setErrorAsentimientoTexto(
          err.message || "No se pudo cargar el texto de asentimiento informado. Contacta a tu colegio."
        )
      );
  }, [token]);

  // 🆕 Antes de mostrar el formulario, averiguamos qué datos ya tiene esta
  // inscripción (nombre/edad/sexo/nivel, cuando viene de una matrícula por
  // padrón) para no volver a pedirlos — ver GET .../intake. Si falla (link
  // inválido, expirado, etc.) no bloqueamos nada aquí: el intento real de
  // comenzar-test ya da el error correcto cuando el alumno envíe el form.
  useEffect(() => {
    if (!token) return;
    apiClient
      .get<IntakeExamen>(`/educativo/examen/${token}/intake`)
      .then((datos) => {
        setIntakePrevio(datos);
        setIntake((prev) => ({
          ...prev,
          nombre_completo: datos.nombre_completo ?? prev.nombre_completo,
          edad: datos.edad ?? prev.edad,
          sexo: (datos.sexo as RegistroAlumnoDemograficos["sexo"]) ?? prev.sexo,
          poblacion: (datos.poblacion as RegistroAlumnoDemograficos["poblacion"]) ?? prev.poblacion,
        }));
      })
      .catch(() => {
        // Silencioso a propósito: el formulario simplemente se ve como
        // siempre (todo editable) y comenzar-test informará el error real.
      })
      .finally(() => setCargandoIntakePrevio(false));
  }, [token]);

  // --- Fase 2: campos sociodemográficos propios de la institución ---
  const [camposSocio, setCamposSocio] = useState<CampoSociodemografico[]>([]);
  const [valoresSocio, setValoresSocio] = useState<Record<number, string>>({});
  const [enviandoSocio, setEnviandoSocio] = useState(false);
  const [errorSocio, setErrorSocio] = useState<string | null>(null);

  // --- Fase 3: preguntas ---
  const [preguntas, setPreguntas] = useState<PreguntaExamen[]>([]);
  // 🆕 pregunta_id -> opcion_id (opción múltiple) O respuesta_numerica
  // (ítem Pregunta.tipo_respuesta="numerico", ej. BARSIT "Razonamiento
  // numérico") — optimista, puede no estar confirmado en el servidor
  // todavía. Un mismo pregunta_id es siempre de un solo tipo, nunca ambiguo.
  const [respuestas, setRespuestas] = useState<Record<number, RespuestaValor>>({});
  // 🆕 Lo que el alumno va escribiendo en cada campo numérico de un ítem
  // "numerico" ANTES de que estén todos los campos llenos — una respuesta
  // parcial no dispara guardado (mismo criterio que elegir una opción: es
  // un evento atómico, no una tecla a la vez).
  const [borradorNumerico, setBorradorNumerico] = useState<Record<number, string[]>>({});
  const [errorPreguntas, setErrorPreguntas] = useState<string | null>(null);
  // 🆕 Antes era un solo id — con el autoguardado ahora serializado por
  // pregunta (ver elegirOpcion), dos preguntas distintas pueden estar
  // guardándose en paralelo sin problema, así que necesita ser un conjunto.
  const [guardandoPreguntaIds, setGuardandoPreguntaIds] = useState<Set<number>>(new Set());
  const [errorGuardar, setErrorGuardar] = useState<string | null>(null);
  const [finalizando, setFinalizando] = useState(false);
  const [errorFinalizar, setErrorFinalizar] = useState<string | null>(null);

  // 🆕 Hallazgo de auditoría (sesión 2026-10-16): `elegirOpcion` actualizaba
  // `respuestas` de forma optimista pero nunca revertía ese cambio si el
  // `POST .../guardar` fallaba — el backend NO valida que todas las
  // preguntas tengan una RespuestaAlumno real antes de finalizar (solo suma
  // lo que de verdad llegó a guardarse), así que una respuesta que el
  // alumno ve marcada pero que nunca se guardó podía colarse hasta
  // "Finalizar" sin ningún aviso, silenciosamente alterando el puntaje. Tres
  // piezas cierran esto:
  // 1. `confirmadoRef`: la última respuesta que el servidor SÍ confirmó
  //    guardada, por pregunta — a dónde hacer rollback si un intento falla.
  // 2. `colaPorPreguntaRef`: encadena los intentos de guardado de la MISMA
  //    pregunta (nunca entre preguntas distintas) para que, si el alumno
  //    cambia de opción varias veces rápido, los POST lleguen al backend en
  //    el mismo orden en que se hicieron los clics — nunca fuera de orden.
  // 3. `intentoVigentePorPreguntaRef`: si un intento falla pero ya hay uno
  //    más nuevo encolado para esa misma pregunta, el rollback se omite —
  //    el resultado de ese intento más nuevo es el que debe decidir el
  //    estado visible final, no el fallido que ya quedó obsoleto.
  const confirmadoRef = useRef<Record<number, RespuestaValor | undefined>>({});
  const colaPorPreguntaRef = useRef<Record<number, Promise<void>>>({});
  const intentoVigentePorPreguntaRef = useRef<Record<number, number>>({});

  // --- Fase 4: finalizado ---
  const [diagnosticos, setDiagnosticos] = useState<DiagnosticoAlumno[] | null>(null);
  const [estadoResultados, setEstadoResultados] = useState<EstadoResultadosAlumno | null>(null);
  const [descargando, setDescargando] = useState(false);

  async function enviarIntake(e: React.FormEvent) {
    e.preventDefault();
    // 🔧 El checkbox de asentimiento se puede marcar antes de que
    // `asentimientoTexto` termine de cargar (o si falló la carga) — sin
    // esta guarda, un alumno podía aceptar y enviar sin que nunca se le
    // mostrara el texto real (regresión de cumplimiento frente a la
    // constante fija que esto reemplazó). El checkbox de abajo también
    // queda deshabilitado mientras no haya texto cargado, pero un campo
    // deshabilitado no se valida como "required" en el navegador, así que
    // la guarda real tiene que estar aquí.
    if (!asentimientoTexto) {
      setErrorIntake("Todavía no se cargó el texto de asentimiento informado. Espera un momento y vuelve a intentar.");
      return;
    }
    setEnviandoIntake(true);
    setErrorIntake(null);
    try {
      await apiClient.post(`/educativo/comenzar-test/${token}`, intake);
      await cargarSiguientePaso();
    } catch (err: any) {
      if (err.status === 409) {
        // Ya estaba Finalizado -- no es un error, vamos directo al estado.
        await irAFinalizado();
      } else if (err.status === 410) {
        setFase("error_terminal");
        setErrorTerminal(err.message);
      } else {
        setErrorIntake(err.message || "No se pudo comenzar la evaluación.");
      }
    } finally {
      setEnviandoIntake(false);
    }
  }

  async function cargarSiguientePaso() {
    try {
      const campos = await apiClient.get<CampoSociodemografico[]>(`/educativo/examen/${token}/campos-socio`);
      if (campos.length > 0) {
        setCamposSocio(campos);
        setFase("socio");
        return;
      }
    } catch {
      // Si falla, no bloqueamos el examen por esto -- seguimos a preguntas.
    }
    await cargarPreguntas();
  }

  async function enviarSocio(e: React.FormEvent) {
    e.preventDefault();
    setEnviandoSocio(true);
    setErrorSocio(null);
    try {
      await apiClient.post(`/educativo/examen/${token}/campos-socio`, {
        respuestas: Object.entries(valoresSocio).map(([campo_id, valor]) => ({ campo_id: Number(campo_id), valor })),
      });
      await cargarPreguntas();
    } catch (err: any) {
      setErrorSocio(err.message || "No se pudieron guardar tus datos.");
    } finally {
      setEnviandoSocio(false);
    }
  }

  async function cargarPreguntas() {
    setErrorPreguntas(null);
    try {
      const [listaPreguntas, progreso] = await Promise.all([
        apiClient.get<PreguntaExamen[]>(`/educativo/examen/${token}/preguntas`),
        apiClient.get<ProgresoExamen>(`/educativo/examen/${token}/progreso`),
      ]);
      setPreguntas(listaPreguntas);
      const previas: Record<number, RespuestaValor> = {};
      const borrador: Record<number, string[]> = {};
      listaPreguntas.forEach((p) => {
        if (p.tipo_respuesta === "numerico") {
          borrador[p.id] = Array.from({ length: p.cantidad_valores_numericos ?? 0 }, () => "");
        }
      });
      progreso.respuestas.forEach((r) => {
        if (r.respuesta_numerica) {
          previas[r.pregunta_id] = r.respuesta_numerica;
          borrador[r.pregunta_id] = r.respuesta_numerica.map((n) => String(n));
        } else if (r.opcion_id != null) {
          previas[r.pregunta_id] = r.opcion_id;
        }
      });
      setRespuestas(previas);
      setBorradorNumerico(borrador);
      confirmadoRef.current = { ...previas }; // lo que ya está confirmado en el servidor al cargar
      setFase("preguntas");
    } catch (err: any) {
      setErrorPreguntas(err.message || "No se pudieron cargar las preguntas.");
    }
  }

  // Se marca "en vuelo" ANTES de encolar — así `finalizar()` nota el intento
  // aunque la cadena de esta pregunta ya estuviera corriendo.
  function elegirOpcion(preguntaId: number, opcionId: number) {
    setRespuestas((prev) => ({ ...prev, [preguntaId]: opcionId }));
    setErrorGuardar(null);

    const miIntento = (intentoVigentePorPreguntaRef.current[preguntaId] ?? 0) + 1;
    intentoVigentePorPreguntaRef.current[preguntaId] = miIntento;
    setGuardandoPreguntaIds((prev) => new Set(prev).add(preguntaId));

    // Encadenado sobre la cola de ESA pregunta (nunca sobre las demás): si
    // el alumno cambia de opción varias veces rápido, cada POST espera a
    // que el anterior termine, así que siempre llegan al backend en el
    // mismo orden en que se hicieron los clics.
    const anterior = colaPorPreguntaRef.current[preguntaId] ?? Promise.resolve();
    colaPorPreguntaRef.current[preguntaId] = anterior.then(() =>
      guardarRespuestaConReintento(preguntaId, opcionId, miIntento)
    );
  }

  // 🆕 Equivalente de `elegirOpcion` para un ítem Pregunta.tipo_respuesta=
  // "numerico" (ej. BARSIT "Razonamiento numérico") — `valores` ya viene
  // completo (todos los campos llenos con un entero válido), decidido por
  // `actualizarValorNumerico` más abajo. El resto del mecanismo (cola por
  // pregunta, reintento, rollback) es exactamente el mismo que una opción.
  function elegirNumerico(preguntaId: number, valores: number[]) {
    setRespuestas((prev) => ({ ...prev, [preguntaId]: valores }));
    setErrorGuardar(null);

    const miIntento = (intentoVigentePorPreguntaRef.current[preguntaId] ?? 0) + 1;
    intentoVigentePorPreguntaRef.current[preguntaId] = miIntento;
    setGuardandoPreguntaIds((prev) => new Set(prev).add(preguntaId));

    const anterior = colaPorPreguntaRef.current[preguntaId] ?? Promise.resolve();
    colaPorPreguntaRef.current[preguntaId] = anterior.then(() =>
      guardarRespuestaConReintento(preguntaId, valores, miIntento)
    );
  }

  // 🆕 Actualiza UN campo (de los `cantidadEsperada` que tiene este ítem
  // numérico) a medida que el alumno escribe. Solo dispara guardado cuando
  // TODOS los campos de la pregunta tienen un entero válido — una
  // respuesta parcial (un blanco vacío, o con texto no numérico) no es
  // todavía "una respuesta", igual que elegir una opción es un evento
  // atómico y no una tecla a la vez. `Number("")` da 0 en JS (no NaN), así
  // que un campo vacío se mapea a NaN explícitamente antes de validar.
  function actualizarValorNumerico(preguntaId: number, indice: number, cantidadEsperada: number, texto: string) {
    setErrorGuardar(null);
    // 🔧 `elegirNumerico` (incrementa un ref, encola un POST real, dispara
    // más setState) vivía DENTRO del updater de `setBorradorNumerico` — un
    // updater de React debe ser puro porque puede llegar a ejecutarse más
    // de una vez (p. ej. en StrictMode), lo que duplicaría el intento y el
    // POST para la misma respuesta. `actual` se calcula ahora a partir del
    // estado ya comprometido en este render (una sola llamada por evento
    // onChange, nunca concurrente con otra escritura a esta misma
    // pregunta), y `elegirNumerico` se llama por fuera del updater.
    const actual = borradorNumerico[preguntaId]
      ? [...borradorNumerico[preguntaId]]
      : Array.from({ length: cantidadEsperada }, () => "");
    actual[indice] = texto;
    setBorradorNumerico((prev) => ({ ...prev, [preguntaId]: actual }));

    const valores = actual.map((v) => (v.trim() === "" ? NaN : Number(v)));
    if (valores.every((v) => Number.isInteger(v))) {
      elegirNumerico(preguntaId, valores);
    }
  }

  async function guardarRespuestaConReintento(
    preguntaId: number, valor: RespuestaValor, miIntento: number, intentosRestantes = 2
  ) {
    try {
      const cuerpo = Array.isArray(valor)
        ? { pregunta_id: preguntaId, respuesta_numerica: valor }
        : { pregunta_id: preguntaId, opcion_id: valor };
      await apiClient.post(`/educativo/examen/${token}/guardar`, { respuestas: [cuerpo] });
      confirmadoRef.current[preguntaId] = valor;
    } catch (err: any) {
      // Un ApiError es una respuesta HTTP real de error (4xx/5xx) — repetir
      // el mismo cuerpo fallaría otra vez. Cualquier otra excepción (el
      // fetch nunca llegó a completarse: red caída, DNS, etc.) sí vale la
      // pena reintentar un par de veces antes de darse por vencido.
      if (!(err instanceof ApiError) && intentosRestantes > 0) {
        await new Promise((resolver) => setTimeout(resolver, 800));
        return guardarRespuestaConReintento(preguntaId, valor, miIntento, intentosRestantes - 1);
      }
      // Solo se revierte si NINGÚN intento más nuevo ya quedó encolado para
      // esta misma pregunta — si lo hay, es ese el que debe decidir el
      // estado visible final, no este, que ya quedó obsoleto.
      if (intentoVigentePorPreguntaRef.current[preguntaId] === miIntento) {
        setErrorGuardar(err.message || "No se pudo guardar esta respuesta. Vuelve a intentarlo.");
        const valorConfirmado = confirmadoRef.current[preguntaId];
        setRespuestas((prev) => {
          const copia = { ...prev };
          if (valorConfirmado === undefined) {
            delete copia[preguntaId];
          } else {
            copia[preguntaId] = valorConfirmado;
          }
          return copia;
        });
        // Si el intento fallido era de un ítem numérico, el cuadro de texto
        // vuelve a reflejar lo último confirmado (o se vacía si nunca hubo
        // nada confirmado) — si no, el alumno vería los números tal como
        // los escribió, sin saber que en realidad no se guardaron.
        if (Array.isArray(valor)) {
          setBorradorNumerico((prev) => ({
            ...prev,
            [preguntaId]: Array.isArray(valorConfirmado)
              ? valorConfirmado.map(String)
              : (prev[preguntaId] ?? valor).map(() => ""),
          }));
        }
      }
    } finally {
      if (intentoVigentePorPreguntaRef.current[preguntaId] === miIntento) {
        setGuardandoPreguntaIds((prev) => {
          const copia = new Set(prev);
          copia.delete(preguntaId);
          return copia;
        });
      }
    }
  }

  const faltanPreguntas = preguntas.filter((p) => respuestas[p.id] === undefined);
  // Mantiene una copia siempre al día de `respuestas` fuera de React, para
  // que `finalizar()` pueda leer el estado real DESPUÉS de esperar a que
  // los guardados pendientes terminen (la closure de `respuestas` en ese
  // punto seguiría siendo la de antes de esperar).
  const respuestasRef = useRef(respuestas);
  useEffect(() => {
    respuestasRef.current = respuestas;
  }, [respuestas]);

  async function finalizar() {
    if (faltanPreguntas.length > 0 || guardandoPreguntaIds.size > 0) return;
    if (!window.confirm("¿Confirmas que terminaste de responder? No podrás modificar tus respuestas después.")) {
      return;
    }
    setFinalizando(true);
    setErrorFinalizar(null);
    try {
      // 🆕 Espera a que termine de asentarse cualquier guardado todavía
      // encolado — el botón ya se deshabilita mientras `guardandoPreguntaIds`
      // no está vacío, pero esto cierra la ventana de una pregunta cuyo
      // guardado arrancó justo antes del clic en "Finalizar". Ningún intento
      // lanza — `guardarRespuestaConReintento` siempre resuelve, incluso si
      // termina revirtiendo la respuesta — así que esto nunca se cuelga.
      await Promise.all(Object.values(colaPorPreguntaRef.current));
      const faltanAhora = preguntas.filter((p) => respuestasRef.current[p.id] === undefined);
      if (faltanAhora.length > 0) {
        setErrorFinalizar(
          "Alguna respuesta no se pudo guardar. Revisa las preguntas marcadas y vuelve a seleccionarlas."
        );
        return;
      }
      const resultado = await apiClient.post<DiagnosticoAlumno[]>(`/educativo/examen/${token}/finalizar`);
      setDiagnosticos(resultado);
      await irAFinalizado();
    } catch (err: any) {
      setErrorFinalizar(err.message || "No se pudo finalizar la evaluación.");
    } finally {
      setFinalizando(false);
    }
  }

  async function irAFinalizado() {
    try {
      const estado = await apiClient.get<EstadoResultadosAlumno>(`/educativo/examen/${token}/estado-resultados`);
      setEstadoResultados(estado);
    } catch {
      // Si falla, igual mostramos la fase final con lo que ya tengamos.
    }
    setFase("finalizado");
  }

  async function descargarInforme() {
    setDescargando(true);
    try {
      const blob = await apiClient.descargarArchivo(`/educativo/examen/${token}/informe-pdf`);
      descargarBlob(blob, "mi_informe.pdf");
    } catch (err: any) {
      setErrorFinalizar(err.message || "No se pudo descargar tu informe.");
    } finally {
      setDescargando(false);
    }
  }

  if (fase === "error_terminal") {
    return (
      <div className="bg-white rounded-card border border-border p-8">
        <h1 className="font-display text-xl text-teal-900 mb-2">Evaluación</h1>
        <TextoError>{errorTerminal}</TextoError>
      </div>
    );
  }

  if (fase === "intake") {
    if (cargandoIntakePrevio) {
      return (
        <div className="bg-white rounded-card border border-border p-8">
          <p className="text-sm text-ink/60">Cargando...</p>
        </div>
      );
    }

    const nombreConocido = intakePrevio?.nombre_conocido ?? false;
    const edadConocida = intakePrevio?.edad != null;
    const sexoConocido = intakePrevio?.sexo != null;
    const poblacionConocida = intakePrevio?.poblacion != null;

    return (
      <form onSubmit={enviarIntake} className="bg-white rounded-card border border-border p-8 space-y-4">
        <h1 className="font-display text-xl text-teal-900 mb-2">Antes de comenzar</h1>

        {nombreConocido ? (
          <div className="flex flex-col gap-1 text-sm">
            <span className="text-ink/70 font-medium">Nombre completo</span>
            <p className="px-3 py-2">{intake.nombre_completo}</p>
          </div>
        ) : (
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-ink/70 font-medium">Nombre completo</span>
            <input
              required
              value={intake.nombre_completo}
              onChange={(e) => setIntake({ ...intake, nombre_completo: e.target.value })}
              className="rounded-card border border-border px-3 py-2 focus:outline-none focus:ring-2 focus:ring-teal-400"
            />
          </label>
        )}

        {edadConocida ? (
          <div className="flex flex-col gap-1 text-sm">
            <span className="text-ink/70 font-medium">Edad</span>
            <p className="px-3 py-2">{intake.edad} años</p>
          </div>
        ) : (
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-ink/70 font-medium">Edad</span>
            <input
              required
              type="number"
              min={1}
              max={120}
              value={intake.edad || ""}
              onChange={(e) => setIntake({ ...intake, edad: Number(e.target.value) })}
              className="rounded-card border border-border px-3 py-2 focus:outline-none focus:ring-2 focus:ring-teal-400"
            />
          </label>
        )}

        {sexoConocido ? (
          <div className="flex flex-col gap-1 text-sm">
            <span className="text-ink/70 font-medium">Sexo</span>
            <p className="px-3 py-2">{intake.sexo}</p>
          </div>
        ) : (
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-ink/70 font-medium">Sexo</span>
            <select
              value={intake.sexo}
              onChange={(e) => setIntake({ ...intake, sexo: e.target.value as RegistroAlumnoDemograficos["sexo"] })}
              className="rounded-card border border-border px-3 py-2 focus:outline-none focus:ring-2 focus:ring-teal-400"
            >
              <option value="Masculino">Masculino</option>
              <option value="Femenino">Femenino</option>
            </select>
          </label>
        )}

        {poblacionConocida ? (
          <div className="flex flex-col gap-1 text-sm">
            <span className="text-ink/70 font-medium">Nivel</span>
            <p className="px-3 py-2">{intake.poblacion}</p>
          </div>
        ) : (
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-ink/70 font-medium">Nivel</span>
            <select
              value={intake.poblacion}
              onChange={(e) => setIntake({ ...intake, poblacion: e.target.value as RegistroAlumnoDemograficos["poblacion"] })}
              className="rounded-card border border-border px-3 py-2 focus:outline-none focus:ring-2 focus:ring-teal-400"
            >
              <option value="Primaria">Primaria</option>
              <option value="Secundaria">Secundaria</option>
              <option value="Universitario">Universitario</option>
            </select>
          </label>
        )}

        {/* Solo aplica cuando ESTA prueba la responde un padre/madre o
            docente EN NOMBRE del estudiante (Prueba.informante_tipo) — para
            el autorreporte de siempre (la inmensa mayoría) ni se pregunta.
            `informante_tipo` viene de /intake; si todavía no cargó o la
            prueba es de autorreporte, este bloque no se muestra. */}
        {intakePrevio && intakePrevio.informante_tipo !== "estudiante" && (
          <div className="space-y-2 text-sm rounded-card border border-teal-200 bg-teal-50/50 p-3">
            <p className="text-ink/70 font-medium">
              Esta evaluación la debe completar{" "}
              {intakePrevio.informante_tipo === "padre_madre" ? "el padre, madre o apoderado" : "un(a) docente"} del
              estudiante, no el estudiante mismo.
            </p>
            <input
              required
              placeholder="Tu nombre"
              value={intake.informante_nombre ?? ""}
              onChange={(e) => setIntake({ ...intake, informante_nombre: e.target.value })}
              className="w-full rounded-card border border-border px-3 py-2 focus:outline-none focus:ring-2 focus:ring-teal-400"
            />
            <input
              placeholder="Relación (ej. Madre, Docente de aula)"
              value={intake.informante_relacion ?? ""}
              onChange={(e) => setIntake({ ...intake, informante_relacion: e.target.value })}
              className="w-full rounded-card border border-border px-3 py-2 focus:outline-none focus:ring-2 focus:ring-teal-400"
            />
          </div>
        )}

        <div className="rounded-card border border-border bg-mist/40 p-4 space-y-2 text-sm">
          <h2 className="font-display text-base text-teal-900">Asentimiento informado</h2>
          {asentimientoTexto ? (
            <>
              <p className="text-ink/40 italic text-xs">Versión {asentimientoTexto.version}</p>
              <ul className="list-disc pl-5 space-y-1 text-ink/80">
                {asentimientoTexto.contenido
                  .split("\n")
                  .map((p) => p.trim())
                  .filter(Boolean)
                  .map((parrafo, i) => (
                    <li key={i}>{parrafo}</li>
                  ))}
              </ul>
            </>
          ) : errorAsentimientoTexto ? (
            <TextoError>{errorAsentimientoTexto}</TextoError>
          ) : (
            <p className="text-ink/50 text-xs">Cargando...</p>
          )}
        </div>

        <label className="flex items-start gap-2 text-sm">
          <input
            type="checkbox"
            required
            checked={intake.acepta_terminos}
            disabled={!asentimientoTexto}
            onChange={(e) => setIntake({ ...intake, acepta_terminos: e.target.checked })}
            className="mt-1"
          />
          <span>Leí la información de arriba y acepto el asentimiento informado para esta evaluación.</span>
        </label>

        <TextoError>{errorIntake}</TextoError>

        <Boton type="submit" disabled={enviandoIntake || !asentimientoTexto}>
          {enviandoIntake ? "Comenzando..." : "Comenzar"}
        </Boton>
      </form>
    );
  }

  if (fase === "socio") {
    return (
      <form onSubmit={enviarSocio} className="bg-white rounded-card border border-border p-8 space-y-4">
        <h1 className="font-display text-xl text-teal-900 mb-2">Algunos datos más</h1>
        {camposSocio.map((c) => (
          <label key={c.id} className="flex flex-col gap-1 text-sm">
            <span className="text-ink/70 font-medium">
              {c.pregunta}
              {c.obligatorio ? " *" : ""}
            </span>
            {c.tipo_respuesta === "opciones" && c.opciones ? (
              <select
                required={c.obligatorio}
                value={valoresSocio[c.id] ?? ""}
                onChange={(e) => setValoresSocio({ ...valoresSocio, [c.id]: e.target.value })}
                className="rounded-card border border-border px-3 py-2 focus:outline-none focus:ring-2 focus:ring-teal-400"
              >
                <option value="">Elige...</option>
                {c.opciones.split(",").map((op) => (
                  <option key={op.trim()} value={op.trim()}>
                    {op.trim()}
                  </option>
                ))}
              </select>
            ) : (
              <input
                required={c.obligatorio}
                type={c.tipo_respuesta === "numero" ? "number" : "text"}
                value={valoresSocio[c.id] ?? ""}
                onChange={(e) => setValoresSocio({ ...valoresSocio, [c.id]: e.target.value })}
                className="rounded-card border border-border px-3 py-2 focus:outline-none focus:ring-2 focus:ring-teal-400"
              />
            )}
          </label>
        ))}
        <TextoError>{errorSocio}</TextoError>
        <Boton type="submit" disabled={enviandoSocio}>
          {enviandoSocio ? "Guardando..." : "Continuar"}
        </Boton>
      </form>
    );
  }

  if (fase === "preguntas") {
    return (
      <div className="space-y-4">
        <div className="bg-white rounded-card border border-border p-6">
          <h1 className="font-display text-xl text-teal-900">Evaluación</h1>
          <p className="text-sm text-ink/60">
            {Object.keys(respuestas).length} de {preguntas.length} respondidas — se guarda automáticamente.
          </p>
        </div>

        <TextoError>{errorPreguntas}</TextoError>
        <TextoError>{errorGuardar}</TextoError>

        {preguntas.map((p, i) => (
          <div key={p.id} className="bg-white rounded-card border border-border p-5 space-y-2">
            <p className="text-sm font-medium text-ink">
              {i + 1}. {p.texto_pregunta}
              {guardandoPreguntaIds.has(p.id) && <span className="text-xs text-ink/40 ml-2">guardando...</span>}
            </p>
            {p.tipo_respuesta === "numerico" ? (
              <div className="flex flex-wrap items-center gap-2">
                {Array.from({ length: p.cantidad_valores_numericos ?? 0 }).map((_, idx) => (
                  <input
                    key={idx}
                    type="number"
                    inputMode="numeric"
                    aria-label={`Valor ${idx + 1} de ${p.cantidad_valores_numericos}`}
                    value={borradorNumerico[p.id]?.[idx] ?? ""}
                    onChange={(e) =>
                      actualizarValorNumerico(p.id, idx, p.cantidad_valores_numericos ?? 0, e.target.value)
                    }
                    className="w-20 rounded-card border border-border px-3 py-2 text-center focus:outline-none focus:ring-2 focus:ring-teal-400"
                  />
                ))}
              </div>
            ) : (
              <div className="space-y-1">
                {p.opciones.map((o) => (
                  <label key={o.id} className="flex items-center gap-2 text-sm cursor-pointer">
                    <input
                      type="radio"
                      name={`pregunta-${p.id}`}
                      checked={respuestas[p.id] === o.id}
                      onChange={() => elegirOpcion(p.id, o.id)}
                    />
                    {o.texto_opcion}
                  </label>
                ))}
              </div>
            )}
          </div>
        ))}

        <div className="bg-white rounded-card border border-border p-6 space-y-2">
          {faltanPreguntas.length > 0 && (
            <p className="text-sm text-ink/60">Faltan {faltanPreguntas.length} pregunta(s) por responder.</p>
          )}
          <TextoError>{errorFinalizar}</TextoError>
          <Boton
            onClick={finalizar}
            disabled={finalizando || faltanPreguntas.length > 0 || guardandoPreguntaIds.size > 0}
          >
            {finalizando
              ? "Finalizando..."
              : guardandoPreguntaIds.size > 0
                ? "Guardando respuestas..."
                : "Finalizar evaluación"}
          </Boton>
        </div>
      </div>
    );
  }

  // fase === "finalizado"
  return (
    <div className="bg-white rounded-card border border-border p-8 space-y-4">
      <h1 className="font-display text-xl text-teal-900">Evaluación finalizada</h1>
      <p className="text-sm text-ink/70">{estadoResultados?.mensaje ?? "Gracias por completar la evaluación."}</p>

      {diagnosticos && diagnosticos.length > 0 && (
        <ul className="text-sm text-ink/80 list-disc list-inside">
          {diagnosticos.map((d) => (
            <li key={d.id}>Nivel: {d.nivel}</li>
          ))}
        </ul>
      )}

      {estadoResultados?.informe_liberado && (
        <Boton onClick={descargarInforme} disabled={descargando}>
          {descargando ? "Descargando..." : "Descargar mi informe (PDF)"}
        </Boton>
      )}
    </div>
  );
}
