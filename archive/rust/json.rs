/// Native JSON support for Sovereign.
///
/// Built-in, zero-dependency JSON:
///   set data = json_parse("{\"name\":\"Alice\",\"age\":30}")
///   set name = json_get(data, "name")
///   set output = json_stringify(data)
///
/// This makes Sovereign better than C for web/API work
/// without any external libraries.
use std::collections::HashMap;

#[derive(Debug, Clone)]
pub enum JsonValue {
    Null,
    Bool(bool),
    Number(f64),
    Str(String),
    Array(Vec<JsonValue>),
    Object(HashMap<String, JsonValue>),
}

impl JsonValue {
    pub fn to_string(&self) -> String {
        match self {
            JsonValue::Null => "null".to_string(),
            JsonValue::Bool(b) => b.to_string(),
            JsonValue::Number(n) => {
                if n.fract() == 0.0 && n.abs() < 1e15 {
                    format!("{}", *n as i64)
                } else {
                    format!("{}", n)
                }
            }
            JsonValue::Str(s) => format!("\"{}\"", s.replace('"', "\\\"")),
            JsonValue::Array(arr) => {
                let items: Vec<String> = arr.iter().map(|v| v.to_string()).collect();
                format!("[{}]", items.join(","))
            }
            JsonValue::Object(obj) => {
                let items: Vec<String> = obj
                    .iter()
                    .map(|(k, v)| format!("\"{}\":{}", k, v.to_string()))
                    .collect();
                format!("{{{}}}", items.join(","))
            }
        }
    }
}

pub struct JsonParser {
    source: Vec<char>,
    pos: usize,
}

impl JsonParser {
    pub fn new(s: &str) -> Self {
        JsonParser {
            source: s.chars().collect(),
            pos: 0,
        }
    }

    pub fn parse(&mut self) -> Result<JsonValue, String> {
        self.skip_ws();
        let result = self.parse_value()?;
        Ok(result)
    }

    fn skip_ws(&mut self) {
        while self.pos < self.source.len()
            && matches!(self.source[self.pos], ' ' | '\t' | '\n' | '\r')
        {
            self.pos += 1;
        }
    }

    fn current(&self) -> Option<char> {
        self.source.get(self.pos).copied()
    }

    fn advance(&mut self) {
        self.pos += 1;
    }

    fn parse_value(&mut self) -> Result<JsonValue, String> {
        self.skip_ws();
        match self.current() {
            Some('n') => {
                self.pos += 4;
                Ok(JsonValue::Null)
            }
            Some('t') => {
                self.pos += 4;
                Ok(JsonValue::Bool(true))
            }
            Some('f') => {
                self.pos += 5;
                Ok(JsonValue::Bool(false))
            }
            Some('"') => self.parse_string().map(JsonValue::Str),
            Some('[') => self.parse_array(),
            Some('{') => self.parse_object(),
            Some(c) if c == '-' || c.is_ascii_digit() => self.parse_number(),
            other => Err(format!("Unexpected char: {:?}", other)),
        }
    }

    fn parse_string(&mut self) -> Result<String, String> {
        self.advance(); // skip "
        let mut s = String::new();
        while let Some(c) = self.current() {
            if c == '"' {
                self.advance();
                return Ok(s);
            }
            if c == '\\' {
                self.advance();
                match self.current() {
                    Some('"') => s.push('"'),
                    Some('\\') => s.push('\\'),
                    Some('/') => s.push('/'),
                    Some('n') => s.push('\n'),
                    Some('t') => s.push('\t'),
                    Some('r') => s.push('\r'),
                    _ => {}
                }
            } else {
                s.push(c);
            }
            self.advance();
        }
        Err("Unterminated string".into())
    }

    fn parse_number(&mut self) -> Result<JsonValue, String> {
        let start = self.pos;
        if self.current() == Some('-') {
            self.advance();
        }
        while self.current().map_or(false, |c| c.is_ascii_digit()) {
            self.advance();
        }
        if self.current() == Some('.') {
            self.advance();
            while self.current().map_or(false, |c| c.is_ascii_digit()) {
                self.advance();
            }
        }
        if matches!(self.current(), Some('e') | Some('E')) {
            self.advance();
            if matches!(self.current(), Some('+') | Some('-')) {
                self.advance();
            }
            while self.current().map_or(false, |c| c.is_ascii_digit()) {
                self.advance();
            }
        }
        let s: String = self.source[start..self.pos].iter().collect();
        s.parse::<f64>()
            .map(JsonValue::Number)
            .map_err(|_| format!("Invalid number: {}", s))
    }

    fn parse_array(&mut self) -> Result<JsonValue, String> {
        self.advance(); // [
        let mut items = Vec::new();
        self.skip_ws();
        if self.current() == Some(']') {
            self.advance();
            return Ok(JsonValue::Array(items));
        }
        loop {
            items.push(self.parse_value()?);
            self.skip_ws();
            match self.current() {
                Some(',') => {
                    self.advance();
                    self.skip_ws();
                }
                Some(']') => {
                    self.advance();
                    break;
                }
                other => return Err(format!("Expected , or ], got {:?}", other)),
            }
        }
        Ok(JsonValue::Array(items))
    }

    fn parse_object(&mut self) -> Result<JsonValue, String> {
        self.advance(); // {
        let mut map = HashMap::new();
        self.skip_ws();
        if self.current() == Some('}') {
            self.advance();
            return Ok(JsonValue::Object(map));
        }
        loop {
            self.skip_ws();
            let key = self.parse_string()?;
            self.skip_ws();
            if self.current() != Some(':') {
                return Err(format!("Expected :"));
            }
            self.advance();
            let val = self.parse_value()?;
            map.insert(key, val);
            self.skip_ws();
            match self.current() {
                Some(',') => {
                    self.advance();
                }
                Some('}') => {
                    self.advance();
                    break;
                }
                other => return Err(format!("Expected , or }}, got {:?}", other)),
            }
        }
        Ok(JsonValue::Object(map))
    }
}

pub fn parse(s: &str) -> Result<JsonValue, String> {
    JsonParser::new(s).parse()
}

pub fn stringify(val: &JsonValue) -> String {
    val.to_string()
}
