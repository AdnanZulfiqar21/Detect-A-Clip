// Strict bounded JSON reader, port of android PackIndex.kt MiniJson (and Python strict_json_loads
// in l0/dac_l0/index/format.py). Rejects duplicate keys and NaN/Infinity; integers without a
// fraction or exponent become .int, other numbers .double. Foundation's JSONSerialization is not
// used because it neither rejects duplicate keys nor distinguishes 1 from 1.0 portably.
// Status: compiled and tested only where CI runs `swift test` (see docs/TEST_EVIDENCE.md).

public enum JSONValue: Equatable {
    case null
    case bool(Bool)
    case int(Int64)
    case double(Double)
    case string(String)
    case array([JSONValue])
    case object(JSONObject)

    public var string: String? { if case .string(let s) = self { return s }; return nil }
    public var int: Int64? { if case .int(let v) = self { return v }; return nil }
    public var array: [JSONValue]? { if case .array(let a) = self { return a }; return nil }
    public var object: JSONObject? { if case .object(let o) = self { return o }; return nil }
    public var isNull: Bool { if case .null = self { return true }; return false }
    /// JSON number as Double (int or double); nil for any other type (booleans are not numbers).
    public var number: Double? {
        switch self { case .int(let v): return Double(v); case .double(let d): return d; default: return nil }
    }
}

/// Insertion-ordered object with unique keys.
public struct JSONObject: Equatable {
    public private(set) var keys: [String] = []
    private var values: [String: JSONValue] = [:]
    public init() {}
    public subscript(_ k: String) -> JSONValue? { values[k] }
    public var keySet: Set<String> { Set(keys) }
    public var count: Int { keys.count }
    mutating func insert(_ k: String, _ v: JSONValue) -> Bool {
        if values[k] != nil { return false }
        keys.append(k); values[k] = v
        return true
    }
}

public enum MiniJson {
    public struct ParseError: Error { public let message: String }

    public static func parse(_ text: String) throws -> JSONValue {
        var p = Parser(Array(text.utf16))
        let v = try p.value(0)
        p.ws()
        guard p.i == p.s.count else { throw ParseError(message: "trailing data") }
        return v
    }

    private struct Parser {
        let s: [UInt16]
        var i = 0
        init(_ s: [UInt16]) { self.s = s }

        static let quote: UInt16 = 0x22, backslash: UInt16 = 0x5C, slash: UInt16 = 0x2F
        static func isDigit(_ c: UInt16) -> Bool { c >= 0x30 && c <= 0x39 }

        func fail(_ m: String) -> ParseError { ParseError(message: m) }

        mutating func ws() { while i < s.count && (s[i] == 0x20 || s[i] == 0x09 || s[i] == 0x0D || s[i] == 0x0A) { i += 1 } }

        mutating func value(_ depth: Int) throws -> JSONValue {
            guard depth < 32 else { throw fail("nesting too deep") }
            ws()
            guard i < s.count else { throw fail("unexpected end") }
            switch s[i] {
            case 0x7B: return try obj(depth)                    // {
            case 0x5B: return try arr(depth)                    // [
            case Parser.quote: return .string(try str())
            case 0x74: return try lit("true", .bool(true))
            case 0x66: return try lit("false", .bool(false))
            case 0x6E: return try lit("null", .null)
            default:
                if s[i] == 0x2D || Parser.isDigit(s[i]) { return try num() }
                throw fail("bad token at \(i)")
            }
        }

        mutating func lit(_ w: String, _ v: JSONValue) throws -> JSONValue {
            let u = Array(w.utf16)
            guard i + u.count <= s.count, Array(s[i..<(i + u.count)]) == u else { throw fail("bad literal") }
            i += u.count
            return v
        }

        /// Same grammar as Kotlin: -?(0|[1-9][0-9]*)(\.[0-9]+)?([eE][+-]?[0-9]+)?
        mutating func num() throws -> JSONValue {
            let st = i
            while i < s.count && (Parser.isDigit(s[i]) || s[i] == 0x2B || s[i] == 0x2D || s[i] == 0x2E || s[i] == 0x45 || s[i] == 0x65) { i += 1 }
            let t = Array(s[st..<i])
            var k = 0
            if k < t.count && t[k] == 0x2D { k += 1 }
            guard k < t.count, Parser.isDigit(t[k]) else { throw fail("bad number") }
            if t[k] == 0x30 { k += 1 } else { while k < t.count && Parser.isDigit(t[k]) { k += 1 } }
            var integral = true
            if k < t.count && t[k] == 0x2E {
                integral = false; k += 1
                let d0 = k
                while k < t.count && Parser.isDigit(t[k]) { k += 1 }
                guard k > d0 else { throw fail("bad number") }
            }
            if k < t.count && (t[k] == 0x45 || t[k] == 0x65) {
                integral = false; k += 1
                if k < t.count && (t[k] == 0x2B || t[k] == 0x2D) { k += 1 }
                let d0 = k
                while k < t.count && Parser.isDigit(t[k]) { k += 1 }
                guard k > d0 else { throw fail("bad number") }
            }
            guard k == t.count else { throw fail("bad number") }
            let text = String(decoding: t, as: UTF16.self)
            if integral, let v = Int64(text) { return .int(v) }
            guard let d = Double(text), d.isFinite else { throw fail("number out of range") }
            return .double(d)
        }

        mutating func hex4() throws -> UInt16 {
            guard i + 4 <= s.count else { throw fail("bad escape") }
            var v: UInt16 = 0
            for k in 0..<4 {
                let c = s[i + k]
                let d: UInt16
                switch c {
                case 0x30...0x39: d = c - 0x30
                case 0x41...0x46: d = c - 0x41 + 10
                case 0x61...0x66: d = c - 0x61 + 10
                default: throw fail("bad escape")
                }
                v = v << 4 | d
            }
            i += 4
            return v
        }

        mutating func str() throws -> String {
            i += 1
            var out: [UInt16] = []
            while true {
                guard i < s.count else { throw fail("unterminated string") }
                let c = s[i]; i += 1
                if c == Parser.quote { return String(decoding: out, as: UTF16.self) }
                if c == Parser.backslash {
                    guard i < s.count else { throw fail("bad escape") }
                    let e = s[i]; i += 1
                    switch e {
                    case Parser.quote, Parser.backslash, Parser.slash: out.append(e)
                    case 0x62: out.append(0x08)
                    case 0x66: out.append(0x0C)
                    case 0x6E: out.append(0x0A)
                    case 0x72: out.append(0x0D)
                    case 0x74: out.append(0x09)
                    case 0x75: out.append(try hex4())
                    default: throw fail("bad escape")
                    }
                } else {
                    guard c >= 0x20 else { throw fail("control character in string") }
                    out.append(c)
                }
                guard out.count <= 1_000_000 else { throw fail("string too long") }
            }
        }

        mutating func arr(_ d: Int) throws -> JSONValue {
            i += 1
            var out: [JSONValue] = []
            ws()
            guard i < s.count else { throw fail("unexpected end") }
            if s[i] == 0x5D { i += 1; return .array(out) }
            while true {
                out.append(try value(d + 1)); ws()
                guard i < s.count else { throw fail("unexpected end") }
                let c = s[i]; i += 1
                if c == 0x2C { continue }
                if c == 0x5D { return .array(out) }
                throw fail("bad array")
            }
        }

        mutating func obj(_ d: Int) throws -> JSONValue {
            i += 1
            var out = JSONObject()
            ws()
            guard i < s.count else { throw fail("unexpected end") }
            if s[i] == 0x7D { i += 1; return .object(out) }
            while true {
                ws()
                guard i < s.count, s[i] == Parser.quote else { throw fail("bad key") }
                let k = try str(); ws()
                guard i < s.count, s[i] == 0x3A else { throw fail("missing colon") }
                i += 1
                let v = try value(d + 1)
                guard out.insert(k, v) else { throw fail("duplicate key") }
                ws()
                guard i < s.count else { throw fail("unexpected end") }
                let c = s[i]; i += 1
                if c == 0x2C { continue }
                if c == 0x7D { return .object(out) }
                throw fail("bad object")
            }
        }
    }
}
