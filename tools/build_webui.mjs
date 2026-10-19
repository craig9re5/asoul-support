// Offline JSX compiler. Python passes paths as argv and source text as JSON stdin.
import fs from "node:fs";
import { createRequire } from "node:module";
import vm from "node:vm";

try {
  const require = createRequire(import.meta.url);
  const Babel = require(process.argv[2]);
  if (Babel.version !== "7.29.0") {
    throw new Error(`Expected @babel/standalone 7.29.0, found ${Babel.version}`);
  }
  const sources = JSON.parse(fs.readFileSync(0, "utf8"));
  const outputs = sources.map(({ name, source }) => {
    const result = Babel.transform(source, {
      filename: name,
      babelrc: false,
      configFile: false,
      sourceType: "script",
      presets: [["react", { runtime: "classic", development: false }]],
      comments: true,
      compact: false,
      minified: false,
      sourceMaps: false,
    });
    // Each classic script gets its own scope; exports are explicit window fields.
    const code = `(function () {\n"use strict";\n${result.code}\n})();\n`;
    new vm.Script(code, { filename: name.replace(/\.jsx$/, ".js") });
    return { name, code };
  });
  process.stdout.write(JSON.stringify(outputs));
} catch (error) {
  process.stderr.write(`${error.message || error}\n`);
  process.exitCode = 1;
}
