// Installed pack store (P03-T06, IDX-01, RIGHTS-02): Swift port of android PackStore.kt and
// l0/dac_l0/pack/store.py for manifest V2 packs. Same layout and state.json shape:
//   staging/<pack_id>.<nonce>/   payload.pack + manifest.json + manifest.sig being validated
//   packs/<pack_id>/<slot>/      immutable slot
//   state.json                   COMMIT POINT (atomic replace)
//   floors.json                  epoch/version floors, merged by maximum (never lowered)
// Startup recovery deletes staging leftovers, temp files and unreferenced slots and fails closed
// when state.json names a missing slot; active() re-verifies through PackLoader on every load.
// Recovery after abrupt termination is tested by halting a child process (DACStoreCrashChild)
// at every I/O step. iOS file-protection/durability semantics are a device check (B-02).
// Status: compiled and tested by the swift-core CI job (macOS).
import Foundation

public protocol PackStoreIO: AnyObject {
    func writeBytes(_ url: URL, _ data: [UInt8]) throws
    func replace(_ src: URL, _ dst: URL) throws
    func rmtree(_ url: URL)
    func mkdir(_ url: URL) throws
}

/// fsync'd writes and rename(2) replaces (atomic on one volume).
public final class DurablePackStoreIO: PackStoreIO {
    public init() {}
    public func writeBytes(_ url: URL, _ data: [UInt8]) throws {
        let fd = open(url.path, O_WRONLY | O_CREAT | O_TRUNC, 0o600)
        guard fd >= 0 else { throw PackStore.StoreError(message: "open failed: \(url.lastPathComponent)") }
        defer { close(fd) }
        var off = 0
        while off < data.count {
            let n = data[off...].withUnsafeBytes { write(fd, $0.baseAddress, $0.count) }
            guard n > 0 else { throw PackStore.StoreError(message: "write failed: \(url.lastPathComponent)") }
            off += n
        }
        guard fsync(fd) == 0 else { throw PackStore.StoreError(message: "fsync failed: \(url.lastPathComponent)") }
    }
    public func replace(_ src: URL, _ dst: URL) throws {
        guard rename(src.path, dst.path) == 0 else { throw PackStore.StoreError(message: "rename failed: \(src.lastPathComponent)") }
    }
    public func rmtree(_ url: URL) { try? FileManager.default.removeItem(at: url) }
    public func mkdir(_ url: URL) throws { try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true) }
}

public final class PackStore {
    public struct StoreError: Error, Equatable { public let message: String }
    public struct Entry: Equatable { public let slot: String, version: String; public let bytes: Int64 }
    public struct State: Equatable {
        public let epoch: Int64
        public let packs: [String: Entry]
        public let floors: [String: PackVersion]
    }

    public static let stateFile = "state.json", floorsFile = "floors.json"
    public static let payloadFile = "payload.pack", manifestFile = "manifest.json", signatureFile = "manifest.sig"
    static let slotFiles = [payloadFile, manifestFile, signatureFile]

    private let root: URL
    private let rights: PackLoader.DeviceRightsState
    private let io: PackStoreIO
    private let budgetBytes: Int64
    private let stagingCapBytes: Int64
    private let fm = FileManager.default
    public private(set) var state: State
    public private(set) var recoveryActions: [String] = []

    public init(root: URL, rights: PackLoader.DeviceRightsState, io: PackStoreIO = DurablePackStoreIO(),
                budgetBytes: Int64 = PackLoader.defaultBudget, stagingCapBytes: Int64? = nil) throws {
        self.root = root; self.rights = rights; self.io = io
        self.budgetBytes = budgetBytes; self.stagingCapBytes = stagingCapBytes ?? budgetBytes
        try fm.createDirectory(at: root.appendingPathComponent("staging"), withIntermediateDirectories: true)
        try fm.createDirectory(at: root.appendingPathComponent("packs"), withIntermediateDirectories: true)
        state = State(epoch: 0, packs: [:], floors: [:])
        state = try loadState()
        recoveryActions = try recover()
        syncRights()
    }

    // MARK: state

    private func children(_ url: URL) -> [URL] {
        ((try? fm.contentsOfDirectory(at: url, includingPropertiesForKeys: nil)) ?? []).sorted { $0.lastPathComponent < $1.lastPathComponent }
    }

    private func loadState() throws -> State {
        var st = State(epoch: 0, packs: [:], floors: [:])
        let p = root.appendingPathComponent(PackStore.stateFile)
        if fm.fileExists(atPath: p.path) {
            guard let d = fm.contents(atPath: p.path), let parsed = try? PackStore.parseState([UInt8](d)) else {
                throw StoreError(message: "state file corrupt; refusing to guess (revalidation required)")
            }
            st = parsed
        }
        let f = root.appendingPathComponent(PackStore.floorsFile)
        if fm.fileExists(atPath: f.path) {
            guard let d = fm.contents(atPath: f.path), let text = String(data: d, encoding: .utf8),
                  let m = (try? MiniJson.parse(text))?.object, let e = m["minimum_rights_epoch"]?.int,
                  let fl = m["minimum_pack_versions"]?.object else { throw StoreError(message: "floors file corrupt") }
            var floors = st.floors
            for k in fl.keys {
                guard let v = PackStore.version(fl[k]) else { throw StoreError(message: "floors file corrupt") }
                floors[k] = PackStore.maxVersion(floors[k], v)
            }
            st = State(epoch: max(st.epoch, e), packs: st.packs, floors: floors)
        }
        return st
    }

    private func recover() throws -> [String] {
        var actions: [String] = []
        for d in children(root.appendingPathComponent("staging")) { io.rmtree(d); actions.append("removed staging \(d.lastPathComponent)") }
        for name in [PackStore.stateFile + ".tmp", PackStore.floorsFile + ".tmp"] {
            let t = root.appendingPathComponent(name)
            if fm.fileExists(atPath: t.path) { try? fm.removeItem(at: t); actions.append("removed \(name)") }
        }
        for packDir in children(root.appendingPathComponent("packs")) {
            let ref = state.packs[packDir.lastPathComponent]?.slot
            for slot in children(packDir) where slot.lastPathComponent != ref {
                io.rmtree(slot); actions.append("removed unreferenced slot \(packDir.lastPathComponent)/\(slot.lastPathComponent)")
            }
            if ref == nil && children(packDir).isEmpty { try? fm.removeItem(at: packDir) }
        }
        for (pid, e) in state.packs {
            let slot = root.appendingPathComponent("packs").appendingPathComponent(pid).appendingPathComponent(e.slot)
            if PackStore.slotFiles.contains(where: { !fm.fileExists(atPath: slot.appendingPathComponent($0).path) }) {
                throw StoreError(message: "state references a missing slot for \(pid); revalidation required")
            }
        }
        return actions
    }

    /// Device rights state is derived from persisted state, never the other way round.
    private func syncRights() {
        rights.minimumRightsEpoch = max(rights.minimumRightsEpoch, state.epoch)
        rights.installedIndexBytes = state.packs.mapValues { $0.bytes }
        for (k, v) in state.floors { rights.minimumPackVersions[k] = PackStore.maxVersion(rights.minimumPackVersions[k], v) }
    }

    private func scratchRights(excluding packId: String) -> PackLoader.DeviceRightsState {
        let s = PackLoader.DeviceRightsState()
        s.minimumRightsEpoch = rights.minimumRightsEpoch
        s.installedIndexBytes = rights.installedIndexBytes.filter { $0.key != packId }
        s.minimumPackVersions = rights.minimumPackVersions
        s.acceptedRegionMethods = rights.acceptedRegionMethods
        s.trustedKeys = rights.trustedKeys
        s.revokedKeyIds = rights.revokedKeyIds
        return s
    }

    private func commit(_ st: State) throws {
        let tmp = root.appendingPathComponent(PackStore.stateFile + ".tmp")
        try io.writeBytes(tmp, PackStore.stateJson(st))
        try io.replace(tmp, root.appendingPathComponent(PackStore.stateFile))      // <- the commit point
        let ftmp = root.appendingPathComponent(PackStore.floorsFile + ".tmp")
        try io.writeBytes(ftmp, PackStore.floorsJson(st))
        try io.replace(ftmp, root.appendingPathComponent(PackStore.floorsFile))
    }

    private func read(_ url: URL) throws -> [UInt8] {
        guard let d = fm.contents(atPath: url.path) else { throw StoreError(message: "unreadable \(url.lastPathComponent)") }
        return [UInt8](d)
    }

    // MARK: install / load

    @discardableResult
    public func install(manifest: [UInt8], signature: [UInt8], payload: [UInt8], now: PackInstant?, releaseMode: Bool = false) throws -> PackLoader.Loaded {
        guard Int64(payload.count + manifest.count + signature.count) <= stagingCapBytes else { throw PackLoader.Rejected(reason: "staging cap exceeded") }
        guard let text = String(data: Data(manifest), encoding: .utf8), let m = (try? MiniJson.parse(text))?.object,
              let packId = m["pack_id"]?.string else { throw PackLoader.Rejected(reason: "manifest not readable") }
        guard PackLoader.isPackId(packId) else { throw PackLoader.Rejected(reason: "bad pack_id") }
        let stage = root.appendingPathComponent("staging").appendingPathComponent("\(packId).\(PackStore.hex(4))")
        try io.mkdir(stage)
        defer { if fm.fileExists(atPath: stage.path) { io.rmtree(stage) } }
        try io.writeBytes(stage.appendingPathComponent(PackStore.payloadFile), payload)
        try io.writeBytes(stage.appendingPathComponent(PackStore.manifestFile), manifest)
        try io.writeBytes(stage.appendingPathComponent(PackStore.signatureFile), signature)
        // Validate exactly what was written, against a scratch copy of the rights state.
        let loaded = try PackLoader(state: scratchRights(excluding: packId)).load(
            manifest: read(stage.appendingPathComponent(PackStore.manifestFile)),
            signature: read(stage.appendingPathComponent(PackStore.signatureFile)),
            payload: read(stage.appendingPathComponent(PackStore.payloadFile)), now: now, releaseMode: releaseMode, budgetBytes: budgetBytes)
        let slot = PackStore.hex(8)
        let packDir = root.appendingPathComponent("packs").appendingPathComponent(packId)
        try fm.createDirectory(at: packDir, withIntermediateDirectories: true)
        try io.replace(stage, packDir.appendingPathComponent(slot))                 // new immutable slot
        let declaredMin = try PackLoader.parseVersion(loaded.manifest["minimum_allowed_version"], "minimum_allowed_version")
        var packs = state.packs; packs[packId] = Entry(slot: slot, version: loaded.manifest["pack_version"]!.string!, bytes: Int64(payload.count))
        var floors = state.floors; floors[packId] = PackStore.maxVersion(floors[packId], declaredMin)
        let newState = State(epoch: max(state.epoch, loaded.manifest["rights_epoch"]!.int!), packs: packs, floors: floors)
        do {
            try commit(newState)
        } catch {
            // Not committed (or committed without floors): resolve from state.json alone.
            state = try loadState(); _ = try recover(); syncRights()
            throw error
        }
        state = newState
        _ = try recover()                  // drop the previous slot now that state.json no longer names it
        syncRights()
        return loaded
    }

    /// Re-verifies the referenced slot on every load. `now` nil means time is not trustworthy.
    public func active(_ packId: String, now: PackInstant?) throws -> PackLoader.Loaded {
        guard let e = state.packs[packId] else { throw StoreError(message: "no active pack") }
        let d = root.appendingPathComponent("packs").appendingPathComponent(packId).appendingPathComponent(e.slot)
        return try PackLoader(state: scratchRights(excluding: packId)).load(
            manifest: read(d.appendingPathComponent(PackStore.manifestFile)), signature: read(d.appendingPathComponent(PackStore.signatureFile)),
            payload: read(d.appendingPathComponent(PackStore.payloadFile)), now: now, releaseMode: false, budgetBytes: budgetBytes)
    }

    // MARK: serialisation (same shape as Python/Kotlin; IDs, slots and versions are validated ASCII)

    static func hex(_ n: Int) -> String {
        var g = SystemRandomNumberGenerator()
        return (0..<n).map { _ in String(format: "%02x", UInt8.random(in: 0...255, using: &g)) }.joined()
    }

    static func maxVersion(_ a: PackVersion?, _ b: PackVersion) -> PackVersion {
        guard let a else { return b }
        return b > a ? b : a
    }

    static func version(_ v: JSONValue?) -> PackVersion? {
        guard let l = v?.array, l.count == 3, let a = l[0].int, let b = l[1].int, let c = l[2].int, a >= 0, b >= 0, c >= 0 else { return nil }
        return PackVersion(major: a, minor: b, patch: c)
    }

    static func isSlot(_ s: String) -> Bool { s.utf8.count == 16 && s.utf8.allSatisfy { ($0 >= 48 && $0 <= 57) || ($0 >= 97 && $0 <= 102) } }

    public static func parseState(_ b: [UInt8]) throws -> State {
        guard let text = String(data: Data(b), encoding: .utf8), let m = try MiniJson.parse(text).object,
              m["format"]?.string == "store-v2", let epoch = m["minimum_rights_epoch"]?.int, epoch >= 0,
              let packsObj = m["packs"]?.object, let floorsObj = m["minimum_pack_versions"]?.object else {
            throw StoreError(message: "bad state")
        }
        var packs: [String: Entry] = [:]
        for k in packsObj.keys {
            guard let e = packsObj[k]?.object, let slot = e["slot"]?.string, let ver = e["version"]?.string, let bytes = e["bytes"]?.int,
                  PackLoader.isPackId(k), isSlot(slot), (try? PackLoader.parseVersion(.string(ver), "version")) != nil, bytes >= 0 else {
                throw StoreError(message: "bad pack entry")
            }
            packs[k] = Entry(slot: slot, version: ver, bytes: bytes)
        }
        var floors: [String: PackVersion] = [:]
        for k in floorsObj.keys {
            guard let v = version(floorsObj[k]) else { throw StoreError(message: "bad version floor") }
            floors[k] = v
        }
        return State(epoch: epoch, packs: packs, floors: floors)
    }

    static func floorsMap(_ st: State) -> String {
        "{" + st.floors.keys.sorted().map { k -> String in
            let v = st.floors[k]!
            return "\"\(k)\":[\(v.major),\(v.minor),\(v.patch)]"
        }.joined(separator: ",") + "}"
    }

    public static func stateJson(_ st: State) -> [UInt8] {
        let packs = "{" + st.packs.keys.sorted().map { k -> String in
            let e = st.packs[k]!
            return "\"\(k)\":{\"bytes\":\(e.bytes),\"slot\":\"\(e.slot)\",\"version\":\"\(e.version)\"}"
        }.joined(separator: ",") + "}"
        let s = "{\"format\":\"store-v2\",\"minimum_pack_versions\":\(floorsMap(st)),\"minimum_rights_epoch\":\(st.epoch),\"packs\":\(packs)}"
        return Array(s.utf8)
    }

    public static func floorsJson(_ st: State) -> [UInt8] {
        Array("{\"minimum_pack_versions\":\(floorsMap(st)),\"minimum_rights_epoch\":\(st.epoch)}".utf8)
    }
}
