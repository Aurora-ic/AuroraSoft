"use client";

import { useEffect, useState } from "react";
import { School } from "lucide-react";
import type { Institucion } from "@/types/api";

// 🆕 (2026-11-16, a pedido del usuario) Bloque de la institución arriba de la
// barra lateral. Antes era un cuadradito blanco de 48 px con el logo y el
// nombre al lado: con un logo cuadrado se veía chico, con uno horizontal
// (un escudo con texto al costado) quedaba ilegible, y el bloque era igual
// para todos los colegios. Ahora se adapta a CUALQUIER logo:
//   1. Colores: lee el logo en un canvas de 40×40 y saca hasta 3 colores
//      dominantes con saturación (ignora el blanco del fondo, grises y negros).
//      Con ellos tiñe un halo detrás del logo, el borde de su marco y una
//      cinta de colores al pie del bloque. Cada colegio se ve con los suyos.
//   2. Forma: un logo ancho (proporción ≥ 1.7) va a lo ancho del bloque con
//      el nombre debajo; uno cuadrado o vertical, en un marco de 64 px con
//      el nombre al lado.
// Si el canvas no se puede leer (logo externo sin CORS) o no hay logo, usa
// los verdes de la barra: nunca bloquea ni deja un hueco.

const PALETA_RESPALDO = ["#2BB3A0", "#7FE3D2", "#1C8F80"];

type Rgb = [number, number, number];

function aHex([r, g, b]: Rgb): string {
  return "#" + [r, g, b].map((v) => Math.round(v).toString(16).padStart(2, "0")).join("");
}

function rgbDe(hex: string): Rgb {
  return [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16)) as Rgb;
}

function hslDe([r, g, b]: Rgb): [number, number, number] {
  const rn = r / 255, gn = g / 255, bn = b / 255;
  const max = Math.max(rn, gn, bn), min = Math.min(rn, gn, bn);
  const l = (max + min) / 2;
  if (max === min) return [0, 0, l];
  const d = max - min;
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
  let h = max === rn ? (gn - bn) / d + (gn < bn ? 6 : 0) : max === gn ? (bn - rn) / d + 2 : (rn - gn) / d + 4;
  h *= 60;
  return [h, s, l];
}

// Agrupa los píxeles en 12 franjas de tono y devuelve el color medio de las
// franjas con más peso (cantidad × saturación), separadas entre sí.
function paletaDeImagen(img: HTMLImageElement): string[] {
  const lado = 40;
  const canvas = document.createElement("canvas");
  canvas.width = lado;
  canvas.height = lado;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) return [];
  ctx.drawImage(img, 0, 0, lado, lado);
  const datos = ctx.getImageData(0, 0, lado, lado).data; // lanza si el canvas quedó "tainted"
  const franjas = new Map<number, { peso: number; suma: Rgb; n: number }>();
  for (let i = 0; i < datos.length; i += 4) {
    if (datos[i + 3] < 128) continue; // transparente
    const rgb: Rgb = [datos[i], datos[i + 1], datos[i + 2]];
    const [h, s, l] = hslDe(rgb);
    if (s < 0.28 || l < 0.12 || l > 0.9) continue; // fondo blanco, grises, negro
    const clave = Math.floor(h / 30) % 12;
    const f = franjas.get(clave) ?? { peso: 0, suma: [0, 0, 0] as Rgb, n: 0 };
    f.peso += s;
    f.suma = [f.suma[0] + rgb[0], f.suma[1] + rgb[1], f.suma[2] + rgb[2]];
    f.n += 1;
    franjas.set(clave, f);
  }
  const total = [...franjas.values()].reduce((a, f) => a + f.peso, 0);
  return [...franjas.values()]
    .filter((f) => f.peso >= total * 0.04) // un color que es apenas un detalle no cuenta
    .sort((a, b) => b.peso - a.peso)
    .slice(0, 3)
    .map((f) => aHex([f.suma[0] / f.n, f.suma[1] / f.n, f.suma[2] / f.n]));
}

type LecturaLogo = { url: string; paleta: string[]; proporcion: number };

function useLecturaLogo(url: string | null | undefined): LecturaLogo | null {
  const [lectura, setLectura] = useState<LecturaLogo | null>(null);
  useEffect(() => {
    if (!url) return;
    let vigente = true;
    // Una imagen aparte con crossOrigin: si el servidor del logo no da CORS,
    // solo falla esta lectura, nunca el <img> que se muestra.
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => {
      if (!vigente) return;
      const proporcion = img.naturalHeight ? img.naturalWidth / img.naturalHeight : 1;
      let paleta: string[] = [];
      try {
        paleta = paletaDeImagen(img);
      } catch {
        paleta = [];
      }
      setLectura({ url, paleta, proporcion });
    };
    img.onerror = () => vigente && setLectura({ url, paleta: [], proporcion: 1 });
    img.src = url;
    return () => {
      vigente = false;
    };
  }, [url]);
  return lectura && lectura.url === url ? lectura : null;
}

export function inicialesInstitucion(nombre: string): string {
  const palabras = nombre
    .replace(/[^\p{L}\s]/gu, " ")
    .split(/\s+/)
    .filter((w) => w.length > 2 || /^[A-ZÁÉÍÓÚÑ]/.test(w));
  return (palabras.slice(0, 2).map((w) => w[0]).join("") || nombre.slice(0, 2)).toUpperCase();
}

export function BloqueInstitucion({ institucion }: { institucion: Institucion | null }) {
  const logo = institucion?.logo_url || null;
  const lectura = useLecturaLogo(logo);
  const paleta = lectura?.paleta.length ? lectura.paleta : PALETA_RESPALDO;
  const [c1, c2 = c1, c3 = c2] = paleta;
  const ancho = (lectura?.proporcion ?? 1) >= 1.7;
  // El punto junto al año va sobre fondo oscuro: el color más claro de la paleta.
  const claro = [...paleta].sort((a, b) => hslDe(rgbDe(b))[2] - hslDe(rgbDe(a))[2])[0];
  const nombre = institucion?.nombre ?? "Mi institución";
  const detalle = institucion?.anio_escolar_activo
    ? `Año escolar ${institucion.anio_escolar_activo}`
    : institucion?.tipo || "Institución educativa";

  const marco = (
    <span
      className={`relative flex shrink-0 items-center justify-center overflow-hidden bg-white ${
        ancho ? "h-14 w-full rounded-xl px-3" : "h-16 w-16 rounded-2xl"
      }`}
      style={{ boxShadow: `0 0 0 2px ${c1}66, 0 10px 24px -10px ${c1}aa` }}
    >
      {logo ? (
        // eslint-disable-next-line @next/next/no-img-element -- URL configurada por la institución (mismo <img> que Configuración)
        <img src={logo} alt={`Logo de ${nombre}`} className={`h-full w-full object-contain ${ancho ? "py-1.5" : "p-1.5"}`} />
      ) : institucion ? (
        <span className="font-display text-[18px] font-bold" style={{ color: c3 === c1 ? "#0E4A44" : c3 }}>
          {inicialesInstitucion(nombre)}
        </span>
      ) : (
        <School size={22} className="text-teal-900/60" aria-hidden="true" />
      )}
    </span>
  );

  return (
    <div className="relative overflow-hidden rounded-2xl border border-white/10 bg-white/[0.04]">
      {/* Halo con los colores del logo: dos manchas difuminadas detrás del marco. */}
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 transition-opacity duration-500">
        <div className="absolute -left-8 -top-10 h-32 w-32 rounded-full opacity-45 blur-2xl" style={{ background: c1 }} />
        <div className="absolute -bottom-12 -right-6 h-28 w-28 rounded-full opacity-35 blur-2xl" style={{ background: c2 }} />
      </div>

      <div className={`relative p-3.5 ${ancho ? "space-y-3" : "flex items-center gap-3"}`}>
        {marco}
        <div className="min-w-0">
          <p className="m-0 font-display text-[14.5px] font-bold leading-snug text-white line-clamp-2" title={nombre}>
            {nombre}
          </p>
          <p className="m-0 mt-1 inline-flex max-w-full items-center gap-1.5 truncate rounded-full bg-black/20 px-2 py-0.5 text-[11.5px] text-white/75">
            <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: claro }} aria-hidden="true" />
            <span className="truncate">{detalle}</span>
          </p>
        </div>
      </div>

      {/* Cinta con los colores del colegio, en el orden de su peso en el logo. */}
      <div aria-hidden="true" className="relative flex h-[3px]">
        <span className="flex-[3]" style={{ background: c1 }} />
        <span className="flex-[2]" style={{ background: c2 }} />
        <span className="flex-1" style={{ background: c3 }} />
      </div>
    </div>
  );
}
