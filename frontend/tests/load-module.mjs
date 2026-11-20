import { readFileSync } from "node:fs";
import ts from "typescript";

// Retain the prototype's Node test runner and project TypeScript compiler.
// Pure modules have only type imports, which compilation removes.
export async function loadModule(relativePath) {
  const source = readFileSync(new URL(relativePath, import.meta.url), "utf8");
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 },
  });
  return import(`data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`);
}
