import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    // 🆕 (sesión 2026-11-02) Archivos estáticos de terceros (p. ej. el worker
    // minificado de pdf.js): no son código del proyecto y sumaban ~1.600 avisos.
    "public/**",
  ]),
]);

export default eslintConfig;
