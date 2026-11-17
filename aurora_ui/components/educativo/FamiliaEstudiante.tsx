"use client";

import type { FormEvent } from "react";
import { Baby, Briefcase, GraduationCap, HeartHandshake, Home, MapPin, Phone, Plus, ShieldCheck, UsersRound } from "lucide-react";
import { Boton } from "@/components/ui/Boton";
import { CampoEditable } from "@/components/ui/CampoEditable";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { TextoError } from "@/components/ui/TextoError";
import { VacioFicha } from "@/components/educativo/BloqueFicha";
import type { ContactoFamiliar, ContactoFamiliarCreate } from "@/types/api";

// 🆕 (2026-11-16) Registro único por familiar. Un familiar (padre, madre,
// hermano, apoderado...) se escribe UNA vez y aparece en "Composición
// familiar" y, si es contacto, en "Contactos familiares" — ver
// models.ContactoFamiliar en el backend. Aquí viven el formulario (el mismo
// desde los dos bloques) y las tarjetas de la composición familiar.

export const PARENTESCOS = ["Padre", "Madre", "Hermano", "Hermana", "Abuelo", "Abuela", "Tío", "Tía", "Tutor legal", "Otro"];
export const GRADOS_INSTRUCCION = [
  "Sin estudios",
  "Primaria incompleta",
  "Primaria completa",
  "Secundaria incompleta",
  "Secundaria completa",
  "Técnico incompleto",
  "Técnico completo",
  "Superior universitario incompleto",
  "Superior universitario completo",
  "Posgrado",
];
export const ESTADOS_CIVILES = ["Soltero(a)", "Casado(a)", "Conviviente", "Separado(a)", "Divorciado(a)", "Viudo(a)"];

export type FormFamiliar = {
  id: number | null; // null = nuevo
  origen: "familia" | "contactos"; // en qué bloque se abrió el formulario
  nombre: string;
  apellidos: string;
  relacion: string;
  es_apoderado: boolean;
  es_contacto: boolean;
  vive_con_estudiante: "" | "si" | "no";
  telefono: string;
  email: string;
  ocupacion: string;
  grado_instruccion: string;
  estado_civil: string;
  direccion: string;
  distrito: string;
  fecha_nacimiento: string;
};

const esPadreOMadre = (relacion: string) => /^(padre|madre)\b/i.test(relacion.trim());
const esHermano = (relacion: string) => /^herman/i.test(relacion.trim());

export function formFamiliarNuevo(origen: FormFamiliar["origen"], relacion = "", esApoderado = false): FormFamiliar {
  return {
    id: null,
    origen,
    nombre: "",
    apellidos: "",
    relacion,
    es_apoderado: esApoderado,
    // Un hermano casi nunca es a quién llamar; padres y apoderados sí.
    es_contacto: origen === "contactos" || !esHermano(relacion),
    vive_con_estudiante: "",
    telefono: "",
    email: "",
    ocupacion: "",
    grado_instruccion: "",
    estado_civil: "",
    direccion: "",
    distrito: "",
    fecha_nacimiento: "",
  };
}

export function formFamiliarDe(c: ContactoFamiliar, origen: FormFamiliar["origen"]): FormFamiliar {
  return {
    id: c.id,
    origen,
    nombre: c.nombre,
    apellidos: c.apellidos ?? "",
    relacion: c.relacion ?? "",
    es_apoderado: c.es_apoderado,
    es_contacto: c.es_contacto,
    vive_con_estudiante: c.vive_con_estudiante === null ? "" : c.vive_con_estudiante ? "si" : "no",
    telefono: c.telefono ?? "",
    email: c.email ?? "",
    ocupacion: c.ocupacion ?? "",
    grado_instruccion: c.grado_instruccion ?? "",
    estado_civil: c.estado_civil ?? "",
    direccion: c.direccion ?? "",
    distrito: c.distrito ?? "",
    fecha_nacimiento: c.fecha_nacimiento ?? "",
  };
}

// Mismo cuerpo para crear (POST) y editar (PATCH): un campo vaciado se envía
// como null para que de verdad se borre.
export function payloadFamiliar(f: FormFamiliar): ContactoFamiliarCreate {
  const texto = (v: string) => v.trim() || null;
  return {
    nombre: f.nombre.trim(),
    apellidos: texto(f.apellidos),
    relacion: texto(f.relacion),
    es_apoderado: f.es_apoderado,
    es_contacto: f.es_contacto,
    vive_con_estudiante: f.vive_con_estudiante === "" ? null : f.vive_con_estudiante === "si",
    telefono: texto(f.telefono),
    email: texto(f.email),
    ocupacion: texto(f.ocupacion),
    grado_instruccion: texto(f.grado_instruccion),
    estado_civil: texto(f.estado_civil),
    direccion: texto(f.direccion),
    distrito: texto(f.distrito),
    fecha_nacimiento: f.fecha_nacimiento || null,
  };
}

export function nombreFamiliar(c: Pick<ContactoFamiliar, "nombre" | "apellidos">): string {
  return [c.nombre, c.apellidos].filter(Boolean).join(" ");
}

export function edadDesde(fecha: string | null): number | null {
  if (!fecha) return null;
  const [a, m, d] = fecha.split("-").map(Number);
  if (!a || !m || !d) return null;
  const hoy = new Date();
  const edad = hoy.getFullYear() - a - (hoy.getMonth() + 1 < m || (hoy.getMonth() + 1 === m && hoy.getDate() < d) ? 1 : 0);
  return edad >= 0 ? edad : null;
}

export function FormularioFamiliar({
  valor,
  onCambio,
  onGuardar,
  onCancelar,
  guardando,
  error,
}: {
  valor: FormFamiliar;
  onCambio: (v: FormFamiliar) => void;
  onGuardar: (e: FormEvent) => void;
  onCancelar: () => void;
  guardando: boolean;
  error: string | null;
}) {
  const set = <K extends keyof FormFamiliar>(campo: K, v: FormFamiliar[K]) => onCambio({ ...valor, [campo]: v });
  const padreOMadre = esPadreOMadre(valor.relacion);
  // Estado civil: pensado para los padres (o un apoderado), pero si ya tiene
  // un valor se muestra siempre para poder corregirlo.
  const verEstadoCivil = padreOMadre || valor.es_apoderado || !!valor.estado_civil;
  // Fecha de nacimiento: pensada para hermanos; en los padres no se pide.
  const verFechaNacimiento = !padreOMadre || !!valor.fecha_nacimiento;

  return (
    <form
      onSubmit={onGuardar}
      className="grid sm:grid-cols-2 gap-4 text-sm border-b border-border dark:border-border-dark pb-4 mb-4"
      aria-label={valor.id === null ? "Agregar familiar" : "Editar familiar"}
    >
      <CampoEditable etiqueta="Parentesco">
        <Input
          list="parentescos-familiar"
          placeholder="Padre, madre, hermana, tutor legal..."
          value={valor.relacion}
          onChange={(e) => set("relacion", e.target.value)}
        />
        <datalist id="parentescos-familiar">
          {PARENTESCOS.map((p) => (
            <option key={p} value={p} />
          ))}
        </datalist>
      </CampoEditable>
      <CampoEditable etiqueta="¿Vive con el estudiante?">
        <Select
          value={valor.vive_con_estudiante}
          onChange={(e) => set("vive_con_estudiante", e.target.value as FormFamiliar["vive_con_estudiante"])}
        >
          <option value="">Sin dato</option>
          <option value="si">Sí</option>
          <option value="no">No</option>
        </Select>
      </CampoEditable>
      <CampoEditable etiqueta="Nombres (obligatorio)">
        <Input required value={valor.nombre} onChange={(e) => set("nombre", e.target.value)} />
      </CampoEditable>
      <CampoEditable etiqueta="Apellidos">
        <Input value={valor.apellidos} onChange={(e) => set("apellidos", e.target.value)} />
      </CampoEditable>

      <div className="sm:col-span-2 flex flex-wrap gap-x-6 gap-y-2 rounded-lg border border-border dark:border-border-dark bg-surface/60 dark:bg-surface-dark/40 px-3.5 py-2.5">
        <label className="inline-flex items-center gap-2 font-medium text-ink/80 dark:text-ink-dark/80">
          <input
            type="checkbox"
            className="h-4 w-4 accent-teal-600"
            checked={valor.es_apoderado}
            onChange={(e) => set("es_apoderado", e.target.checked)}
          />
          Es el apoderado
        </label>
        <label className="inline-flex items-center gap-2 font-medium text-ink/80 dark:text-ink-dark/80">
          <input
            type="checkbox"
            className="h-4 w-4 accent-teal-600"
            checked={valor.es_contacto}
            onChange={(e) => set("es_contacto", e.target.checked)}
          />
          Mostrar en contactos (a quién llamar)
        </label>
      </div>

      <CampoEditable etiqueta="Teléfono">
        <Input type="tel" value={valor.telefono} onChange={(e) => set("telefono", e.target.value)} />
      </CampoEditable>
      <CampoEditable etiqueta="Correo">
        <Input type="email" value={valor.email} onChange={(e) => set("email", e.target.value)} />
      </CampoEditable>
      <CampoEditable etiqueta="Ocupación">
        <Input
          placeholder="Docente, comerciante, ama de casa, estudiante..."
          value={valor.ocupacion}
          onChange={(e) => set("ocupacion", e.target.value)}
        />
      </CampoEditable>
      <CampoEditable etiqueta="Grado de instrucción">
        <Input list="grados-instruccion-familiar" value={valor.grado_instruccion} onChange={(e) => set("grado_instruccion", e.target.value)} />
        <datalist id="grados-instruccion-familiar">
          {GRADOS_INSTRUCCION.map((g) => (
            <option key={g} value={g} />
          ))}
        </datalist>
      </CampoEditable>
      {verEstadoCivil && (
        <CampoEditable etiqueta="Estado civil">
          <Select value={valor.estado_civil} onChange={(e) => set("estado_civil", e.target.value)}>
            <option value="">Sin dato</option>
            {/* Un valor antiguo fuera de la lista no se pierde al editar. */}
            {[...ESTADOS_CIVILES, ...(valor.estado_civil && !ESTADOS_CIVILES.includes(valor.estado_civil) ? [valor.estado_civil] : [])].map((e) => (
              <option key={e} value={e}>
                {e}
              </option>
            ))}
          </Select>
        </CampoEditable>
      )}
      {verFechaNacimiento && (
        <CampoEditable etiqueta="Fecha de nacimiento">
          <Input type="date" value={valor.fecha_nacimiento} onChange={(e) => set("fecha_nacimiento", e.target.value)} />
        </CampoEditable>
      )}
      <CampoEditable etiqueta="Dirección (dónde vive)">
        <Input
          placeholder={valor.vive_con_estudiante === "si" ? "La misma del estudiante, o escríbela" : "Av., calle, número..."}
          value={valor.direccion}
          onChange={(e) => set("direccion", e.target.value)}
        />
      </CampoEditable>
      <CampoEditable etiqueta="Distrito">
        <Input value={valor.distrito} onChange={(e) => set("distrito", e.target.value)} />
      </CampoEditable>

      <TextoError className="sm:col-span-2">{error}</TextoError>

      <div className="sm:col-span-2 flex items-center gap-3 pt-1">
        <Boton type="submit" disabled={guardando}>
          {guardando ? "Guardando..." : valor.id === null ? "Agregar familiar" : "Guardar cambios"}
        </Boton>
        <button type="button" onClick={onCancelar} className="text-sm text-ink/60 dark:text-ink-dark/60 hover:underline">
          Cancelar
        </button>
      </div>
    </form>
  );
}

// Orden en pantalla: padres, apoderados, hermanos y el resto (igual que el PDF).
function ordenFamiliar(c: ContactoFamiliar): number {
  const r = (c.relacion ?? "").trim().toLowerCase();
  if (r.startsWith("padre") || r.startsWith("madre")) return 0;
  if (c.es_apoderado) return 1;
  if (r.startsWith("herman")) return 2;
  return 3;
}

export const ATAJOS_FAMILIAR: { etiqueta: string; relacion: string; apoderado?: boolean }[] = [
  { etiqueta: "Padre", relacion: "Padre" },
  { etiqueta: "Madre", relacion: "Madre" },
  { etiqueta: "Hermano/a", relacion: "Hermano" },
  { etiqueta: "Apoderado", relacion: "", apoderado: true },
  { etiqueta: "Otro", relacion: "" },
];

export function ComposicionFamiliar({
  familiares,
  puedeEditar,
  onAgregar,
  onEditar,
}: {
  familiares: ContactoFamiliar[];
  puedeEditar: boolean;
  onAgregar: (relacion: string, apoderado: boolean) => void;
  onEditar: (c: ContactoFamiliar) => void;
}) {
  const activos = familiares.filter((c) => c.activo).sort((a, b) => ordenFamiliar(a) - ordenFamiliar(b));
  const hermanos = activos.filter((c) => /^herman/i.test((c.relacion ?? "").trim())).length;

  return (
    <div className="space-y-3">
      {activos.length === 0 ? (
        <VacioFicha icono={UsersRound} texto="Aún no hay familiares registrados." />
      ) : (
        <ul className="m-0 grid list-none gap-3 p-0 sm:grid-cols-2 xl:grid-cols-3">
          {activos.map((c) => {
            const edad = edadDesde(c.fecha_nacimiento);
            const detalles = [
              c.ocupacion && { icono: Briefcase, texto: c.ocupacion },
              c.grado_instruccion && { icono: GraduationCap, texto: c.grado_instruccion },
              c.estado_civil && { icono: HeartHandshake, texto: c.estado_civil },
              edad !== null && { icono: Baby, texto: `${edad} ${edad === 1 ? "año" : "años"}` },
              (c.direccion || c.distrito) && { icono: MapPin, texto: [c.direccion, c.distrito].filter(Boolean).join(", ") },
              c.telefono && { icono: Phone, texto: c.telefono },
            ].filter(Boolean) as { icono: typeof Briefcase; texto: string }[];
            return (
              <li
                key={c.id}
                className="flex flex-col rounded-lg border border-border dark:border-border-dark bg-surface dark:bg-surface-dark px-3.5 py-3"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="m-0 text-[11.5px] font-semibold uppercase tracking-wide text-teal-700 dark:text-teal-accent-dark">
                      {c.relacion || "Familiar"}
                    </p>
                    <p className="m-0 mt-0.5 font-semibold text-ink dark:text-ink-dark break-words">{nombreFamiliar(c)}</p>
                  </div>
                  {puedeEditar && (
                    <button
                      type="button"
                      onClick={() => onEditar(c)}
                      className="shrink-0 text-xs font-medium text-teal-600 hover:underline dark:text-teal-accent-dark"
                      aria-label={`Editar a ${nombreFamiliar(c)}`}
                    >
                      Editar
                    </button>
                  )}
                </div>
                {(c.es_apoderado || c.vive_con_estudiante !== null) && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {c.es_apoderado && (
                      <span className="inline-flex items-center gap-1 rounded-full bg-teal-600/10 px-2 py-0.5 text-[11.5px] font-semibold text-teal-800 dark:bg-teal-accent-dark/15 dark:text-teal-accent-dark">
                        <ShieldCheck size={11} aria-hidden="true" /> Apoderado
                      </span>
                    )}
                    {c.vive_con_estudiante !== null && (
                      <span className="inline-flex items-center gap-1 rounded-full bg-ink/[0.06] px-2 py-0.5 text-[11.5px] font-medium text-ink/70 dark:bg-white/10 dark:text-ink-dark/70">
                        <Home size={11} aria-hidden="true" /> {c.vive_con_estudiante ? "Vive con el estudiante" : "No vive con el estudiante"}
                      </span>
                    )}
                  </div>
                )}
                {detalles.length > 0 && (
                  <ul className="m-0 mt-2.5 list-none space-y-1 p-0 text-[13px] text-ink/70 dark:text-ink-dark/70">
                    {detalles.map(({ icono: Icono, texto }) => (
                      <li key={texto} className="flex items-start gap-1.5">
                        <Icono size={13} className="mt-0.5 shrink-0 text-ink/35 dark:text-ink-dark/35" aria-hidden="true" />
                        <span className="break-words">{texto}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {puedeEditar && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[12.5px] font-medium text-ink/55 dark:text-ink-dark/55">Agregar:</span>
          {ATAJOS_FAMILIAR.map((a) => (
            <button
              key={a.etiqueta}
              type="button"
              onClick={() => onAgregar(a.relacion, !!a.apoderado)}
              className="inline-flex items-center gap-1 rounded-full border border-border bg-surface px-2.5 py-1 text-xs font-semibold text-ink/70 hover:border-teal-400 hover:text-teal-700 dark:border-border-dark dark:bg-surface-dark dark:text-ink-dark/70 dark:hover:text-teal-accent-dark"
            >
              <Plus size={12} aria-hidden="true" /> {a.etiqueta}
            </button>
          ))}
        </div>
      )}
      {hermanos > 0 && (
        <p className="m-0 text-[12px] text-ink/50 dark:text-ink-dark/50">
          {hermanos === 1 ? "1 hermano/a registrado/a" : `${hermanos} hermanos/as registrados/as`} en la composición familiar.
        </p>
      )}
    </div>
  );
}
