// Every verdict in golden_format_cases.txt (generated and checked by the Python parser) must be
// reproduced by the Swift parser, as it is by Kotlin FormatContractTest.
import XCTest
@testable import DetectAClipCore

final class FormatContractTests: XCTestCase {
    private func cases() throws -> [(name: String, accept: Bool, payload: [UInt8])] {
        try Golden.lines("golden_format_cases.txt").filter { $0.hasPrefix("CASE ") }.map {
            let p = $0.split(separator: " ")
            return (String(p[1]), p[2] == "ACCEPT", Golden.hex(p[3]))
        }
    }

    func testSwiftVerdictsMatchThePythonContract() throws {
        let all = try cases()
        XCTAssertGreaterThanOrEqual(all.count, 49)
        var mismatches: [String] = []
        for c in all {
            let accepted = (try? PackIndex.parse(c.payload)) != nil
            if accepted != c.accept { mismatches.append("\(c.name): expected \(c.accept ? "ACCEPT" : "REJECT")") }
        }
        XCTAssertEqual(mismatches, [])
    }

    func testAcceptedV4CaseExposesNamesAliasesAndSharedScenes() throws {
        let c = try cases().first { $0.name == "valid_v4_aliases_series_shared_scene" }!
        let p = try PackIndex.parse(c.payload)
        XCTAssertEqual(p.formatVersion, "idx-flat-4")
        XCTAssertEqual(p.aliases[0], ["Synthetic Work Zero"])
        XCTAssertEqual(p.sharedScenes.count, 1)
        XCTAssertEqual(p.sharedScenes[0].groupId, "intro-S-X")
        XCTAssertEqual(p.works[2].editions, ["E2_BROADCAST"])
        XCTAssertEqual(p.displayName(workIndex: 0, preferences: ["ur-Latn"]), "Masnooi Kaam 000")
        XCTAssertEqual(p.displayName(workIndex: 0, preferences: ["ur-PK"]), "Masnooi Kaam 000")
        XCTAssertEqual(p.displayName(workIndex: 0, preferences: ["ko"]), "Synthetic Work 000")
        XCTAssertEqual(PackIndex.resolveDisplayName([:], preferences: ["en"], fallback: "SW100"), "SW100")
    }

    func testResultDisplayNamesMatchPython() throws {
        let lines = try Golden.lines("golden_format_cases.txt")
        let v4 = try cases().first { $0.name == "valid_v4_aliases_series_shared_scene" }!
        let p = try PackIndex.parse(v4.payload)
        let rows = lines.filter { $0.hasPrefix("DISPLAY ") }.map { $0.split(separator: " ").map(String.init) }
        XCTAssertGreaterThanOrEqual(rows.count, 10)
        for c in rows {
            let prefs = c[3] == "-" ? [] : c[3].split(separator: ",").map(String.init)
            let expected: String? = c[4] == "-" ? nil : String(decoding: Golden.hex(c[4]), as: UTF8.self)
            let got = p.resultDisplayName(workId: c[1] == "-" ? nil : c[1], episodeId: c[2] == "-" ? nil : c[2], preferences: prefs)
            XCTAssertEqual(got, expected, c.joined(separator: " "))
        }
    }

    func testV3PayloadMigratesWithEmptyAliasesAndScenes() throws {
        let c = try cases().first { $0.name == "valid_v3_migration_no_aliases" }!
        let p = try PackIndex.parse(c.payload)
        XCTAssertEqual(p.formatVersion, "idx-flat-3")
        XCTAssertTrue(p.aliases.allSatisfy { $0.isEmpty })
        XCTAssertTrue(p.sharedScenes.isEmpty)
    }

    func testStrictJsonRejectsDuplicatesNaNAndTrailingData() {
        XCTAssertThrowsError(try MiniJson.parse("{\"a\":1,\"a\":2}"))
        XCTAssertThrowsError(try MiniJson.parse("{\"a\":NaN}"))
        XCTAssertThrowsError(try MiniJson.parse("[1] x"))
        XCTAssertThrowsError(try MiniJson.parse("01"))
        XCTAssertEqual(try MiniJson.parse("[1, 1.0, -0, 1e2]"), .array([.int(1), .double(1.0), .int(0), .double(100.0)]))
        XCTAssertEqual(try MiniJson.parse("\"\\ud83d\\ude00\"").string?.unicodeScalars.count, 1)
    }
}
