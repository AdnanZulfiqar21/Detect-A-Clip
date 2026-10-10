// Swift PackLoader verdicts must equal the Python loader on every committed manifest case
// (golden_manifest_cases.txt), and a rejected pack must leave the device state unchanged.
import XCTest
@testable import DetectAClipCore

final class ManifestContractTests: XCTestCase {
    func testSwiftVerdictsMatchPython() throws {
        #if !canImport(CryptoKit)
        throw XCTSkip("CryptoKit unavailable: PackLoader fails closed on this toolchain")
        #else
        let lines = try Golden.lines("golden_manifest_cases.txt")
        let pub = lines.first { $0.hasPrefix("PUBKEY ") }!.split(separator: " ").map(String.init)
        var payloads: [String: [UInt8]] = [:]
        for l in lines where l.hasPrefix("PAYLOAD ") {
            let p = l.split(separator: " ")
            payloads[String(p[1])] = Golden.hex(p[2])
        }
        var mismatches: [String] = []
        var n = 0
        for line in lines where line.hasPrefix("CASE ") {
            let p = line.split(separator: " ").map(String.init)
            var kv: [String: String] = [:]
            for item in p.dropFirst(3) {
                let eq = item.firstIndex(of: "=")!
                kv[String(item[..<eq])] = String(item[item.index(after: eq)...])
            }
            let st = PackLoader.DeviceRightsState()
            st.minimumRightsEpoch = Int64(kv["epoch"]!)!
            st.trustedKeys[pub[1]] = Golden.hex(pub[2])
            if kv["revoked"] == "1" { st.revokedKeyIds.insert(pub[1]) }
            if kv["floors"] != "-" {
                for item in kv["floors"]!.split(separator: ",") {
                    let parts = item.split(separator: ":")
                    st.minimumPackVersions[String(parts[0])] = try PackLoader.parseVersion(.string(String(parts[1])), "floor")
                }
            }
            let before = (st.minimumRightsEpoch, st.installedIndexBytes, st.minimumPackVersions)
            let now: PackInstant? = try kv["now"] == "UNTRUSTED" ? nil : PackLoader.parseInstant(.string(kv["now"]!), "now")
            let accepted: Bool
            do {
                _ = try PackLoader(state: st).load(manifest: Golden.hex(kv["manifest"]!), signature: Golden.hex(kv["sig"]!),
                                                   payload: payloads[kv["payload"]!]!, now: now, releaseMode: kv["release"] == "1")
                accepted = true
            } catch is PackLoader.Rejected {
                accepted = false
            }
            if accepted != (p[2] == "ACCEPT") { mismatches.append("\(p[1]): expected \(p[2])") }
            if !accepted {
                XCTAssertEqual(before.0, st.minimumRightsEpoch, "epoch changed on rejection in \(p[1])")
                XCTAssertEqual(before.1, st.installedIndexBytes, "bytes changed on rejection in \(p[1])")
                XCTAssertEqual(before.2, st.minimumPackVersions, "floors changed on rejection in \(p[1])")
            }
            n += 1
        }
        XCTAssertGreaterThanOrEqual(n, 60)
        XCTAssertEqual(mismatches, [])
        #endif
    }

    func testInstantParsingRules() throws {
        let a = try PackLoader.parseInstant(.string("2026-10-10T17:30:00+05:30"), "t")
        let b = try PackLoader.parseInstant(.string("2026-10-10T12:00:00Z"), "t")
        XCTAssertEqual(a, b)
        XCTAssertEqual(try PackLoader.parseInstant(.string("1970-01-01T00:00:00.000001Z"), "t").utcMicros, 1)
        for bad in ["2026-10-10T12:00:00", "2026-02-29T00:00:00Z", "0000-01-01T00:00:00Z", "2026-10-10T24:00:00Z",
                    "2026-10-10T12:00:60Z", "2026-10-10T12:00:00+19:00", "2026-10-10T12:00:00+05:60",
                    "2026-10-10T12:00:00.1234567Z", "2026-10-10t12:00:00z", "2026-10-10T12:00:00Z\n"] {
            XCTAssertThrowsError(try PackLoader.parseInstant(.string(bad), "t"), bad)
        }
        XCTAssertNoThrow(try PackLoader.parseInstant(.string("2024-02-29T00:00:00Z"), "t"))
        XCTAssertNoThrow(try PackLoader.parseInstant(.string("2026-10-10T12:00:00-18:00"), "t"))
    }

    func testVersionOrderingIsNumeric() throws {
        XCTAssertLessThan(try PackLoader.parseVersion(.string("2.9.0"), "v"), try PackLoader.parseVersion(.string("2.10.0"), "v"))
        for bad in ["1.02.0", "1.2", "1.2.3.4", "v1.2.3", "1.2.3-rc1", "1.\u{0663}.0", "1234567890.0.0"] {
            XCTAssertThrowsError(try PackLoader.parseVersion(.string(bad), "v"), bad)
        }
    }
}
