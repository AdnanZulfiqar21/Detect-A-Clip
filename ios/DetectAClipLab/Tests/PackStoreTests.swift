// Installed pack store, mirroring android PackStoreTest.kt: persistence and re-verification,
// rejected packs leave everything unchanged, rollback floors, restored state cannot lower
// floors, corrupt/dangling state fails closed, injected I/O failures, and a child process
// halted (_exit) before or mid-write at every I/O step recovers to exactly the old or new pack.
import XCTest
@testable import DetectAClipCore

private final class ThrowingIO: PackStoreIO {
    struct Injected: Error {}
    private let inner = DurablePackStoreIO()
    private let at: Int
    private var calls = 0
    init(at: Int) { self.at = at }
    private func step() throws { calls += 1; if calls == at { throw Injected() } }
    func writeBytes(_ url: URL, _ data: [UInt8]) throws { try step(); try inner.writeBytes(url, data) }
    func replace(_ src: URL, _ dst: URL) throws { try step(); try inner.replace(src, dst) }
    func rmtree(_ url: URL) { inner.rmtree(url) }                       // non-throwing in the protocol
    func mkdir(_ url: URL) throws { try step(); try inner.mkdir(url) }
}

final class PackStoreTests: XCTestCase {
    private var packs: [String: (manifest: [UInt8], sig: [UInt8], payload: [UInt8])] = [:]
    private var pubId = "", pub: [UInt8] = []
    private var now: PackInstant!

    override func setUpWithError() throws {
        let lines = try Golden.lines("golden_manifest_cases.txt")
        let p = lines.first { $0.hasPrefix("PUBKEY ") }!.split(separator: " ")
        pubId = String(p[1]); pub = Golden.hex(p[2])
        var payloads: [String: [UInt8]] = [:]
        for l in lines where l.hasPrefix("PAYLOAD ") { let q = l.split(separator: " "); payloads[String(q[1])] = Golden.hex(q[2]) }
        for l in lines where l.hasPrefix("CASE ") {
            let q = l.split(separator: " ")
            var kv: [String: String] = [:]
            for item in q.dropFirst(3) { let eq = item.firstIndex(of: "=")!; kv[String(item[..<eq])] = String(item[item.index(after: eq)...]) }
            packs[String(q[1])] = (Golden.hex(kv["manifest"]!), Golden.hex(kv["sig"]!), payloads[kv["payload"]!]!)
        }
        now = try PackLoader.parseInstant(.string("2026-10-10T12:00:00+00:00"), "now")
    }

    private func rights() -> PackLoader.DeviceRightsState {
        let r = PackLoader.DeviceRightsState(); r.trustedKeys[pubId] = pub; return r
    }
    private func tmp() throws -> URL {
        let u = FileManager.default.temporaryDirectory.appendingPathComponent("dac-store-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: u, withIntermediateDirectories: true)
        return u
    }
    @discardableResult private func install(_ s: PackStore, _ name: String) throws -> PackLoader.Loaded {
        let p = packs[name]!
        return try s.install(manifest: p.manifest, signature: p.sig, payload: p.payload, now: now)
    }
    private func tree(_ root: URL) -> [String] {
        let e = FileManager.default.enumerator(at: root, includingPropertiesForKeys: [.isRegularFileKey])!
        var out: [String] = []
        for case let u as URL in e where (try? u.resourceValues(forKeys: [.isRegularFileKey]).isRegularFile) == true {
            let base = root.resolvingSymlinksInPath().path
            out.append(String(u.resolvingSymlinksInPath().path.dropFirst(base.count + 1)))
        }
        return out.sorted()
    }
    private func slotCount(_ root: URL) -> Int {
        (try? FileManager.default.contentsOfDirectory(atPath: root.appendingPathComponent("packs/L0-E2E").path).count) ?? -1
    }

    func testInstallPersistsAndReopenReVerifies() throws {
        let root = try tmp()
        try install(PackStore(root: root, rights: rights()), "valid_dev_no_expiry")
        let again = try PackStore(root: root, rights: rights())
        XCTAssertEqual(again.state.packs["L0-E2E"]?.version, "1.0.0")
        XCTAssertEqual(try again.active("L0-E2E", now: now).manifest["pack_id"]?.string, "L0-E2E")
        XCTAssertEqual(try again.active("L0-E2E", now: nil).manifest["pack_id"]?.string, "L0-E2E")
        XCTAssertTrue(again.recoveryActions.isEmpty)
    }

    func testRejectedPackLeavesStateAndFilesUnchanged() throws {
        let root = try tmp()
        let r = rights()
        let s = try PackStore(root: root, rights: r)
        try install(s, "valid_dev_no_expiry")
        let before = tree(root), stateBefore = s.state, bytesBefore = r.installedIndexBytes
        for bad in ["bad_signature_bit", "future_valid_from", "below_declared_minimum", "payload_hash_mismatch", "duplicate_json_key"] {
            XCTAssertThrowsError(try install(s, bad), bad) { XCTAssertTrue($0 is PackLoader.Rejected, bad) }
            XCTAssertEqual(tree(root), before, bad)
            XCTAssertEqual(s.state, stateBefore, bad)
            XCTAssertEqual(r.installedIndexBytes, bytesBefore, bad)
        }
    }

    func testUpgradeReplacesSlotAndFloorBlocksRollback() throws {
        let root = try tmp()
        let s = try PackStore(root: root, rights: rights())
        try install(s, "valid_dev_no_expiry")
        let oldSlot = s.state.packs["L0-E2E"]!.slot
        try install(s, "version_numeric_order_2_10_over_2_9")
        XCTAssertEqual(s.state.packs["L0-E2E"]?.version, "2.10.0")
        XCTAssertNotEqual(s.state.packs["L0-E2E"]?.slot, oldSlot)
        XCTAssertFalse(FileManager.default.fileExists(atPath: root.appendingPathComponent("packs/L0-E2E/\(oldSlot)").path))
        XCTAssertEqual(s.state.floors["L0-E2E"], PackVersion(major: 2, minor: 0, patch: 0))
        XCTAssertThrowsError(try install(s, "valid_dev_no_expiry"))
        XCTAssertEqual(s.state.packs["L0-E2E"]?.version, "2.10.0")
    }

    func testRestoredOldStateCannotLowerFloors() throws {
        let root = try tmp()
        let s = try PackStore(root: root, rights: rights())
        try install(s, "valid_dev_no_expiry")
        let statePath = root.appendingPathComponent(PackStore.stateFile)
        let oldState = try Data(contentsOf: statePath)
        let oldSlot = s.state.packs["L0-E2E"]!.slot
        let slotDir = root.appendingPathComponent("packs/L0-E2E/\(oldSlot)")
        var files: [String: Data] = [:]
        for f in [PackStore.payloadFile, PackStore.manifestFile, PackStore.signatureFile] { files[f] = try Data(contentsOf: slotDir.appendingPathComponent(f)) }
        try install(s, "version_numeric_order_2_10_over_2_9")
        try oldState.write(to: statePath)
        try FileManager.default.createDirectory(at: slotDir, withIntermediateDirectories: true)
        for (f, d) in files { try d.write(to: slotDir.appendingPathComponent(f)) }
        let r = rights()
        let restored = try PackStore(root: root, rights: r)
        XCTAssertEqual(r.minimumPackVersions["L0-E2E"], PackVersion(major: 2, minor: 0, patch: 0))
        XCTAssertThrowsError(try restored.active("L0-E2E", now: now))
    }

    /// SEC-03: a signer revoked after installation stops the installed pack from activating.
    func testRevokedSignerBlocksActivationOfAnInstalledPack() throws {
        let root = try tmp()
        try install(PackStore(root: root, rights: rights()), "valid_dev_no_expiry")
        let r = rights(); r.revokedKeyIds.insert(pubId)
        XCTAssertThrowsError(try PackStore(root: root, rights: r).active("L0-E2E", now: now))
        let t = rights(); t.trustedKeys = [:]
        XCTAssertThrowsError(try PackStore(root: root, rights: t).active("L0-E2E", now: now))
    }

    func testCorruptOrDanglingStateFailsClosed() throws {
        let root = try tmp()
        try install(PackStore(root: root, rights: rights()), "valid_dev_no_expiry")
        let statePath = root.appendingPathComponent(PackStore.stateFile)
        let good = try Data(contentsOf: statePath)
        try Data("{\"format\":\"store-v2\"".utf8).write(to: statePath)
        XCTAssertThrowsError(try PackStore(root: root, rights: rights()))
        try good.write(to: statePath)
        let slot = try PackStore.parseState([UInt8](good)).packs["L0-E2E"]!.slot
        try FileManager.default.removeItem(at: root.appendingPathComponent("packs/L0-E2E/\(slot)/\(PackStore.payloadFile)"))
        XCTAssertThrowsError(try PackStore(root: root, rights: rights()))
    }

    func testInjectedIOFailureAtEveryStepLeavesOldOrNewPack() throws {
        var at = 1
        while true {
            let root = try tmp()
            try install(PackStore(root: root, rights: rights()), "valid_dev_no_expiry")
            let s = try PackStore(root: root, rights: rights(), io: ThrowingIO(at: at))
            var failed = false
            do { try install(s, "version_numeric_order_2_10_over_2_9") } catch is ThrowingIO.Injected { failed = true }
            let r = try PackStore(root: root, rights: rights())
            let v = r.state.packs["L0-E2E"]?.version
            XCTAssertTrue(v == "1.0.0" || v == "2.10.0", "step \(at): \(String(describing: v))")
            XCTAssertNoThrow(try r.active("L0-E2E", now: now))
            XCTAssertEqual(slotCount(root), 1, "step \(at)")
            if !failed { break }
            at += 1
            XCTAssertLessThan(at, 60)
            if at >= 60 { break }
        }
        XCTAssertGreaterThan(at, 5)
    }

    func testHaltedProcessAtEveryStepRecoversToOldOrNewPack() throws {
        #if os(macOS) || os(Linux)
        let child = Bundle(for: PackStoreTests.self).bundleURL.deletingLastPathComponent().appendingPathComponent("DACStoreCrashChild")
        guard FileManager.default.isExecutableFile(atPath: child.path) else { XCTFail("crash child not built at \(child.path)"); return }
        var seen = Set<String>()
        for mode in ["halt", "torn"] {
            var at = 1
            while true {
                let root = try tmp()
                try install(PackStore(root: root, rights: rights()), "valid_dev_no_expiry")
                let p = Process()
                p.executableURL = child
                p.arguments = [root.path, String(at), Golden.url("golden_manifest_cases.txt").path, mode]
                let pipe = Pipe(); p.standardOutput = pipe; p.standardError = pipe
                try p.run(); p.waitUntilExit()
                let out = String(decoding: pipe.fileHandleForReading.readDataToEndOfFile(), as: UTF8.self)
                let code = p.terminationStatus
                XCTAssertTrue(code == 77 || code == 0, "\(mode)/\(at) exited \(code): \(out)")
                let r = try PackStore(root: root, rights: rights())
                let v = r.state.packs["L0-E2E"]?.version ?? "none"
                XCTAssertTrue(v == "1.0.0" || v == "2.10.0", "\(mode)/\(at): \(v)")
                seen.insert(v)
                XCTAssertNoThrow(try r.active("L0-E2E", now: now))
                XCTAssertEqual(tree(root).filter { $0.hasPrefix("staging/") || $0.hasSuffix(".tmp") }, [], "\(mode)/\(at)")
                XCTAssertEqual(slotCount(root), 1, "\(mode)/\(at)")
                if code == 0 || code != 77 { break }
                at += 1
                if at >= 60 { XCTFail("runaway"); break }
            }
        }
        XCTAssertEqual(seen, ["1.0.0", "2.10.0"])
        #else
        throw XCTSkip("no child processes on this platform")
        #endif
    }
}
