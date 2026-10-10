// Simulator UI test of the LAB journey: Terms first, decline keeps scanning off, Terms stay
// readable, acceptance enables Start, and Start is refused before any OS prompt because this
// build admits no capture cell. Simulator evidence only (not device, signing or store).
import XCTest

final class LabJourneyUITests: XCTestCase {
    override func setUp() { continueAfterFailure = false }

    func testTermsGateAndStartRefusedWithoutCaptureCell() {
        let app = XCUIApplication()
        app.launchArguments = ["-DACResetForUITest"]
        app.launch()

        // First use: the Terms sheet is shown before anything else.
        XCTAssertTrue(app.buttons["accept"].waitForExistence(timeout: 10))
        app.buttons["decline"].tap()

        let start = app.buttons["start"]
        XCTAssertTrue(start.waitForExistence(timeout: 5))
        XCTAssertFalse(start.isEnabled)
        XCTAssertTrue((app.staticTexts["status"].label).contains("Terms not accepted"))

        // Legal text stays readable after declining; accepting enables Start.
        app.buttons["terms"].tap()
        XCTAssertTrue(app.buttons["accept"].waitForExistence(timeout: 5))
        app.buttons["accept"].tap()
        XCTAssertTrue(start.waitForExistence(timeout: 5))
        XCTAssertTrue(start.isEnabled)

        // Start: refused locally, no disclosure and no system prompt, scan never begins.
        start.tap()
        let msg = app.staticTexts["message"]
        XCTAssertTrue(msg.waitForExistence(timeout: 5))
        XCTAssertEqual(msg.label, "Scanning unavailable: NO_CAPABILITY_CELL")
        XCTAssertFalse(app.alerts["Before you scan"].exists)
        XCTAssertTrue(app.staticTexts["status"].label.contains("State: idle"))

        // Stop / Cancel on an idle app is harmless.
        app.buttons["stop"].tap()
        XCTAssertTrue(app.staticTexts["status"].label.contains("State: idle"))
    }
}
