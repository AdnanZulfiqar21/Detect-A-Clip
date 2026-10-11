// Ports of android ConsentRecords.kt and EligibilityGate.kt. Status: compiled and tested by the swift-core CI job (macOS, Swift 6.3.3; first pass at 3f77273).
// CryptoKit is used only for the rendered-text hash; no network, no OS permission tokens.
import Foundation
#if canImport(CryptoKit)
import CryptoKit
#endif

func sha256Hex(_ s: String) -> String {
    #if canImport(CryptoKit)
    return SHA256.hash(data: Data(s.utf8)).map { String(format: "%02x", $0) }.joined()
    #else
    fatalError("CryptoKit unavailable")
    #endif
}

public struct TermsDocument: Equatable {
    public let termsVersion, locale, renderedText, governingLanguageVersion, disclosureVersion: String
    public init(termsVersion: String, locale: String, renderedText: String, governingLanguageVersion: String, disclosureVersion: String) {
        self.termsVersion = termsVersion; self.locale = locale; self.renderedText = renderedText
        self.governingLanguageVersion = governingLanguageVersion; self.disclosureVersion = disclosureVersion
    }
    public var termsHash: String { sha256Hex("\(termsVersion)|\(governingLanguageVersion)") }
    public var renderedTextHash: String { sha256Hex(renderedText) }
}

public struct TermsReceipt: Equatable, Codable {
    public let termsVersion, termsHash, locale, renderedTextHash, governingLanguageVersion, disclosureVersion: String
    public let acceptedAtEpochMs: Int64
    func matches(_ d: TermsDocument) -> Bool {
        termsVersion == d.termsVersion && termsHash == d.termsHash && locale == d.locale &&
            renderedTextHash == d.renderedTextHash && governingLanguageVersion == d.governingLanguageVersion &&
            disclosureVersion == d.disclosureVersion
    }
}

public protocol ReceiptStorage: AnyObject {
    func read(_ key: String) -> String?
    func write(_ key: String, _ value: String)
    func delete(_ key: String)
}

public final class ConsentRecords {
    public enum TermsStatus { case acceptedCurrent, notAccepted, changedNeedsNewNotice, declined }
    private let storage: ReceiptStorage
    private let clock: () -> Int64
    public init(storage: ReceiptStorage, clock: @escaping () -> Int64) { self.storage = storage; self.clock = clock }

    public func termsStatus(_ d: TermsDocument) -> TermsStatus {
        if storage.read("terms.declined") == d.termsHash + "|" + d.renderedTextHash { return .declined }
        guard let raw = storage.read("terms.receipt"), let data = raw.data(using: .utf8),
              let r = try? JSONDecoder().decode(TermsReceipt.self, from: data) else { return .notAccepted }
        return r.matches(d) ? .acceptedCurrent : .changedNeedsNewNotice
    }

    @discardableResult public func accept(_ d: TermsDocument) -> TermsReceipt {
        let r = TermsReceipt(termsVersion: d.termsVersion, termsHash: d.termsHash, locale: d.locale,
                             renderedTextHash: d.renderedTextHash, governingLanguageVersion: d.governingLanguageVersion,
                             disclosureVersion: d.disclosureVersion, acceptedAtEpochMs: clock())
        if let data = try? JSONEncoder().encode(r), let s = String(data: data, encoding: .utf8) { storage.write("terms.receipt", s) }
        storage.delete("terms.declined")
        return r
    }

    public func decline(_ d: TermsDocument) {
        storage.delete("terms.receipt")
        storage.write("terms.declined", d.termsHash + "|" + d.renderedTextHash)
    }

    public func scanningAllowed(_ d: TermsDocument) -> Bool { termsStatus(d) == .acceptedCurrent }
    public func setPurpose(_ p: String, allowed: Bool) { storage.write("purpose.\(p)", allowed ? "1" : "0") }
    public func purposeAllowed(_ p: String) -> Bool { storage.read("purpose.\(p)") == "1" }
}

public final class EligibilityGate {
    public enum BuildPurpose { case lab, consumer }
    public struct Cell {
        public let cellId, osBuild, labStatus, consumerStatus: String
        public let stopPathVerified, postCaptureCancelVerified: Bool
        public let expiresAtEpochMs: Int64?
        public init(cellId: String, osBuild: String, labStatus: String, consumerStatus: String,
                    stopPathVerified: Bool, postCaptureCancelVerified: Bool, expiresAtEpochMs: Int64?) {
            self.cellId = cellId; self.osBuild = osBuild; self.labStatus = labStatus; self.consumerStatus = consumerStatus
            self.stopPathVerified = stopPathVerified; self.postCaptureCancelVerified = postCaptureCancelVerified
            self.expiresAtEpochMs = expiresAtEpochMs
        }
    }
    public struct PackState {
        public let packId, calibrationStatus: String?
        public let leaseValidUntilEpochMs: Int64?
        public let timeTrustworthy: Bool
        public init(packId: String?, calibrationStatus: String?, leaseValidUntilEpochMs: Int64?, timeTrustworthy: Bool) {
            self.packId = packId; self.calibrationStatus = calibrationStatus
            self.leaseValidUntilEpochMs = leaseValidUntilEpochMs; self.timeTrustworthy = timeTrustworthy
        }
    }
    public enum Decision: Equatable { case eligible, denied(String) }

    private let clock: () -> Int64
    public init(clock: @escaping () -> Int64) { self.clock = clock }

    public func check(_ purpose: BuildPurpose, termsAccepted: Bool, cell: Cell?, currentOsBuild: String, pack: PackState,
                      snapchatRequested: Bool = false, cloudModeRequested: Bool = false) -> Decision {
        if cloudModeRequested { return .denied("MODE_R_OFF") }
        if snapchatRequested { return .denied("SNAPCHAT_OFF") }
        if !termsAccepted { return .denied("TERMS_NOT_ACCEPTED") }
        guard let cell else { return .denied("NO_CAPABILITY_CELL") }
        if cell.osBuild != currentOsBuild { return .denied("CELL_OS_BUILD_MISMATCH") }
        let now = clock()
        if let e = cell.expiresAtEpochMs, !pack.timeTrustworthy || now >= e { return .denied("CELL_EXPIRED_OR_TIME_UNTRUSTED") }
        switch purpose {
        case .lab:
            if cell.labStatus != "PASS" && cell.labStatus != "IN_PROGRESS" { return .denied("CELL_NOT_ADMITTED_FOR_LAB") }
        case .consumer:
            if cell.consumerStatus != "PASS" { return .denied("CONSUMER_CELL_BLOCKED") }
            if !cell.stopPathVerified || !cell.postCaptureCancelVerified { return .denied("STOP_PATH_UNVERIFIED") }
        }
        guard pack.packId != nil else { return .denied("NO_ACTIVE_PACK") }
        if purpose == .consumer && pack.calibrationStatus != "CALIBRATED" { return .denied("PACK_NOT_RELEASE_CALIBRATED") }
        if let u = pack.leaseValidUntilEpochMs, !pack.timeTrustworthy || now >= u { return .denied("PACK_LEASE_EXPIRED_OR_TIME_UNTRUSTED") }
        return .eligible
    }
}
