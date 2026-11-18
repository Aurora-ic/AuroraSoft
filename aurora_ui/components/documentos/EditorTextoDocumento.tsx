"use client";

import { useEffect, useRef } from "react";
import { EditorContent, useEditor, useEditorState, type Editor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { Placeholder } from "@tiptap/extensions";
import { Bold, IndentDecrease, IndentIncrease, Italic, List, ListOrdered, Redo2, Underline, Undo2, type LucideIcon } from "lucide-react";
import { documentoATexto, textoAHtml } from "@/lib/textoFormato";

// 🆕 (2026-11-18, opción B del plan de Documentos) Editor visual para las
// partes que redacta la psicóloga: se escribe viendo la negrita, la cursiva y
// las listas, como en un procesador de texto, en vez de teclear **marcas**.
//
// Lo que se GUARDA sigue siendo texto con marcas (lib/textoFormato.ts, mismo
// formato que dibuja el PDF): solo se permite lo que el PDF sabe imprimir —
// negrita, cursiva, subrayado, viñetas, numeradas y sangría de listas —; lo
// demás (títulos, tablas, colores, imágenes) se descarta también al PEGAR
// desde Word o Google Docs, que conserva lo permitido y deja el resto como
// texto normal.

const MARCAS_PERMITIDAS = StarterKit.configure({
  heading: false,
  blockquote: false,
  codeBlock: false,
  code: false,
  horizontalRule: false,
  strike: false,
  link: false,
});

export function EditorTextoDocumento({
  valor,
  onCambio,
  onSalir,
  etiqueta,
  placeholder = "Escribe aquí…",
}: {
  valor: string;
  onCambio: (texto: string) => void;
  onSalir?: () => void;
  /** Nombre accesible del cuadro (el título de la parte del documento). */
  etiqueta: string;
  placeholder?: string;
}) {
  // El último texto que salió de ESTE editor: si `valor` cambia a otra cosa
  // (carga inicial, otro documento) se recarga; si es el eco de lo que se
  // acaba de escribir, no (si no, el cursor saltaría al final en cada tecla).
  const ultimoEmitido = useRef<string | null>(null);
  const refOnCambio = useRef(onCambio);
  const refOnSalir = useRef(onSalir);
  useEffect(() => {
    refOnCambio.current = onCambio;
    refOnSalir.current = onSalir;
  });

  const editor = useEditor({
    extensions: [MARCAS_PERMITIDAS, Placeholder.configure({ placeholder })],
    content: textoAHtml(valor),
    immediatelyRender: false, // Next: sin render en el servidor
    editorProps: {
      attributes: {
        role: "textbox",
        "aria-multiline": "true",
        "aria-label": etiqueta,
        class:
          "editor-documento min-h-[9rem] px-3 py-2.5 text-[14px] leading-relaxed text-ink dark:text-ink-dark focus:outline-none",
      },
    },
    onUpdate: ({ editor: e }) => {
      const texto = documentoATexto(e.getJSON() as never);
      ultimoEmitido.current = texto;
      refOnCambio.current(texto);
    },
    onBlur: () => refOnSalir.current?.(),
  });

  useEffect(() => {
    if (!editor || valor === ultimoEmitido.current) return;
    if (documentoATexto(editor.getJSON() as never) === valor) return;
    editor.commands.setContent(textoAHtml(valor), { emitUpdate: false });
    ultimoEmitido.current = valor;
  }, [editor, valor]);

  return (
    <div className="overflow-hidden rounded-card border border-border bg-surface focus-within:ring-2 focus-within:ring-seccion-400 dark:border-border-dark dark:bg-surface-dark dark:focus-within:ring-seccion-claro">
      {editor && <BarraFormato editor={editor} />}
      <EditorContent editor={editor} />
    </div>
  );
}

function BarraFormato({ editor }: { editor: Editor }) {
  const estado = useEditorState({
    editor,
    selector: ({ editor: e }) => ({
      negrita: e.isActive("bold"),
      cursiva: e.isActive("italic"),
      subrayado: e.isActive("underline"),
      vinetas: e.isActive("bulletList"),
      numerada: e.isActive("orderedList"),
      enLista: e.isActive("listItem"),
      puedeSangrar: e.can().sinkListItem("listItem"),
      puedeDesangrar: e.can().liftListItem("listItem"),
      puedeDeshacer: e.can().undo(),
      puedeRehacer: e.can().redo(),
    }),
  });
  const cadena = () => editor.chain().focus();
  return (
    <div
      role="toolbar"
      aria-label="Formato del texto"
      className="flex flex-wrap items-center gap-0.5 border-b border-border bg-mist/60 px-1.5 py-1 dark:border-border-dark dark:bg-surface-raised-dark"
    >
      <BotonFormato icono={Bold} etiqueta="Negrita (Ctrl+B)" activo={estado.negrita} onClick={() => cadena().toggleBold().run()} />
      <BotonFormato icono={Italic} etiqueta="Cursiva (Ctrl+I)" activo={estado.cursiva} onClick={() => cadena().toggleItalic().run()} />
      <BotonFormato icono={Underline} etiqueta="Subrayado (Ctrl+U)" activo={estado.subrayado} onClick={() => cadena().toggleUnderline().run()} />
      <Separador />
      <BotonFormato icono={List} etiqueta="Viñetas" activo={estado.vinetas} onClick={() => cadena().toggleBulletList().run()} />
      <BotonFormato icono={ListOrdered} etiqueta="Lista numerada" activo={estado.numerada} onClick={() => cadena().toggleOrderedList().run()} />
      <BotonFormato
        icono={IndentIncrease}
        etiqueta="Aumentar sangría (Tab, dentro de una lista)"
        desactivado={!estado.puedeSangrar}
        onClick={() => cadena().sinkListItem("listItem").run()}
      />
      <BotonFormato
        icono={IndentDecrease}
        etiqueta="Reducir sangría (Mayús+Tab)"
        desactivado={!estado.puedeDesangrar}
        onClick={() => cadena().liftListItem("listItem").run()}
      />
      <Separador />
      <BotonFormato icono={Undo2} etiqueta="Deshacer (Ctrl+Z)" desactivado={!estado.puedeDeshacer} onClick={() => cadena().undo().run()} />
      <BotonFormato icono={Redo2} etiqueta="Rehacer (Ctrl+Y)" desactivado={!estado.puedeRehacer} onClick={() => cadena().redo().run()} />
    </div>
  );
}

function Separador() {
  return <span className="mx-1 h-5 w-px bg-border dark:bg-border-dark" aria-hidden="true" />;
}

function BotonFormato({
  icono: Icono,
  etiqueta,
  onClick,
  activo = false,
  desactivado = false,
}: {
  icono: LucideIcon;
  etiqueta: string;
  onClick: () => void;
  activo?: boolean;
  desactivado?: boolean;
}) {
  return (
    <button
      type="button"
      title={etiqueta}
      aria-label={etiqueta}
      aria-pressed={activo}
      disabled={desactivado}
      // mousedown sin perder el foco ni la selección del texto
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
      className={`flex h-8 w-8 items-center justify-center rounded-md transition-colors disabled:opacity-35 ${
        activo
          ? "bg-seccion-600/15 text-seccion-900 dark:bg-seccion-claro/20 dark:text-seccion-claro"
          : "text-ink/70 hover:bg-ink/5 dark:text-ink-dark/70 dark:hover:bg-white/5"
      }`}
    >
      <Icono size={15} aria-hidden="true" />
    </button>
  );
}
