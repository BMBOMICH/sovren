/// Sovereign Error Reporter
///
/// Shows errors like this:
///
///   Error at line 5, column 12:
///     set result = x + y
///                      ^
///   Type mismatch: expected int, got float
///   Hint: cast y to int with: y as int
use std::fmt::Write;

pub struct ErrorReporter {
    source_lines: Vec<String>,
    file_name: String,
    errors: Vec<ReportedError>,
    warnings: Vec<ReportedError>,
}

#[derive(Debug, Clone)]
pub struct ReportedError {
    pub line: usize,
    pub col: usize,
    pub end_col: usize,
    pub message: String,
    pub hint: Option<String>,
    pub is_warn: bool,
}

impl ErrorReporter {
    pub fn new(source: &str, file_name: &str) -> Self {
        ErrorReporter {
            source_lines: source.lines().map(|l| l.to_string()).collect(),
            file_name: file_name.to_string(),
            errors: Vec::new(),
            warnings: Vec::new(),
        }
    }

    pub fn error(&mut self, line: usize, col: usize, message: &str, hint: Option<&str>) {
        self.errors.push(ReportedError {
            line,
            col,
            end_col: col,
            message: message.to_string(),
            hint: hint.map(|s| s.to_string()),
            is_warn: false,
        });
    }

    pub fn error_span(
        &mut self,
        line: usize,
        col: usize,
        end_col: usize,
        message: &str,
        hint: Option<&str>,
    ) {
        self.errors.push(ReportedError {
            line,
            col,
            end_col,
            message: message.to_string(),
            hint: hint.map(|s| s.to_string()),
            is_warn: false,
        });
    }

    pub fn warning(&mut self, line: usize, col: usize, message: &str, hint: Option<&str>) {
        self.warnings.push(ReportedError {
            line,
            col,
            end_col: col,
            message: message.to_string(),
            hint: hint.map(|s| s.to_string()),
            is_warn: true,
        });
    }

    pub fn has_errors(&self) -> bool {
        !self.errors.is_empty()
    }

    pub fn print_all(&self) {
        for w in &self.warnings {
            self.print_one(w);
        }
        for e in &self.errors {
            self.print_one(e);
        }

        if !self.errors.is_empty() {
            eprintln!(
                "\n{} error(s) found in '{}'.",
                self.errors.len(),
                self.file_name
            );
        }
    }

    fn print_one(&self, err: &ReportedError) {
        let kind = if err.is_warn { "Warning" } else { "Error" };
        let color = if err.is_warn { "\x1b[33m" } else { "\x1b[31m" };
        let reset = "\x1b[0m";
        let bold = "\x1b[1m";

        // Header: Error[E001] at file.sov:5:12
        eprintln!(
            "{}{}{}{}:{}{}: {}{}{}\n",
            bold, color, kind, reset, bold, self.file_name, err.line, err.col, reset
        );

        // Source line
        if err.line > 0 && err.line <= self.source_lines.len() {
            let source_line = &self.source_lines[err.line - 1];
            let line_num = format!("{} | ", err.line);
            let pad = " ".repeat(line_num.len());

            eprintln!("{}{}", pad, "");
            eprintln!("{}{}{}", bold, line_num, reset);
            eprintln!("{}  {}", pad, source_line);

            // Error pointer
            let pointer_col = err.col.saturating_sub(1);
            let span_len = (err.end_col.saturating_sub(err.col)).max(1);
            let arrows = "^".repeat(span_len);
            eprintln!(
                "{}  {}{}{}{} {}",
                pad,
                " ".repeat(pointer_col),
                color,
                bold,
                arrows,
                reset
            );
        }

        // Message
        eprintln!("  {}{}{}", bold, err.message, reset);

        // Hint
        if let Some(hint) = &err.hint {
            eprintln!("  \x1b[36mHint:\x1b[0m {}", hint);
        }

        eprintln!();
    }

    /// Generate a "did you mean?" suggestion
    pub fn suggest_similar(word: &str, candidates: &[&str]) -> Option<String> {
        let mut best: Option<&str> = None;
        let mut best_dist: usize = usize::MAX;

        for &candidate in candidates {
            let dist = levenshtein(word, candidate);
            if dist < best_dist && dist <= 2 {
                best_dist = dist;
                best = Some(candidate);
            }
        }

        best.map(|s| format!("did you mean '{}'?", s))
    }
}

/// Levenshtein edit distance for spell-check suggestions
fn levenshtein(a: &str, b: &str) -> usize {
    let a: Vec<char> = a.chars().collect();
    let b: Vec<char> = b.chars().collect();
    let m = a.len();
    let n = b.len();
    let mut dp = vec![vec![0usize; n + 1]; m + 1];
    for i in 0..=m {
        dp[i][0] = i;
    }
    for j in 0..=n {
        dp[0][j] = j;
    }
    for i in 1..=m {
        for j in 1..=n {
            dp[i][j] = if a[i - 1] == b[j - 1] {
                dp[i - 1][j - 1]
            } else {
                1 + dp[i - 1][j].min(dp[i][j - 1]).min(dp[i - 1][j - 1])
            };
        }
    }
    dp[m][n]
}

/// Common error hints database
pub fn get_hint(error_type: &str, context: &str) -> Option<String> {
    match error_type {
        "type_mismatch_int_float" => Some(format!("Cast to int with: {} as int", context)),
        "type_mismatch_float_int" => Some(format!("Cast to float with: {} as float", context)),
        "use_after_move" => Some(format!(
            "Use 'copy {}' to explicitly copy the value",
            context
        )),
        "undefined_variable" => {
            let keywords = ["set", "task", "check", "loop", "print", "return"];
            ErrorReporter::suggest_similar(context, &keywords)
        }
        "missing_return" => Some("Add a 'return' statement at the end of this task".into()),
        "array_out_of_bounds" => Some("Use 'check index < arr_len { }' before accessing".into()),
        "null_deref" => Some(format!(
            "Add a null check: 'check {} != null {{ }}'",
            context
        )),
        "double_free" => Some(format!("Remove one of the 'free {}' calls", context)),
        _ => None,
    }
}
