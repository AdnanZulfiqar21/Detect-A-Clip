import XCTest
@testable import DetectAClipCore

final class RecognitionTests: XCTestCase {
    private static let catalogue = SyntheticCatalogue.makeDefault()

    /// Simulates the app's acquisition loop: source delivers ~10 fps, sampler admits ≤ 2 fps.
    private func query(_ clip: SyntheticClip, seed: UInt64, frames: Int = 12) -> [QuerySample] {
        var rng = SplitMix64(seed: seed)
        var sampler = FrameSampler(capacity: frames)
        var samples: [QuerySample] = []
        var t = 0.0
        while !sampler.isFull {
            if sampler.admit(at: t) {
                samples.append(QuerySample(time: t, frame: clip.frame(at: t, rng: &rng)))
            }
            t += 0.1
        }
        return samples
    }

    func testRendererMatchesPythonPrototype() {
        // Golden values from the reference prototype of the same generator; pixels may differ
        // by one where libm `sin` rounds differently, the hash must not.
        let frame = SyntheticRenderer.frame(seed: 1001, at: 0)
        for (index, expected) in [(0, 147), (1, 128), (100, 216), (3071, 113)] {
            XCTAssertLessThanOrEqual(abs(Int(frame.pixels[index]) - expected), 1, "pixel \(index)")
        }
        XCTAssertEqual(PerceptualHash.dHash(frame), 0x9B92_A46C_6D46_96B6)
    }

    func testRendererIsDeterministicAndWorksDiffer() {
        XCTAssertEqual(SyntheticRenderer.frame(seed: 1002, at: 7.25),
                       SyntheticRenderer.frame(seed: 1002, at: 7.25))
        XCTAssertNotEqual(PerceptualHash.dHash(SyntheticRenderer.frame(seed: 1001, at: 3)),
                          PerceptualHash.dHash(SyntheticRenderer.frame(seed: 1002, at: 3)))
    }

    func testCatalogueManifestIsUncalibratedSynthetic() {
        let manifest = Self.catalogue.manifest
        XCTAssertEqual(manifest.calibrationStatus, "UNCALIBRATED")
        XCTAssertEqual(manifest.rightsBasis, "SELF_CREATED_SYNTHETIC")
        XCTAssertEqual(Self.catalogue.entries.count, 6 * SyntheticCatalogue.referenceFrameCount)
        XCTAssertTrue(Self.catalogue.works.allSatisfy { $0.title.hasPrefix("Synthetic") })
    }

    func testCataloguedNoisyClipsAreVerifiedAsTheRightWork() {
        let matcher = Matcher(catalogue: Self.catalogue)
        for (i, work) in Self.catalogue.works.enumerated() {
            for offset in [0.0, 3.3, 11.7, 22.9] {
                let decision = matcher.decide(query(.catalogued(work, startOffset: offset),
                                                    seed: UInt64(i * 100) + UInt64(offset * 10)))
                XCTAssertEqual(decision.state, .verifiedMatch, "\(work.id) @\(offset)")
                XCTAssertEqual(decision.work, work)
            }
        }
    }

    func testUncataloguedWorksNeverMatch() {
        let matcher = Matcher(catalogue: Self.catalogue)
        for seed in UInt64(2001)...2030 {
            let decision = matcher.decide(query(.uncatalogued(seed: seed, startOffset: Double(seed % 20)),
                                                seed: seed))
            XCTAssertEqual(decision.state, .noConfidentMatch, "seed \(seed)")
            XCTAssertNil(decision.work)
        }
    }

    func testBlankPictureIsInsufficientSignal() {
        let decision = Matcher(catalogue: Self.catalogue).decide(query(.blank, seed: 9))
        XCTAssertEqual(decision.state, .insufficientSignal)
        XCTAssertEqual(decision.usableFrames, 0)
    }

    func testTooFewUsableFramesAbstainsEvenIfTheyMatch() {
        let work = Self.catalogue.works[0]
        let samples = query(.catalogued(work, startOffset: 2), seed: 1, frames: 3)
        XCTAssertEqual(Matcher(catalogue: Self.catalogue).decide(samples).state, .insufficientSignal)
    }

    func testShuffledFramesFromOneWorkAreNotVerified() {
        // Same work but playback order destroyed: identity evidence without temporal support
        // must not reach VERIFIED_MATCH.
        let work = Self.catalogue.works[2]
        var rng = SplitMix64(seed: 5)
        let times = [20.0, 2.0, 15.5, 6.0, 26.0, 0.5, 11.0, 24.0, 4.5, 18.0, 9.0, 13.0]
        let samples = times.enumerated().map { i, t in
            QuerySample(time: Double(i) * 0.5,
                        frame: SyntheticClip.catalogued(work, startOffset: 0).frame(at: t, rng: &rng))
        }
        let decision = Matcher(catalogue: Self.catalogue).decide(samples)
        XCTAssertEqual(decision.state, .possibleMatch)
        XCTAssertEqual(decision.work, work)
    }

    func testMatcherNeverEmitsReservedStates() {
        let matcher = Matcher(catalogue: Self.catalogue)
        let clips: [SyntheticClip] = [.blank, .uncatalogued(seed: 2100, startOffset: 1),
                                      .catalogued(Self.catalogue.works[4], startOffset: 5)]
        for (i, clip) in clips.enumerated() {
            let state = matcher.decide(query(clip, seed: UInt64(i))).state
            XCTAssertFalse(ResultState.unreachableInL0L1.contains(state))
        }
    }

    func testSamplerEnforcesSpacingAndCapacity() {
        var sampler = FrameSampler(capacity: 3)
        XCTAssertTrue(sampler.admit(at: 0))
        XCTAssertFalse(sampler.admit(at: 0.2))
        XCTAssertFalse(sampler.admit(at: 0.49))
        XCTAssertTrue(sampler.admit(at: 0.5))
        XCTAssertTrue(sampler.admit(at: 5))
        XCTAssertFalse(sampler.admit(at: 10), "capacity reached")
        XCTAssertTrue(sampler.isFull)
    }
}
