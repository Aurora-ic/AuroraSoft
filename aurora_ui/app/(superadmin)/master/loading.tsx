import { EsqueletoSeccion } from "@/components/ui/PantallaCarga";

// 🆕 (2026-11-17, plan de UX fase 1) Lo que se ve AL INSTANTE al hacer clic
// en el menú, mientras llega la pantalla: la franja con el color de la
// sección de destino y la silueta del contenido. Antes no pasaba nada
// visible hasta que la página nueva estaba lista. Se pinta dentro del menú
// lateral y la barra superior, que no se recargan.
export default function Cargando() {
  return <EsqueletoSeccion />;
}
