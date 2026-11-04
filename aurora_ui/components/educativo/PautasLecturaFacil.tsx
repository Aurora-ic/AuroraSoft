"use client";

import { useMemo } from "react";
import { BookOpenCheck } from "lucide-react";

// 🆕 (sesión 2026-11-02) Ayuda para que el colegio redacte un asentimiento
// más sencillo para los más pequeños (decisión del usuario: el texto lo
// escribe el colegio; el sistema solo ayuda a que se entienda).
//
// Son pautas de FORMA de lectura fácil (frases cortas, palabras cotidianas,
// una idea por línea), no de contenido: qué debe decir el asentimiento
// (voluntariedad, confidencialidad, a quién acudir) lo decide el colegio.
// La revisión automática es orientativa: cuenta palabras por frase y marca
// palabras largas; no reemplaza leerlo en voz alta con un estudiante.

const MAX_PALABRAS_FRASE = 15;
const LARGO_PALABRA_LARGA = 12;

const PAUTAS = [
  "Una idea por frase, y frases cortas: hasta 15 palabras.",
  "Palabras de todos los días. Si usas una difícil (por ejemplo «confidencial»), explícala con otras palabras.",
  "Háblale de tú, en presente y en positivo: «Puedes parar cuando quieras».",
  "Dile qué va a pasar: qué va a hacer, que no hay respuestas buenas ni malas y a quién puede preguntar.",
  "Una idea por línea: en el examen cada línea se muestra como un punto aparte.",
];

function analizar(texto: string) {
  const frases = texto
    .split(/(?<=[.!?])\s+|\n+/)
    .map((f) => f.trim())
    .filter(Boolean);
  const largas = frases.filter((f) => f.split(/\s+/).filter(Boolean).length > MAX_PALABRAS_FRASE);
  const palabras = texto.match(/[\p{L}]+/gu) ?? [];
  const palabrasLargas = Array.from(
    new Set(palabras.filter((p) => p.length >= LARGO_PALABRA_LARGA && !/^\p{Lu}/u.test(p)).map((p) => p.toLowerCase())),
  );
  return { frases: frases.length, largas, palabrasLargas };
}

export function PautasLecturaFacil({ contenido, destacado }: { contenido: string; destacado: boolean }) {
  const resultado = useMemo(() => analizar(contenido), [contenido]);

  return (
    <aside
      aria-label="Pautas de lectura fácil"
      className={`rounded-xl border p-4 text-[12.5px] ${
        destacado
          ? "border-acento-violeta/30 bg-acento-violeta/[0.06] dark:border-acento-violeta-dark/30 dark:bg-acento-violeta-dark/10"
          : "border-border bg-mist/50 dark:border-border-dark dark:bg-surface-raised-dark"
      }`}
    >
      <p className="m-0 flex items-center gap-2 font-semibold text-ink dark:text-ink-dark">
        <BookOpenCheck size={15} aria-hidden="true" className="text-acento-violeta dark:text-acento-violeta-dark" />
        Lectura fácil {destacado ? "— recomendada para este nivel" : ""}
      </p>
      <p className="m-0 mt-1 text-ink/60 dark:text-ink-dark/60">
        El contenido lo decide el colegio. Estas pautas solo ayudan a que un estudiante pequeño lo entienda.
      </p>
      <ul className="m-0 mt-2 list-disc space-y-1 pl-4 text-ink/70 dark:text-ink-dark/70">
        {PAUTAS.map((p) => (
          <li key={p}>{p}</li>
        ))}
      </ul>

      {contenido.trim().length > 0 && (
        <div className="mt-3 border-t border-border/70 pt-3 dark:border-border-dark" aria-live="polite">
          <p className="m-0 font-semibold text-ink dark:text-ink-dark">Revisión de este texto</p>
          <p className="m-0 mt-1 text-ink/65 dark:text-ink-dark/65">
            {resultado.frases} frase{resultado.frases === 1 ? "" : "s"} ·{" "}
            {resultado.largas.length === 0 ? (
              <span className="text-teal-800 dark:text-teal-accent-dark">ninguna pasa de {MAX_PALABRAS_FRASE} palabras</span>
            ) : (
              <span className="font-semibold text-acento-pizarra dark:text-acento-pizarra-dark">
                {resultado.largas.length} pasa{resultado.largas.length === 1 ? "" : "n"} de {MAX_PALABRAS_FRASE} palabras
              </span>
            )}
          </p>
          {resultado.largas.length > 0 && (
            <ul className="m-0 mt-1.5 list-disc space-y-1 pl-4 text-ink/60 dark:text-ink-dark/60">
              {resultado.largas.slice(0, 4).map((f) => (
                <li key={f} className="line-clamp-2">
                  {f}
                </li>
              ))}
            </ul>
          )}
          {resultado.palabrasLargas.length > 0 && (
            <p className="m-0 mt-1.5 text-ink/60 dark:text-ink-dark/60">
              Palabras largas que quizá convenga explicar: {resultado.palabrasLargas.slice(0, 8).join(", ")}.
            </p>
          )}
        </div>
      )}
    </aside>
  );
}
