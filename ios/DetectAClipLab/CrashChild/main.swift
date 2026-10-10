// Test helper for PackStoreTests (not shipped): opens the store at argv[1], then installs the
// golden "version_numeric_order_2_10_over_2_9" pack with an I/O layer that terminates this
// process with _exit(77) at I/O step argv[2], either before the step ("halt") or after writing
// half of a file without fsync ("torn"). argv[3] = golden_manifest_cases.txt, argv[4] = mode.
import Foundation
import DetectAClipCore
#if canImport(Darwin)
import Darwin
#elseif canImport(Glibc)
import Glibc
#endif

final class HaltingIO: PackStoreIO {
    private let inner = DurablePackStoreIO()
    private let at: Int, mode: String
    private var calls = 0
    init(at: Int, mode: String) { self.at = at; self.mode = mode }
    private func step(torn: (() -> Void)? = nil) {
        calls += 1
        guard calls == at else { return }
        if mode == "torn" { torn?() }
        _exit(77)
    }
    func writeBytes(_ url: URL, _ data: [UInt8]) throws {
        step { FileManager.default.createFile(atPath: url.path, contents: Data(data.prefix(data.count / 2))) }
        try inner.writeBytes(url, data)
    }
    func replace(_ src: URL, _ dst: URL) throws { step(); try inner.replace(src, dst) }
    func rmtree(_ url: URL) { step(); inner.rmtree(url) }
    func mkdir(_ url: URL) throws { step(); try inner.mkdir(url) }
}

func hex(_ s: Substring) -> [UInt8] {
    let u = Array(s.utf8)
    func v(_ c: UInt8) -> UInt8 { c <= 57 ? c - 48 : (c | 0x20) - 87 }
    return stride(from: 0, to: u.count - 1, by: 2).map { v(u[$0]) << 4 | v(u[$0 + 1]) }
}

let args = CommandLine.arguments
guard args.count == 5, let at = Int(args[2]) else { fputs("usage: root step golden mode\n", stderr); exit(2) }
let lines = try String(contentsOfFile: args[3], encoding: .utf8).split(separator: "\n")
let pub = lines.first { $0.hasPrefix("PUBKEY ") }!.split(separator: " ")
var payloads: [Substring: [UInt8]] = [:]
for l in lines where l.hasPrefix("PAYLOAD ") { let p = l.split(separator: " "); payloads[p[1]] = hex(p[2]) }
let caseLine = lines.first { $0.hasPrefix("CASE version_numeric_order_2_10_over_2_9 ") }!
var kv: [Substring: Substring] = [:]
for item in caseLine.split(separator: " ").dropFirst(3) {
    let eq = item.firstIndex(of: "=")!
    kv[item[..<eq]] = item[item.index(after: eq)...]
}
let rights = PackLoader.DeviceRightsState()
rights.trustedKeys[String(pub[1])] = hex(pub[2])
let store = try PackStore(root: URL(fileURLWithPath: args[1]), rights: rights, io: HaltingIO(at: at, mode: args[4]))
try store.install(manifest: hex(kv["manifest"]!), signature: hex(kv["sig"]!), payload: payloads[kv["payload"]!]!,
                  now: PackLoader.parseInstant(.string("2026-10-10T12:00:00+00:00"), "now"))
exit(0)
