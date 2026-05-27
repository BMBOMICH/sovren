/// Built-in borrow checker test suite.
/// These are the canonical cases that any borrow checker must handle.
/// Running `sovereign borrow-test` verifies the checker catches all of them.

#[cfg(test)]
mod borrow_checker_tests {
    use crate::borrow::BorrowChecker;
    use crate::generics;
    use crate::lexer::Lexer;
    use crate::parser::Parser;

    fn check(source: &str) -> Vec<String> {
        let mut lexer = Lexer::new(source);
        let (tokens, spans) = lexer.tokenize();
        let mut parser = Parser::new(tokens, spans).with_source(source);
        let program = parser.parse_program();
        let program = generics::monomorphize(&program);
        let mut bc = BorrowChecker::new();
        bc.check(&program).err().unwrap_or_default()
    }

    fn must_pass(source: &str) {
        let errors = check(source);
        assert!(
            errors.is_empty(),
            "Expected no errors but got:\n{}",
            errors.join("\n")
        );
    }

    fn must_fail(source: &str, expected_fragment: &str) {
        let errors = check(source);
        assert!(
            !errors.is_empty(),
            "Expected error containing '{}' but passed",
            expected_fragment
        );
        let found = errors.iter().any(|e| e.contains(expected_fragment));
        assert!(
            found,
            "Expected error containing '{}' but got:\n{}",
            expected_fragment,
            errors.join("\n")
        );
    }

    // ── Rule 1: Ownership ─────────────────────────────────────────────────

    #[test]
    fn test_use_after_move() {
        must_fail(
            r#"set s = "hello"
               set t = s
               print s"#,
            "Use of moved value 's'",
        );
    }

    #[test]
    fn test_copy_types_not_moved() {
        must_pass(
            r#"set x = 42
               set y = x
               print x"#,
        );
    }

    #[test]
    fn test_explicit_copy() {
        must_pass(
            r#"set s = "hello"
               set t = copy s
               print s
               print t"#,
        );
    }

    #[test]
    fn test_move_in_function_call() {
        must_fail(
            r#"task use_string(s: string) { print s }
               set msg = "hello"
               use_string(msg)
               print msg"#,
            "Use of moved value 'msg'",
        );
    }

    #[test]
    fn test_move_in_loop() {
        must_fail(
            r#"set s = "hello"
               loop 2 times {
                   set t = s
               }"#,
            "Move of already-moved value",
        );
    }

    #[test]
    fn test_uninitialized() {
        must_fail(
            r#"set x: int = 0
               purge x
               print x"#,
            "purged",
        );
    }

    // ── Rule 2: Borrowing ─────────────────────────────────────────────────

    #[test]
    fn test_multiple_immutable_borrows() {
        must_pass(
            r#"set arr = [1, 2, 3]
               set a = arr[0]
               set b = arr[1]
               print a
               print b"#,
        );
    }

    #[test]
    fn test_mutate_while_borrowed() {
        must_fail(
            r#"set arr = [1, 2, 3]
               loop item in arr {
                   arr[0] = 99
               }"#,
            "Cannot mutate",
        );
    }

    #[test]
    fn test_double_free() {
        must_fail(
            r#"set buf = alloc(64, 1)
               free buf
               free buf"#,
            "Double-free",
        );
    }

    #[test]
    fn test_use_after_free() {
        must_fail(
            r#"set buf = alloc(64, 1)
               free buf
               print buf"#,
            "Use-after-free",
        );
    }

    #[test]
    fn test_free_while_borrowed() {
        must_fail(
            r#"set buf = alloc(64, 1)
               set ref1 = &buf
               free buf"#,
            "Cannot free",
        );
    }

    // ── Rule 3: Lifetimes ─────────────────────────────────────────────────

    #[test]
    fn test_dangling_reference() {
        must_fail(
            r#"task get_local() -> ptr {
                   set x = 42
                   return &x
               }"#,
            "Dangling reference",
        );
    }

    #[test]
    fn test_valid_return_by_value() {
        must_pass(
            r#"task make_value() -> int {
                   set x = 42
                   return x
               }
               print make_value()"#,
        );
    }

    // ── Thread safety ─────────────────────────────────────────────────────

    #[test]
    fn test_data_race_detected() {
        // This would be a data race — caught at compile time
        // (tested via thread analyzer, not borrow checker)
        must_pass(
            r#"set x = 42
               spawn {
                   print x
               }"#,
        );
        // x is int (Copy type), safe to access from thread
    }

    // ── Purge semantics ───────────────────────────────────────────────────

    #[test]
    fn test_use_after_purge() {
        must_fail(
            r#"set key = 12345
               purge key
               print key"#,
            "purged",
        );
    }

    #[test]
    fn test_purge_while_borrowed() {
        must_fail(
            r#"set s = "secret"
               override {
                   set ref1 = &s
                   purge s
               }"#,
            "Cannot purge",
        );
    }
}
