// 🆕 (2026-11-18, editor con formato — opción B del plan de Documentos)
//
// El texto libre de un documento se GUARDA como texto con unas pocas marcas
// (nunca HTML), y el PDF lo dibuja con las mismas reglas
// (backend/modulos/documentos/pdf_generador.py, _renderizar_texto_libre):
//
//   **negrita**   *cursiva*   ++subrayado++
//   "• " / "- " / "* " al inicio de línea → viñeta
//   "1. " al inicio de línea → lista numerada
//   2 espacios delante por cada nivel → lista dentro de lista
//
// Este archivo convierte en los dos sentidos para el editor visual (TipTap):
// textoAHtml() al cargar y documentoATexto() al escribir. Un texto viejo (solo
// **negrita** y "• ") se abre y se guarda sin cambios.

// ---------- texto → HTML (para cargar en el editor) ----------

function escaparHtml(t: string): string {
  return t.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

/** Marcas de UNA línea → HTML. Mismo orden y mismas reglas que el PDF. */
export function marcasAHtml(linea: string): string {
  let t = escaparHtml(linea);
  t = t.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  t = t.replace(/\+\+(.+?)\+\+/g, "<u>$1</u>");
  t = t.replace(/(?<![*\w])\*(?![\s*])(.+?)(?<![\s*])\*(?![*\w])/g, "<em>$1</em>");
  return t;
}

const RE_VINETA = /^(\s*)[•\-*]\s+(.*)$/;
const RE_NUMERADA = /^(\s*)(\d{1,3})[.)]\s+(.*)$/;

function nivelDe(espacios: string): number {
  return Math.min(Math.floor(espacios.replace(/\t/g, "  ").length / 2), 6);
}

type Item = { tipo: "ul" | "ol"; nivel: number; inicio: number; html: string };

/** Lista plana de ítems (con su nivel) → listas anidadas en HTML. */
function listasAHtml(items: Item[]): string {
  let html = "";
  const pila: { tipo: "ul" | "ol"; nivel: number }[] = [];
  for (const it of items) {
    // Cerrar listas más profundas, o del mismo nivel pero de otro tipo.
    while (pila.length && (pila[pila.length - 1].nivel > it.nivel || (pila[pila.length - 1].nivel === it.nivel && pila[pila.length - 1].tipo !== it.tipo))) {
      html += `</li></${pila.pop()!.tipo}>`;
    }
    const tope = pila[pila.length - 1];
    if (!tope || tope.nivel < it.nivel) {
      // Abrir una lista nueva (dentro del <li> abierto si hay uno).
      html += it.tipo === "ol" && it.inicio !== 1 ? `<ol start="${it.inicio}">` : `<${it.tipo}>`;
      pila.push({ tipo: it.tipo, nivel: tope ? Math.max(it.nivel, tope.nivel + 1) : it.nivel });
    } else {
      html += "</li>";
    }
    html += `<li><p>${it.html}</p>`;
  }
  while (pila.length) html += `</li></${pila.pop()!.tipo}>`;
  return html;
}

export function textoAHtml(texto: string): string {
  if (!texto) return "";
  let html = "";
  let items: Item[] = [];
  const cerrarLista = () => {
    if (items.length) html += listasAHtml(items);
    items = [];
  };
  for (const linea of texto.split("\n")) {
    const v = RE_VINETA.exec(linea);
    const n = v ? null : RE_NUMERADA.exec(linea);
    if (v) {
      items.push({ tipo: "ul", nivel: nivelDe(v[1]), inicio: 1, html: marcasAHtml(v[2]) });
    } else if (n) {
      items.push({ tipo: "ol", nivel: nivelDe(n[1]), inicio: Number(n[2]), html: marcasAHtml(n[3]) });
    } else {
      cerrarLista();
      html += `<p>${marcasAHtml(linea.trim())}</p>`;
    }
  }
  cerrarLista();
  return html;
}

// ---------- documento del editor → texto (al escribir) ----------

type Marca = { type: string };
type Nodo = { type: string; text?: string; marks?: Marca[]; content?: Nodo[]; attrs?: Record<string, unknown> };

function textoEnLinea(nodos: Nodo[] | undefined): string {
  let salida = "";
  for (const n of nodos ?? []) {
    if (n.type === "hardBreak") {
      salida += " ";
      continue;
    }
    if (n.type !== "text" || !n.text) continue;
    const marcas = new Set((n.marks ?? []).map((m) => m.type));
    // Los espacios de los bordes van FUERA de la marca ("** a**" no se
    // reconocería al leer), así una palabra marcada con su espacio funciona.
    const m = /^(\s*)([\s\S]*?)(\s*)$/.exec(n.text)!;
    let t = m[2];
    if (t) {
      if (marcas.has("italic")) t = `*${t}*`;
      if (marcas.has("underline")) t = `++${t}++`;
      if (marcas.has("bold")) t = `**${t}**`;
    }
    salida += m[1] + t + m[3];
  }
  return salida;
}

function listaATexto(lista: Nodo, nivel: number, lineas: string[]) {
  const ordenada = lista.type === "orderedList";
  let numero = Number(lista.attrs?.start ?? 1) || 1;
  for (const item of lista.content ?? []) {
    let primera = true;
    for (const hijo of item.content ?? []) {
      if (hijo.type === "bulletList" || hijo.type === "orderedList") {
        listaATexto(hijo, nivel + 1, lineas);
      } else if (primera) {
        lineas.push(`${"  ".repeat(nivel)}${ordenada ? `${numero}.` : "•"} ${textoEnLinea(hijo.content)}`);
        primera = false;
      } else {
        // Un segundo párrafo dentro del mismo punto: línea con sangría.
        lineas.push(`${"  ".repeat(nivel + 1)}${textoEnLinea(hijo.content)}`);
      }
    }
    numero += 1;
  }
}

export function documentoATexto(doc: Nodo): string {
  const lineas: string[] = [];
  for (const bloque of doc.content ?? []) {
    if (bloque.type === "bulletList" || bloque.type === "orderedList") listaATexto(bloque, 0, lineas);
    else lineas.push(textoEnLinea(bloque.content));
  }
  // Las líneas vacías del final no aportan nada al PDF.
  while (lineas.length && !lineas[lineas.length - 1].trim()) lineas.pop();
  return lineas.join("\n");
}
