import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11.12.0/dist/mermaid.esm.min.mjs";

mermaid.initialize({ startOnLoad: false, securityLevel: "strict" });
const diagrams = [...document.querySelectorAll("code.language-mermaid, pre.language-mermaid > code")].map((code) => {
  const diagram = document.createElement("div");
  diagram.className = "mermaid";
  diagram.textContent = code.textContent;
  code.parentElement.replaceWith(diagram);
  return diagram;
});
await mermaid.run({ nodes: diagrams });
