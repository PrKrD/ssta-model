import { readFileSync } from "node:fs";
import ts from "typescript";

// Retain the prototype's Node test runner and project TypeScript compiler.
// Resolve local imports for DOM-free modules without adding a test framework.
const urls = new Map();
async function moduleUrl(url) {
  if (urls.has(url.href)) return urls.get(url.href);
  const source = readFileSync(url, "utf8");
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 },
  });
  let code = outputText;
  for (const match of outputText.matchAll(/from ["'](\.[^"']+)["']/g)) {
    const child = new URL(`${match[1]}.ts`, url);
    code = code.replace(match[0], `from "${await moduleUrl(child)}"`);
  }
  const result = `data:text/javascript;base64,${Buffer.from(code).toString("base64")}`;
  urls.set(url.href, result);
  return result;
}
export async function loadModule(relativePath) {
  return import(await moduleUrl(new URL(relativePath, import.meta.url)));
}
