// Swift port of android PackLoader.kt / l0/dac_l0/pack/loader.py for manifest V2 packs
// (detached Ed25519 signature over the exact manifest bytes). Checked case by case against
// golden_manifest_cases.txt (ManifestContractTests). Device state changes only after every
// check passed. CryptoKit is required; without it (non-Apple toolchains) loading fails closed.
// Status: compiled and tested by the swift-core CI job (macOS, Swift 6.3.3; first pass at 3f77273) (docs/TEST_EVIDENCE.md).
import Foundation
#if canImport(CryptoKit)
import CryptoKit
#endif

public struct PackVersion: Comparable, Hashable {
    public let major: Int64, minor: Int64, patch: Int64
    public static func < (a: PackVersion, b: PackVersion) -> Bool { (a.major, a.minor, a.patch) < (b.major, b.minor, b.patch) }
}

/// An instant with an explicit offset, reduced to UTC microseconds.
public struct PackInstant: Comparable, Hashable {
    public let utcMicros: Int64
    public static func < (a: PackInstant, b: PackInstant) -> Bool { a.utcMicros < b.utcMicros }
}

public final class PackLoader {
    public struct Rejected: Error, Equatable { public let reason: String }

    /// Persistent-by-design rights state: epochs, version floors, installed bytes, keys.
    public final class DeviceRightsState {
        public var minimumRightsEpoch: Int64 = 0
        public var installedIndexBytes: [String: Int64] = [:]
        public var minimumPackVersions: [String: PackVersion] = [:]
        public var acceptedRegionMethods: Set<String> = ["NONE"]
        public var trustedKeys: [String: [UInt8]] = [:]    // key id -> raw 32-byte Ed25519 public key
        public var revokedKeyIds: Set<String> = []
        public init() {}
        func totalInstalled(excluding packId: String) -> Int64 { installedIndexBytes.filter { $0.key != packId }.values.reduce(0, +) }
    }

    public struct Loaded { public let manifest: JSONObject; public let index: PackIndex }

    public static let manifestV2 = "L0_DEV_INTEGRITY_MANIFEST_V2"
    public static let l0GrantId = "GRANT-L0-SELF-SYNTH-001"
    public static let maxManifestBytes = 64 * 1024
    public static let defaultBudget: Int64 = 250_000_000
    static let keys: Set<String> = [
        "pack_id", "pack_version", "payload_sha256", "payload_size_bytes", "generator_version",
        "preprocessing_version", "index_format_version", "calibration_version", "calibration_status",
        "rights_epoch", "valid_from", "valid_until", "signed_time_basis", "key_id", "tombstones",
        "minimum_allowed_version", "region_grants", "operation_grants", "region_assurance_method",
        "indexed_hours", "title_count", "descriptor_bytes", "sampling_interval_s", "descriptor_family",
        "vector_count", "grant_id", "manifest_type",
    ]
    static let calibration: Set<String> = ["UNCALIBRATED", "CALIBRATED_L0_SYNTHETIC", "CALIBRATED"]
    static let acts: Set<String> = ["INGEST_REFERENCE", "BUILD_INDEX", "LOCAL_DISTRIBUTION", "TRANSIENT_QUERY", "DECISION",
                                    "DISPLAY_METADATA", "DISPLAY_STILL", "DERIVATIVE_DESCRIPTOR", "EVALUATION", "TRAINING"]
    static let regionMethods: Set<String> = ["NONE", "STORE_COUNTRY_ATTESTATION", "ONLINE_ACTIVATION", "COARSE_LOCATION"]

    private let state: DeviceRightsState
    public init(state: DeviceRightsState) { self.state = state }

    static func reject(_ m: String) -> Rejected { Rejected(reason: m) }

    /// ^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$
    static func isPackId(_ s: String) -> Bool {
        let b = Array(s.utf8)
        return (1...64).contains(b.count) && Ascii.alnum(b[0]) && b.dropFirst().allSatisfy { Ascii.alnum($0) || $0 == 95 || $0 == 45 }
    }

    /// MAJOR.MINOR.PATCH, each 0 or [1-9][0-9]{0,8}; ASCII digits only.
    public static func parseVersion(_ v: JSONValue?, _ what: String) throws -> PackVersion {
        guard let s = v?.string else { throw reject("\(what) malformed") }
        let parts: [[UInt8]] = s.utf8.split(separator: 46, omittingEmptySubsequences: false).map { Array($0) }
        guard parts.count == 3 else { throw reject("\(what) malformed") }
        var n: [Int64] = []
        for p in parts {
            guard (1...9).contains(p.count), p.allSatisfy({ $0 >= 48 && $0 <= 57 }), p.count == 1 || p[0] != 48 else { throw reject("\(what) malformed") }
            n.append(p.reduce(Int64(0)) { $0 * 10 + Int64($1 - 48) })
        }
        return PackVersion(major: n[0], minor: n[1], patch: n[2])
    }

    /// YYYY-MM-DDTHH:MM:SS[.f{1,6}](Z|+HH:MM|-HH:MM); proleptic Gregorian, year >= 1, no leap
    /// second, |offset| <= 18:00 and offset minutes <= 59 (java.time and Python agree on this).
    public static func parseInstant(_ v: JSONValue?, _ what: String) throws -> PackInstant {
        guard let s = v?.string else { throw reject("\(what) malformed or missing") }
        let b = Array(s.utf8)
        func digits(_ at: Int, _ n: Int) -> Int64? {
            guard at + n <= b.count else { return nil }
            var x: Int64 = 0
            for k in at..<(at + n) { guard b[k] >= 48 && b[k] <= 57 else { return nil }; x = x * 10 + Int64(b[k] - 48) }
            return x
        }
        func bad() -> Rejected { reject("\(what) malformed or missing") }
        guard b.count >= 20, b[4] == 45, b[7] == 45, b[10] == 84, b[13] == 58, b[16] == 58,
              let year = digits(0, 4), let month = digits(5, 2), let day = digits(8, 2),
              let hour = digits(11, 2), let minute = digits(14, 2), let second = digits(17, 2) else { throw bad() }
        var i = 19
        var micros: Int64 = 0
        if i < b.count && b[i] == 46 {
            i += 1
            let st = i
            while i < b.count && b[i] >= 48 && b[i] <= 57 { i += 1 }
            let n = i - st
            guard (1...6).contains(n), let f = digits(st, n) else { throw bad() }
            micros = f * Int64([1, 100_000, 10_000, 1_000, 100, 10, 1][n])
        }
        var offsetMin: Int64 = 0
        guard i < b.count else { throw bad() }
        if b[i] == 90 {                                       // Z
            i += 1
        } else if b[i] == 43 || b[i] == 45 {                  // + or -
            guard i + 6 == b.count, b[i + 3] == 58, let oh = digits(i + 1, 2), let om = digits(i + 4, 2) else { throw bad() }
            guard om <= 59, oh * 60 + om <= 18 * 60 else { throw bad() }
            offsetMin = (b[i] == 45 ? -1 : 1) * (oh * 60 + om)
            i += 6
        } else { throw bad() }
        guard i == b.count else { throw bad() }
        let leap = (year % 4 == 0 && year % 100 != 0) || year % 400 == 0
        let mdays: [Int64] = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
        guard year >= 1, (1...12).contains(month), day >= 1, day <= mdays[Int(month - 1)],
              hour <= 23, minute <= 59, second <= 59 else { throw bad() }
        // days from civil (H. Hinnant), proleptic Gregorian
        let y = month <= 2 ? year - 1 : year
        let era = (y >= 0 ? y : y - 399) / 400
        let yoe = y - era * 400
        let mp = (month + 9) % 12
        let doy = (153 * mp + 2) / 5 + day - 1
        let doe = yoe * 365 + yoe / 4 - yoe / 100 + doy
        let days = era * 146_097 + doe - 719_468
        let secs = days * 86_400 + hour * 3_600 + minute * 60 + second - offsetMin * 60
        return PackInstant(utcMicros: secs * 1_000_000 + micros)
    }

    public static func verifyEd25519(publicKey: [UInt8], message: [UInt8], signature: [UInt8]) -> Bool {
        guard publicKey.count == 32, signature.count == 64 else { return false }
        #if canImport(CryptoKit)
        guard let k = try? Curve25519.Signing.PublicKey(rawRepresentation: publicKey) else { return false }
        return k.isValidSignature(signature, for: message)
        #else
        return false
        #endif
    }

    static func sha256Hex(_ data: [UInt8]) -> String? {
        #if canImport(CryptoKit)
        return SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
        #else
        return nil
        #endif
    }

    private func str(_ m: JSONObject, _ k: String) throws -> String {
        guard let v = m[k]?.string, !v.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { throw PackLoader.reject("\(k) must be a non-empty string") }
        return v
    }

    private func nonNegInt(_ m: JSONObject, _ k: String) throws -> Int64 {
        guard let v = m[k]?.int, v >= 0 else { throw PackLoader.reject("\(k) must be a non-negative integer") }
        return v
    }

    private func nonNegNumber(_ m: JSONObject, _ k: String) throws -> Double {
        guard let v = m[k]?.number else { throw PackLoader.reject("\(k) must be a number") }
        guard v.isFinite, v >= 0 else { throw PackLoader.reject("\(k) must be a finite non-negative number") }
        return v
    }

    /// - Parameter now: trusted current time, or nil when time is not trustworthy.
    public func load(manifest manifestBytes: [UInt8], signature: [UInt8], payload: [UInt8], now: PackInstant?,
                     releaseMode: Bool = false, budgetBytes: Int64 = PackLoader.defaultBudget) throws -> Loaded {
        let R = PackLoader.reject
        // 1. shape and types
        guard manifestBytes.count <= PackLoader.maxManifestBytes else { throw R("manifest too large") }
        guard let text = String(data: Data(manifestBytes), encoding: .utf8),
              let parsed = try? MiniJson.parse(text), let m = parsed.object else { throw R("manifest not valid JSON") }
        guard m["manifest_type"]?.string == PackLoader.manifestV2 else { throw R("unknown manifest type") }
        guard m.keySet == PackLoader.keys else { throw R("manifest keys mismatch") }
        for k in ["payload_size_bytes", "rights_epoch", "title_count", "descriptor_bytes", "vector_count"] { _ = try nonNegInt(m, k) }
        let indexedHours = try nonNegNumber(m, "indexed_hours")
        let sampling = try nonNegNumber(m, "sampling_interval_s")
        guard let packId = m["pack_id"]?.string, PackLoader.isPackId(packId) else { throw R("bad pack_id") }
        for k in ["generator_version", "preprocessing_version", "index_format_version", "calibration_version",
                  "signed_time_basis", "key_id", "grant_id", "payload_sha256"] { _ = try str(m, k) }
        guard let tomb = m["tombstones"]?.array else { throw R("tombstones must be a list") }
        guard tomb.allSatisfy({ $0.string != nil }) else { throw R("tombstones must be a list of strings") }
        guard let regions = m["region_grants"]?.array else { throw R("region_grants must be a list") }
        guard regions.allSatisfy({ ($0.string ?? "").isEmpty == false }) else { throw R("region_grants must be a list of strings") }
        guard let acts = m["operation_grants"]?.array else { throw R("operation_grants must be a list") }
        guard acts.allSatisfy({ v in v.string.map { PackLoader.acts.contains($0) } ?? false }) else { throw R("operation_grants contain an unknown act") }
        let dev = m["grant_id"]?.string == PackLoader.l0GrantId

        // 2. key + signature over the exact bytes
        let keyId = m["key_id"]!.string!
        guard !state.revokedKeyIds.contains(keyId) else { throw R("signer revoked") }
        guard let pub = state.trustedKeys[keyId] else { throw R("unknown signing key") }
        guard PackLoader.verifyEd25519(publicKey: pub, message: manifestBytes, signature: signature) else { throw R("bad signature") }

        // 3. compatibility (this engine: DACDHASH only)
        let fmt = m["index_format_version"]?.string
        guard fmt == PackIndex.formatV3 || fmt == PackIndex.formatV4 else { throw R("incompatible index format version") }
        guard m["descriptor_family"]?.string == "DACDHASH" else { throw R("this engine only accepts DACDHASH packs") }
        guard m["descriptor_bytes"]?.int == 8 else { throw R("descriptor family/bytes mismatch") }
        guard m["preprocessing_version"]?.string == PackIndex.exactPreprocessing else { throw R("incompatible preprocessing") }
        guard let calibration = m["calibration_status"]?.string, PackLoader.calibration.contains(calibration) else { throw R("unknown calibration_status") }
        if dev && calibration == "CALIBRATED" { throw R("synthetic development pack cannot claim release calibration") }
        // generator_version is provenance only (same rule in Python and Kotlin).

        // 4. versions
        let version = try PackLoader.parseVersion(m["pack_version"], "pack_version")
        let declaredMin = try PackLoader.parseVersion(m["minimum_allowed_version"], "minimum_allowed_version")
        guard version >= declaredMin else { throw R("pack_version below minimum allowed version") }
        let floor = state.minimumPackVersions[packId]
        if let f = floor, version < f { throw R("pack version rollback") }

        // 5. size + hash
        guard m["payload_size_bytes"]?.int == Int64(payload.count) else { throw R("payload size mismatch") }
        guard state.totalInstalled(excluding: packId) + Int64(payload.count) <= budgetBytes else { throw R("total installed index budget exceeded") }
        guard let digest = PackLoader.sha256Hex(payload), digest == m["payload_sha256"]?.string else { throw R("payload hash mismatch") }

        // 6. region assurance (D07)
        guard let method = m["region_assurance_method"]?.string, PackLoader.regionMethods.contains(method) else { throw R("unknown region assurance method") }
        guard state.acceptedRegionMethods.contains(method) else { throw R("region assurance method not accepted") }

        // 7. epoch
        let epoch = m["rights_epoch"]!.int!
        guard epoch >= state.minimumRightsEpoch else { throw R("rights epoch rollback") }

        // 8. validity window
        let validFrom = try PackLoader.parseInstant(m["valid_from"], "valid_from")
        let validUntil: PackInstant? = try m["valid_until"]!.isNull ? nil : PackLoader.parseInstant(m["valid_until"], "valid_until")
        if let u = validUntil, !(u > validFrom) { throw R("invalid validity window") }
        if let t = now {
            if t < validFrom { throw R("pack not yet valid") }
            if let u = validUntil, !(t < u) { throw R("pack expired") }
        } else if validUntil != nil || !dev || releaseMode {
            throw R("time not trustworthy")
        }
        if (!dev || releaseMode) && validUntil == nil { throw R("licensed/release packs need a valid_until") }

        // 9. release gate
        if releaseMode && (dev || calibration != "CALIBRATED") { throw R("release gate requires a licensed CALIBRATED pack") }

        // 10. payload parse + consistency
        let index: PackIndex
        do { index = try PackIndex.parse(payload, maxPayloadBytes: Int(clamping: budgetBytes)) } catch let PackError.invalid(why) {
            throw R("payload rejected: \(why)")
        }
        guard index.formatVersion == fmt else { throw R("manifest/payload index format mismatch") }
        guard Int64(index.vectorCount) == m["vector_count"]!.int! else { throw R("manifest/payload descriptor mismatch") }
        guard Int64(index.works.count) == m["title_count"]!.int! else { throw R("manifest/payload title count mismatch") }
        guard abs(index.samplingIntervalS - sampling) <= 1e-9 else { throw R("manifest/payload sampling interval mismatch") }
        let expectedHours = Double(index.vectorCount) * index.samplingIntervalS / 3600.0
        guard abs(indexedHours - expectedHours) <= 1e-6 * max(1.0, expectedHours) else { throw R("indexed_hours inconsistent") }

        // Commit only now.
        state.minimumRightsEpoch = max(state.minimumRightsEpoch, epoch)
        state.installedIndexBytes[packId] = Int64(payload.count)
        state.minimumPackVersions[packId] = (floor == nil || declaredMin > floor!) ? declaredMin : floor!
        return Loaded(manifest: m, index: index)
    }
}
