"use client";

import { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { ArrowLeft, ArrowRight, CheckCircle2, Download, ListChecks } from "lucide-react";
import { apiClient, ApiError, descargarBlob, estadoHttpDe, mensajeDe } from "@/lib/api-client";
import { Boton } from "@/components/ui/Boton";
import { TextoError } from "@/components/ui/TextoError";
import type {
  RegistroAlumnoDemograficos,
  IntakeExamen,
  AsentimientoInformadoTextoPublico,
  CampoSociodemografico,
  PreguntaExamen,
  ProgresoExamen,
  EstadoResultadosAlumno,
} from "@/types/api";

// Botones del examen SIN variantes `dark:` — el examen es siempre claro
// (ver su layout), y <Boton> se oscurecería si quien abre el link tiene el
// tema oscuro guardado en ese navegador.
const BOTON_PRIMARIO =
  "inline-flex min-h-12 items-center justify-center gap-2 rounded-xl bg-accion px-5 text-base font-semibold text-white shadow-sm transition-colors hover:bg-accion-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-400 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-40";
const BOTON_SECUNDARIO =
  "inline-flex min-h-12 items-center justify-center gap-2 rounded-xl border border-border bg-white px-4 text-base font-medium text-ink transition-colors hover:bg-mist focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-400 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-40";

// Flujo público, sin sesión: 1) datos sociodemográficos + asentimiento
// (comenzar-test, también reanuda un examen "En Progreso") — primero se
// consulta /intake para no volver a pedir lo que el colegio ya cargó al
// matricular por padrón, 2) campos sociodemográficos propios de la
// institución (si tiene alguno configurado — la mayoría no), 3) preguntas
// con autoguardado por respuesta (resumible: progreso ya contestado se
// precarga), 4) finalizar.
//
// 🆕 Rediseño del examen (sesión 2026-11-01, decisiones del usuario):
// - las instrucciones de la prueba (Prueba.instrucciones, vía /intake) se
//   muestran TEXTUALES antes de la primera pregunta — antes no se mostraban;
// - UNA pregunta por pantalla, con Anterior/Siguiente, barra de progreso y
//   un mapa de preguntas para saltar a cualquiera (antes: todas en una sola
//   página larga — 47 tarjetas seguidas en RCADS-47);
// - opciones como tarjetas grandes tocables (antes: el radio nativo);
// - antes de finalizar, una pantalla de revisión que lista las preguntas
//   sin responder y deja ir a cada una (antes: "Faltan N" sin decir cuáles,
//   y un window.confirm);
// - al terminar, agradecimiento; el resumen por dimensión y el PDF solo si
//   la campaña tiene encendido "los estudiantes ven su resultado"
//   (Evaluacion.alumno_ve_informe, apagado por defecto — ver irAFinalizado).
//   Apagado, el mensaje es el mismo haya o no alerta.
// El autoguardado por respuesta (cola por pregunta, reintento, rollback) no
// cambió.
type Fase = "intake" | "socio" | "preguntas" | "finalizado" | "error_terminal";
// Dentro de la fase "preguntas".
type VistaPreguntas = "instrucciones" | "pregunta" | "revision";

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
      .catch((err: unknown) =>
        setErrorAsentimientoTexto(
          mensajeDe(err) || "No se pudo cargar el texto de asentimiento informado. Contacta a tu colegio."
        )
      );
  }, [token]);

  // --- Fase 4: finalizado ---
  // 🆕 Solo se usa si la campaña deja que el alumno vea su resultado
  // (alumno_puede_ver_informe) — si no, la pantalla final es solo un
  // agradecimiento. Declarado aquí porque el efecto de /intake (abajo) lo
  // usa cuando el enlace ya está finalizado.
  const [estadoResultados, setEstadoResultados] = useState<EstadoResultadosAlumno | null>(null);

  // 🆕 Antes de mostrar el formulario, averiguamos qué datos ya tiene esta
  // inscripción (nombre/edad/nivel, cuando viene de una matrícula por
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
          poblacion: (datos.poblacion as RegistroAlumnoDemograficos["poblacion"]) ?? prev.poblacion,
        }));
      })
      .catch((err: unknown) => {
        // 🆕 (sesión 2026-11-02) El backend ya avisa aquí si la evaluación
        // terminó (409) o el enlace venció (410). Antes se ignoraba y un
        // alumno que volvía a abrir su enlace después de terminar veía otra
        // vez "Antes de comenzar": recién al reenviar el formulario llegaba
        // al agradecimiento (y a su resultado, si la campaña lo permite).
        const estado = estadoHttpDe(err);
        if (estado === 409) {
          // Lo mismo que irAFinalizado() (más abajo), escrito aquí para no
          // depender de una función declarada después del efecto.
          apiClient
            .get<EstadoResultadosAlumno>(`/educativo/examen/${token}/estado-resultados`)
            .then(setEstadoResultados)
            .catch(() => setEstadoResultados(null))
            .finally(() => setFase("finalizado"));
        } else if (estado === 410) {
          setFase("error_terminal");
          setErrorTerminal(mensajeDe(err));
        }
        // Cualquier otro fallo: silencioso a propósito, el formulario se ve
        // como siempre (todo editable) y comenzar-test informará el error real.
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

  // 🆕 Una pregunta por pantalla: cuál se ve y qué vista de la fase.
  const [indiceActual, setIndiceActual] = useState(0);
  const [vista, setVista] = useState<VistaPreguntas>("pregunta");
  const refTituloVista = useRef<HTMLHeadingElement>(null);

  // --- Fase 4: finalizado --- (estadoResultados se declara más arriba,
  // antes del efecto de /intake, que también lo usa)
  const [descargando, setDescargando] = useState(false);
  const [errorDescarga, setErrorDescarga] = useState<string | null>(null);

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
    } catch (err) {
      if (estadoHttpDe(err) === 409) {
        // Ya estaba Finalizado -- no es un error, vamos directo al estado.
        await irAFinalizado();
      } else if (estadoHttpDe(err) === 410) {
        setFase("error_terminal");
        setErrorTerminal(mensajeDe(err));
      } else {
        setErrorIntake(mensajeDe(err) || "No se pudo comenzar la evaluación.");
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
    } catch (err) {
      setErrorSocio(mensajeDe(err) || "No se pudieron guardar tus datos.");
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
      // Al reanudar, se sigue en la primera pregunta sin responder (o en la
      // revisión si ya estaban todas). Las instrucciones se muestran
      // primero siempre que la prueba las tenga, también al reanudar.
      const primeraSinResponder = listaPreguntas.findIndex((p) => previas[p.id] === undefined);
      const todasRespondidas = primeraSinResponder === -1 && listaPreguntas.length > 0;
      setIndiceActual(primeraSinResponder === -1 ? Math.max(0, listaPreguntas.length - 1) : primeraSinResponder);
      setVista(intakePrevio?.instrucciones ? "instrucciones" : todasRespondidas ? "revision" : "pregunta");
      setFase("preguntas");
    } catch (err) {
      setErrorPreguntas(mensajeDe(err) || "No se pudieron cargar las preguntas.");
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
    } catch (err) {
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
        setErrorGuardar(mensajeDe(err) || "No se pudo guardar esta respuesta. Vuelve a intentarlo.");
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

  // 🆕 Navegación de una pregunta por pantalla. Sube al inicio y lleva el
  // foco al título de la vista nueva (lectores de pantalla y teclado).
  function irAPregunta(indice: number) {
    setIndiceActual(Math.min(Math.max(0, indice), Math.max(0, preguntas.length - 1)));
    setVista("pregunta");
    window.scrollTo({ top: 0 });
  }
  function irARevision() {
    setVista("revision");
    window.scrollTo({ top: 0 });
  }
  const primeraVistaRef = useRef(true);
  useEffect(() => {
    if (fase !== "preguntas") return;
    // La primera vista no roba el foco (el alumno recién llega); las
    // siguientes sí, para que el lector de pantalla lea la pregunta nueva.
    if (primeraVistaRef.current) {
      primeraVistaRef.current = false;
      return;
    }
    refTituloVista.current?.focus();
  }, [fase, vista, indiceActual]);

  // La pantalla de revisión hace de confirmación (antes, window.confirm).
  async function finalizar() {
    if (faltanPreguntas.length > 0 || guardandoPreguntaIds.size > 0) return;
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
          "Alguna respuesta no se pudo guardar. Vuelve a responder las preguntas que aparecen sin responder."
        );
        return;
      }
      // La respuesta (diagnósticos) se ignora a propósito: el alumno no ve
      // niveles — ver el comentario al inicio del archivo.
      await apiClient.post(`/educativo/examen/${token}/finalizar`);
      await irAFinalizado();
    } catch (err) {
      setErrorFinalizar(mensajeDe(err) || "No se pudo finalizar la evaluación.");
    } finally {
      setFinalizando(false);
    }
  }

  // 🆕 Lo que ve el alumno al terminar lo decide el interruptor de la
  // campaña (Evaluacion.alumno_ve_informe), leído de /estado-resultados:
  // apagado (por defecto) solo agradecimiento; encendido, resumen por
  // dimensión + PDF, haya o no alerta. Si la consulta falla, solo
  // agradecimiento.
  async function irAFinalizado() {
    try {
      setEstadoResultados(await apiClient.get<EstadoResultadosAlumno>(`/educativo/examen/${token}/estado-resultados`));
    } catch {
      setEstadoResultados(null);
    }
    setFase("finalizado");
  }

  async function descargarInforme() {
    setDescargando(true);
    setErrorDescarga(null);
    try {
      const blob = await apiClient.descargarArchivo(`/educativo/examen/${token}/informe-pdf`);
      descargarBlob(blob, "mi_informe.pdf");
    } catch (err: unknown) {
      setErrorDescarga(err instanceof Error && err.message ? err.message : "No se pudo descargar tu informe.");
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
    const poblacionConocida = intakePrevio?.poblacion != null;

    return (
      <form onSubmit={enviarIntake} className="bg-white rounded-card border border-border p-8 space-y-4">
        {/* 🆕 (sesión 2026-11-02) De qué colegio es esta evaluación: antes el
            alumno no veía ninguna marca de su institución. */}
        {(intakePrevio?.institucion_logo_url || intakePrevio?.institucion_nombre) && (
          <div className="flex items-center gap-3 border-b border-border pb-4">
            {intakePrevio.institucion_logo_url && (
              // eslint-disable-next-line @next/next/no-img-element -- URL externa del colegio (validada al guardarla), igual que el menú lateral
              <img src={intakePrevio.institucion_logo_url} alt="" className="h-12 w-12 shrink-0 rounded-lg object-contain" />
            )}
            {intakePrevio.institucion_nombre && (
              <p className="m-0 text-sm font-semibold text-teal-900">{intakePrevio.institucion_nombre}</p>
            )}
          </div>
        )}
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

        {/* 🆕 (sesión 2026-11-02) Sin campo Sexo: el alumno no lo ve (decisión
            del usuario). Sale del padrón al matricular; ver RegistroAlumnoDemograficos. */}
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
              <option value="Inicial">Inicial</option>
              <option value="Primaria">Primaria</option>
              <option value="Secundaria">Secundaria</option>
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
    const total = preguntas.length;
    const respondidas = total - faltanPreguntas.length;
    const actual = preguntas[indiceActual];
    const esUltima = indiceActual >= total - 1;
    const indicePorId = new Map(preguntas.map((p, i) => [p.id, i]));
    const guardandoActual = actual ? guardandoPreguntaIds.has(actual.id) : false;

    return (
      <div className="space-y-4">
        {/* Encabezado: progreso siempre visible. */}
        <div className="bg-white rounded-card border border-border p-5 sm:p-6">
          <div className="flex items-baseline justify-between gap-3">
            <h1 className="font-display text-xl text-teal-900">Evaluación</h1>
            <p className="text-sm text-ink/60">
              {respondidas} de {total} respondidas
            </p>
          </div>
          <div
            role="progressbar"
            aria-label="Preguntas respondidas"
            aria-valuemin={0}
            aria-valuemax={total}
            aria-valuenow={respondidas}
            className="mt-3 h-2.5 w-full overflow-hidden rounded-full bg-mist"
          >
            <div
              className="h-full rounded-full bg-teal-600 transition-[width] duration-300"
              style={{ width: `${total ? (respondidas / total) * 100 : 0}%` }}
            />
          </div>
          <p className="mt-2 text-xs text-ink/50">Tus respuestas se guardan automáticamente.</p>
        </div>

        <TextoError>{errorPreguntas}</TextoError>
        <TextoError>{errorGuardar}</TextoError>

        {/* ===== Instrucciones (textuales, tal como están cargadas) ===== */}
        {vista === "instrucciones" && (
          <section className="bg-white rounded-card border border-border p-6 sm:p-8 space-y-5">
            <h2 ref={refTituloVista} tabIndex={-1} className="font-display text-lg text-teal-900 focus:outline-none">
              Instrucciones
            </h2>
            <p className="whitespace-pre-line text-base leading-relaxed text-ink/85">{intakePrevio?.instrucciones}</p>
            <button
              type="button"
              // Al reanudar con todo ya respondido, directo a la revisión.
              onClick={() => (total > 0 && faltanPreguntas.length === 0 ? irARevision() : irAPregunta(indiceActual))}
              className={`${BOTON_PRIMARIO} w-full sm:w-auto`}
            >
              {respondidas > 0 ? "Continuar con las preguntas" : "Comenzar las preguntas"}
              <ArrowRight className="h-4 w-4" aria-hidden />
            </button>
          </section>
        )}

        {/* ===== Una pregunta por pantalla ===== */}
        {vista === "pregunta" && actual && (
          <section className="bg-white rounded-card border border-border p-5 sm:p-7">
            <div className="flex items-center justify-between gap-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-teal-700">
                Pregunta {indiceActual + 1} de {total}
              </p>
              <span aria-live="polite" className="text-xs text-ink/45">
                {guardandoActual ? "Guardando…" : respuestas[actual.id] !== undefined ? "Guardada" : ""}
              </span>
            </div>
            <h2
              id={`pregunta-${actual.id}-texto`}
              ref={refTituloVista}
              tabIndex={-1}
              className="mt-2 text-lg sm:text-xl font-medium leading-snug text-ink focus:outline-none"
            >
              {actual.texto_pregunta}
            </h2>

            {actual.tipo_respuesta === "numerico" ? (
              <div role="group" aria-labelledby={`pregunta-${actual.id}-texto`} className="mt-5 flex flex-wrap items-center gap-3">
                {Array.from({ length: actual.cantidad_valores_numericos ?? 0 }).map((_, idx) => (
                  <input
                    key={idx}
                    type="number"
                    inputMode="numeric"
                    aria-label={`Valor ${idx + 1} de ${actual.cantidad_valores_numericos}`}
                    value={borradorNumerico[actual.id]?.[idx] ?? ""}
                    onChange={(e) =>
                      actualizarValorNumerico(actual.id, idx, actual.cantidad_valores_numericos ?? 0, e.target.value)
                    }
                    className="h-14 w-24 rounded-xl border-2 border-border px-3 text-center text-lg focus:border-teal-600 focus:outline-none focus:ring-2 focus:ring-teal-400/40"
                  />
                ))}
              </div>
            ) : (
              <div role="radiogroup" aria-labelledby={`pregunta-${actual.id}-texto`} className="mt-5 space-y-2.5">
                {actual.opciones.map((o) => {
                  const marcada = respuestas[actual.id] === o.id;
                  return (
                    <label
                      key={o.id}
                      className={`flex min-h-13 cursor-pointer items-center gap-3 rounded-xl border-2 px-4 py-3 text-base transition-colors focus-within:ring-2 focus-within:ring-teal-400 focus-within:ring-offset-1 ${
                        marcada
                          ? "border-teal-600 bg-teal-50 font-medium text-teal-900"
                          : "border-border bg-white text-ink hover:border-ink/25 hover:bg-mist/60"
                      }`}
                    >
                      <input
                        type="radio"
                        name={`pregunta-${actual.id}`}
                        checked={marcada}
                        onChange={() => elegirOpcion(actual.id, o.id)}
                        className="h-5 w-5 shrink-0 accent-teal-600"
                      />
                      <span>{o.texto_opcion}</span>
                    </label>
                  );
                })}
              </div>
            )}

            <div className="mt-7 flex items-center justify-between gap-3">
              <button
                type="button"
                onClick={() => irAPregunta(indiceActual - 1)}
                disabled={indiceActual === 0}
                className={BOTON_SECUNDARIO}
              >
                <ArrowLeft className="h-4 w-4" aria-hidden />
                Anterior
              </button>
              {esUltima ? (
                <button type="button" onClick={irARevision} className={BOTON_PRIMARIO}>
                  Revisar y finalizar
                  <ListChecks className="h-4 w-4" aria-hidden />
                </button>
              ) : (
                <button type="button" onClick={() => irAPregunta(indiceActual + 1)} className={BOTON_PRIMARIO}>
                  Siguiente
                  <ArrowRight className="h-4 w-4" aria-hidden />
                </button>
              )}
            </div>
          </section>
        )}

        {/* ===== Revisión final (hace de confirmación) ===== */}
        {vista === "revision" && (
          <section className="bg-white rounded-card border border-border p-6 sm:p-8 space-y-5">
            <h2 ref={refTituloVista} tabIndex={-1} className="font-display text-lg text-teal-900 focus:outline-none">
              Revisión final
            </h2>
            {faltanPreguntas.length > 0 ? (
              <div className="space-y-3">
                <p className="text-base text-ink/85">
                  {faltanPreguntas.length === 1
                    ? "Te falta responder 1 pregunta. Tócala para ir a ella:"
                    : `Te faltan responder ${faltanPreguntas.length} preguntas. Toca una para ir a ella:`}
                </p>
                <div className="flex flex-wrap gap-2">
                  {faltanPreguntas.map((p) => {
                    const i = indicePorId.get(p.id) ?? 0;
                    return (
                      <button
                        key={p.id}
                        type="button"
                        onClick={() => irAPregunta(i)}
                        className="min-h-11 rounded-xl border-2 border-dashed border-teal-600/60 bg-white px-4 text-sm font-semibold text-teal-800 transition-colors hover:bg-teal-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-400"
                      >
                        Pregunta {i + 1}
                      </button>
                    );
                  })}
                </div>
              </div>
            ) : (
              <p className="text-base text-ink/85">
                Respondiste las {total} preguntas. Cuando finalices ya no podrás cambiar tus respuestas.
              </p>
            )}
            <TextoError>{errorFinalizar}</TextoError>
            <div className="flex flex-col-reverse gap-3 sm:flex-row sm:items-center sm:justify-between">
              <button type="button" onClick={() => irAPregunta(indiceActual)} className={BOTON_SECUNDARIO}>
                <ArrowLeft className="h-4 w-4" aria-hidden />
                Volver a las preguntas
              </button>
              <button
                type="button"
                onClick={finalizar}
                disabled={finalizando || faltanPreguntas.length > 0 || guardandoPreguntaIds.size > 0}
                className={BOTON_PRIMARIO}
              >
                {finalizando
                  ? "Finalizando..."
                  : guardandoPreguntaIds.size > 0
                    ? "Guardando respuestas..."
                    : "Finalizar evaluación"}
              </button>
            </div>
          </section>
        )}

        {/* Mapa de preguntas: saltar a cualquiera (respondida = llena). */}
        {vista !== "instrucciones" && total > 1 && (
          <details className="bg-white rounded-card border border-border p-4 sm:p-5">
            <summary className="cursor-pointer text-sm font-medium text-ink/75">Ver todas las preguntas</summary>
            <div className="mt-3 flex flex-wrap gap-1.5">
              {preguntas.map((p, i) => {
                const respondida = respuestas[p.id] !== undefined;
                const esActual = vista === "pregunta" && i === indiceActual;
                return (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => irAPregunta(i)}
                    aria-label={`Pregunta ${i + 1}${respondida ? ", respondida" : ", sin responder"}`}
                    aria-current={esActual ? "step" : undefined}
                    className={`h-10 w-10 rounded-lg text-sm font-semibold transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-400 ${
                      respondida ? "bg-teal-600 text-white hover:bg-teal-900" : "border border-border bg-white text-ink/70 hover:bg-mist"
                    } ${esActual ? "ring-2 ring-teal-900 ring-offset-2" : ""}`}
                  >
                    {i + 1}
                  </button>
                );
              })}
            </div>
          </details>
        )}
      </div>
    );
  }

  // fase === "finalizado" — agradecimiento siempre; resumen + PDF solo si
  // la campaña lo permite (ver irAFinalizado). Apagado, el mensaje es el
  // mismo haya o no alerta.
  const puedeVer = !!estadoResultados?.alumno_puede_ver_informe;
  return (
    <div className="space-y-4">
      <div className="bg-white rounded-card border border-border p-8 sm:p-10 text-center space-y-3">
        <CheckCircle2 className="mx-auto h-12 w-12 text-teal-600" aria-hidden />
        <h1 className="font-display text-xl text-teal-900">Evaluación finalizada</h1>
        <p className="text-base text-ink/80">Gracias por completar la evaluación. Tus respuestas quedaron registradas.</p>
        <p className="text-sm text-ink/60">Si tienes alguna duda, acércate al equipo de orientación de tu institución.</p>
      </div>

      {puedeVer && (
        <section className="bg-white rounded-card border border-border p-6 sm:p-8 space-y-4">
          <h2 className="font-display text-lg text-teal-900">Tus resultados</h2>
          {estadoResultados && estadoResultados.resultados.length > 0 && (
            <ul className="divide-y divide-border rounded-xl border border-border">
              {estadoResultados.resultados.map((r, i) => (
                <li key={`${r.dimension}-${i}`} className="flex items-baseline justify-between gap-4 px-4 py-3">
                  <span className="text-sm text-ink/75">{r.dimension}</span>
                  <span className="text-right text-sm font-semibold text-ink">{r.nivel}</span>
                </li>
              ))}
            </ul>
          )}
          <TextoError>{errorDescarga}</TextoError>
          <button type="button" onClick={descargarInforme} disabled={descargando} className={`${BOTON_PRIMARIO} w-full sm:w-auto`}>
            <Download className="h-4 w-4" aria-hidden />
            {descargando ? "Descargando..." : "Descargar mi informe (PDF)"}
          </button>
        </section>
      )}
    </div>
  );
}
