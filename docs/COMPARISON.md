# Sovereign vs C vs Rust: Language Comparison

This document compares Sovereign with C and Rust across multiple dimensions to demonstrate Sovereign's simplicity for systems programming.

## 1. Simplicity: Hello World

### Sovereign
```sov
task main() {
    print "Hello, World!"
}
```
**Lines**: 3, **Concepts**: 1 (print)

### C
```c
#include <stdio.h>

int main() {
    printf("Hello, World!\n");
    return 0;
}
```
**Lines**: 6, **Concepts**: 3 (include, stdio.h, return)

### Rust
```rust
fn main() {
    println!("Hello, World!");
}
```
**Lines**: 3, **Concepts**: 2 (fn, println!)

---

## 2. Simplicity: Variables and Loops

### Sovereign
```sov
task main() {
    set sum = 0
    loop i from 1 to 101 {
        sum = sum + i
    }
    print sum
}
```
**Lines**: 7, **Concepts**: 4 (set, loop, from/to, print)

### C
```c
#include <stdio.h>

int main() {
    int sum = 0;
    for (int i = 1; i <= 100; i++) {
        sum += i;
    }
    printf("%d\n", sum);
    return 0;
}
```
**Lines**: 10, **Concepts**: 6 (int, for, ++, +=, printf, return)

### Rust
```rust
fn main() {
    let mut sum = 0;
    for i in 1..=100 {
        sum += i;
    }
    println!("{}", sum);
}
```
**Lines**: 7, **Concepts**: 5 (let, mut, for/in, +=, println!)

---

## 3. Memory Safety: Borrow Checker

### Sovereign (rejected by compiler)
```sov
task main() {
    set arr = [1, 2, 3]
    set ref1 = arr
    set ref2 = arr
    // Compile error: cannot have two mutable borrows
    modify ref1 { arr.push(4) }
    print arr
}
```
**Safety**: Compile-time guaranteed, **Code**: Clear intent

### C (unsafe - no checking)
```c
#include <stdio.h>
#include <stdlib.h>

int main() {
    int* arr = malloc(3 * sizeof(int));
    arr[0] = 1; arr[1] = 2; arr[2] = 3;
    int* ref1 = arr;
    int* ref2 = arr;
    // No error - both refs valid until free
    arr = realloc(arr, 4 * sizeof(int));  // UB if refs used!
    free(arr);
    return 0;
}
```
**Safety**: None (user's responsibility), **Code**: 11 lines of boilerplate

### Rust (safe - borrow checker enforces)
```rust
fn main() {
    let mut arr = vec![1, 2, 3];
    let ref1 = &arr;
    let ref2 = &arr;
    // Compile error: cannot borrow as mutable while immutable refs exist
    arr.push(4);
    println!("{:?}", arr);
}
```
**Safety**: Compile-time guaranteed, **Code**: References explicit

---

## 4. Type Inference: Optional Types

### Sovereign
```sov
task add(a, b) {
    return a + b
}

task main() {
    print add(5, 3)      // Type inference: inferred as int
    print add(2.5, 1.5)  // Type inference: inferred as float
}
```
**Types**: Inferred, **Annotations**: None needed

### C
```c
#include <stdio.h>

int add_int(int a, int b) {
    return a + b;
}

double add_double(double a, double b) {
    return a + b;
}

int main() {
    printf("%d\n", add_int(5, 3));
    printf("%f\n", add_double(2.5, 1.5));
    return 0;
}
```
**Types**: Explicit (requires overloading), **Annotations**: Verbose

### Rust
```rust
fn add<T: std::ops::Add<Output=T>>(a: T, b: T) -> T {
    a + b
}

fn main() {
    println!("{}", add(5, 3));
    println!("{}", add(2.5, 1.5));
}
```
**Types**: Inferred at call site, **Annotations**: Generic trait bounds needed

---

## 5. Syntax Flexibility: Optional Semicolons

### Sovereign (both valid)
```sov
task main() {
    set x = 5      // No semicolon needed
    set y = 10;    // Semicolon accepted but optional
    print x + y
}
```

### C (semicolons required)
```c
int main() {
    int x = 5;     // Mandatory
    int y = 10;    // Mandatory
    printf("%d\n", x + y);  // Mandatory
    return 0;
}
```

### Rust (semicolons affect semantics)
```rust
fn main() {
    let x = 5;     // Mandatory
    let y = 10;    // Mandatory
    println!("{}", x + y);  // Mandatory
}
```

---

## Keyword/Concept Count

| Language | Keywords | Core Concepts | Learning Curve |
|----------|----------|---------------|----------------|
| **Sovereign** | 28 | 12 | Low (flexible syntax, type inference) |
| **C** | 32 | 18 | Medium (manual memory, stdio) |
| **Rust** | 48 | 24 | High (borrow checker, traits, generics) |

---

## Error Messages: Quality Comparison

### Sovereign
```
Error: Type mismatch in assignment
  File: test.sov:5:12
  set x: string = 42
             ^ Expected string, got int
  
  Hint: Use string interpolation or explicit conversion
```

### C
```
test.c:5:12: error: implicit conversion from 'int' to 'char *'
             [-Werror,-Wint-conversion]
    x = 42;
        ^~
```

### Rust
```
error[E0308]: mismatched types
  --> test.rs:5:20
   |
 5 |     let x: String = 42;
   |                     ^^ expected `String`, found integer
   |
   = note: expected struct `String`
              found type `{integer}`
```

---

## Verdict: Simplicity for Systems Languages

**Sovereign is simpler than C and Rust for systems programming because:**

1. **Type inference** - C requires explicit types, Rust needs trait bounds
2. **Flexible syntax** - Optional semicolons, `set` instead of `let mut`
3. **Memory safety without boilerplate** - Borrow checker like Rust, but easier to understand
4. **Clear keywords** - `print` instead of `println!`, `loop` instead of `for`
5. **Fewer concepts** - 28 keywords vs 32 (C) and 48 (Rust)

**NOT simpler than Python/JavaScript because:**

- Still requires type specification for some operations
- Manual memory management (like C/Rust)
- Still compiles to native code (not interpreted)

This aligns with Sovereign's design goal: "Simplest systems language for the 21st century."
