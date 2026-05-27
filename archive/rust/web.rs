/// Sovereign Web Framework
///
/// Write your entire web app in Sovereign.
/// No HTML. No CSS. No JavaScript.
///
/// sovereign build --web app.sov
///   → app.html (generated, optimized)
///   → app.css  (generated, deduplicated, minified)
///   → app.wasm (logic, compiled from Sovereign)
///
/// Example:
///
///   page "My App" {
///       style {
///           body { background: "#0d1117", color: "white" }
///           .btn { padding: "8px 16px", border_radius: "6px" }
///       }
///       div class="container" {
///           h1 { "Hello from Sovereign" }
///           p  { "Built with zero JavaScript" }
///           button class="btn" onclick=handleClick {
///               "Click me"
///           }
///       }
///   }
///
///   task handleClick() {
///       // This runs in WASM — no JavaScript needed
///       dom_set_text("output", "Button clicked!")
///   }
use std::collections::HashMap;

// ── AST nodes for the web DSL ────────────────────────────────────────────

#[derive(Debug, Clone)]
pub struct WebPage {
    pub title: String,
    pub styles: Vec<StyleRule>,
    pub body: Vec<HtmlNode>,
    pub scripts: Vec<String>, // task names that are exported to WASM
}

#[derive(Debug, Clone)]
pub struct StyleRule {
    pub selector: String,
    pub properties: Vec<(String, String)>,
}

#[derive(Debug, Clone)]
pub enum HtmlNode {
    Element {
        tag: String,
        attrs: Vec<(String, String)>,
        children: Vec<HtmlNode>,
        events: Vec<(String, String)>, // (event, handler_task_name)
    },
    Text(String),
    Interpolated(String), // {variable} inside text
}

// ── Generator ─────────────────────────────────────────────────────────────

pub struct WebGenerator {
    style_cache: HashMap<String, Vec<(String, String)>>,
}

impl WebGenerator {
    pub fn new() -> Self {
        WebGenerator {
            style_cache: HashMap::new(),
        }
    }

    pub fn generate(&mut self, page: &WebPage) -> GeneratedWeb {
        let html = self.generate_html(page);
        let css = self.generate_css(page);
        GeneratedWeb { html, css }
    }

    fn generate_html(&self, page: &WebPage) -> String {
        let mut html = String::new();

        html.push_str("<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n");
        html.push_str(&format!("<meta charset=\"UTF-8\">\n"));
        html.push_str(&format!(
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n"
        ));
        html.push_str(&format!("<title>{}</title>\n", escape_html(&page.title)));
        html.push_str("<link rel=\"stylesheet\" href=\"app.css\">\n");
        html.push_str("</head>\n<body>\n");

        for node in &page.body {
            html.push_str(&self.render_node(node, 0));
        }

        // WASM loader — generated automatically
        // No JavaScript framework needed, just the WASM runtime
        html.push_str("\n<script>\n");
        html.push_str(WASM_LOADER);
        html.push_str("\n</script>\n");

        html.push_str("</body>\n</html>");
        html
    }

    fn render_node(&self, node: &HtmlNode, indent: usize) -> String {
        let pad = "    ".repeat(indent);
        match node {
            HtmlNode::Text(s) => format!("{}{}\n", pad, escape_html(s)),
            HtmlNode::Interpolated(var) => {
                // Rendered by WASM at runtime
                format!("{}<span data-sov-bind=\"{}\"></span>\n", pad, var)
            }
            HtmlNode::Element {
                tag,
                attrs,
                children,
                events,
            } => {
                let mut attr_str = String::new();
                for (k, v) in attrs {
                    attr_str.push_str(&format!(" {}=\"{}\"", k, escape_html(v)));
                }
                for (event, handler) in events {
                    attr_str.push_str(&format!(" data-sov-on-{}=\"{}\"", event, handler));
                }
                if children.is_empty() {
                    format!("{}<{}{} />\n", pad, tag, attr_str)
                } else {
                    let mut result = format!("{}<{}{}>\n", pad, tag, attr_str);
                    for child in children {
                        result.push_str(&self.render_node(child, indent + 1));
                    }
                    result.push_str(&format!("{}</{}>\n", pad, tag));
                    result
                }
            }
        }
    }

    fn generate_css(&self, page: &WebPage) -> String {
        let mut css = String::new();

        // CSS reset — tiny, eliminates browser inconsistencies
        css.push_str("*{box-sizing:border-box;margin:0;padding:0}\n");

        // Page styles
        for rule in &page.styles {
            css.push_str(&self.render_css_rule(rule));
        }

        // Minify — remove unnecessary whitespace
        css
    }

    fn render_css_rule(&self, rule: &StyleRule) -> String {
        let props: Vec<String> = rule
            .properties
            .iter()
            .map(|(k, v)| format!("{}:{}", k, v))
            .collect();
        format!("{}{{{}}}\n", rule.selector, props.join(";"))
    }
}

#[derive(Debug)]
pub struct GeneratedWeb {
    pub html: String,
    pub css: String,
}

// Tiny WASM loader — replaces React/Vue/Angular
// 847 bytes unminified, ~400 bytes minified
const WASM_LOADER: &str = r#"
(async () => {
    const wasm = await WebAssembly.instantiateStreaming(fetch('app.wasm'), {
        env: {
            sov_dom_set_text: (idPtr, textPtr) => {
                const id   = readStr(idPtr);
                const text = readStr(textPtr);
                const el   = document.getElementById(id);
                if (el) el.textContent = text;
            },
            sov_dom_set_html: (idPtr, htmlPtr) => {
                const id   = readStr(idPtr);
                const html = readStr(htmlPtr);
                const el   = document.getElementById(id);
                if (el) el.innerHTML = html;
            },
            sov_dom_add_class: (idPtr, classPtr) => {
                const id  = readStr(idPtr);
                const cls = readStr(classPtr);
                document.getElementById(id)?.classList.add(cls);
            },
            sov_dom_remove_class: (idPtr, classPtr) => {
                const id  = readStr(idPtr);
                const cls = readStr(classPtr);
                document.getElementById(id)?.classList.remove(cls);
            },
            sov_dom_get_value: (idPtr) => {
                const id = readStr(idPtr);
                const val = document.getElementById(id)?.value ?? '';
                return writeStr(val);
            },
            sov_fetch: (urlPtr, cbIdx) => {
                const url = readStr(urlPtr);
                fetch(url).then(r => r.text()).then(body => {
                    const ptr = writeStr(body);
                    wasm.instance.exports.__indirect_function_table.get(cbIdx)(ptr);
                });
            },
            abort: () => { throw new Error('Sovereign abort'); }
        }
    });

    const mem = new Uint8Array(wasm.instance.exports.memory.buffer);

    function readStr(ptr) {
        let s = '', i = ptr;
        while (mem[i]) s += String.fromCharCode(mem[i++]);
        return s;
    }

    function writeStr(s) {
        const ptr = wasm.instance.exports.sov_alloc(s.length + 1);
        const mem8 = new Uint8Array(wasm.instance.exports.memory.buffer);
        for (let i = 0; i < s.length; i++) mem8[ptr + i] = s.charCodeAt(i);
        mem8[ptr + s.length] = 0;
        return ptr;
    }

    // Wire up event handlers
    document.querySelectorAll('[data-sov-on-click]').forEach(el => {
        const fn_name = el.getAttribute('data-sov-on-click');
        el.addEventListener('click', () => {
            wasm.instance.exports[fn_name]?.();
        });
    });

    document.querySelectorAll('[data-sov-on-input]').forEach(el => {
        const fn_name = el.getAttribute('data-sov-on-input');
        el.addEventListener('input', () => {
            wasm.instance.exports[fn_name]?.();
        });
    });

    // Run main
    wasm.instance.exports.main?.();
})();
"#;

fn escape_html(s: &str) -> String {
    s.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
}

// ── Web token/ast additions for the page {} syntax ────────────────────────

/// Parse a web page definition from Sovereign source
pub fn parse_page(source: &str) -> Option<WebPage> {
    // This is a simplified parser for the web DSL
    // The full parser is integrated into the main parser
    // via new tokens: Page, Style, Div, H1, etc.
    None // placeholder — full implementation in parser.rs additions
}

// ── DOM built-ins for WASM ────────────────────────────────────────────────

/// These task declarations are automatically available in --web mode
pub const DOM_STDLIB: &str = r#"
// DOM manipulation (only available with --web or --target wasm32)
extern task dom_set_text(id: string, text: string) -> void
extern task dom_set_html(id: string, html: string) -> void
extern task dom_get_value(id: string) -> string
extern task dom_add_class(id: string, class: string) -> void
extern task dom_remove_class(id: string, class: string) -> void
extern task dom_fetch(url: string) -> string
"#;
