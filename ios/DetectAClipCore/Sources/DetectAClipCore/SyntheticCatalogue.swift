import Foundation

/// Metadata of the single bundled development pack (D10: one synthetic pack). The integrity
/// status is UNCALIBRATED, so this pack can never pass a release gate (G03-L0, P03-T04c).
public struct PackManifest: Sendable, Equatable {
    public let packID: String
    public let version: String
    public let calibrationStatus: String
    public let rightsBasis: String
    public let titleCount: Int
    public let indexedSeconds: Double
    public let samplingInterval: Double
    public let descriptorBytes: Int
}

public struct ReferenceEntry: Sendable, Equatable {
    public let workIndex: Int
    public let frameIndex: Int
    public let hash: UInt64
}

/// Tiny local L0 catalogue: dHash of each synthetic work every 0.5 s for 30 s, searched by flat
/// (exhaustive) Hamming lookup. Built in memory at launch from seeds; nothing is downloaded and
/// no per-scan lookup leaves the device.
public struct SyntheticCatalogue: Sendable {
    public static let referenceInterval: Double = 0.5
    public static let referenceFrameCount = 60

    public let works: [SyntheticWork]
    public let entries: [ReferenceEntry]
    public let manifest: PackManifest

    public init(works: [SyntheticWork]) {
        var entries: [ReferenceEntry] = []
        entries.reserveCapacity(works.count * Self.referenceFrameCount)
        for (workIndex, work) in works.enumerated() {
            for frameIndex in 0..<Self.referenceFrameCount {
                let frame = SyntheticRenderer.frame(seed: work.seed,
                                                    at: Double(frameIndex) * Self.referenceInterval)
                entries.append(ReferenceEntry(workIndex: workIndex, frameIndex: frameIndex,
                                              hash: PerceptualHash.dHash(frame)))
            }
        }
        self.works = works
        self.entries = entries
        self.manifest = PackManifest(
            packID: "L0-SYNTHETIC-DEV",
            version: "0.1.0",
            calibrationStatus: "UNCALIBRATED",
            rightsBasis: "SELF_CREATED_SYNTHETIC",
            titleCount: works.count,
            indexedSeconds: Double(works.count * Self.referenceFrameCount) * Self.referenceInterval,
            samplingInterval: Self.referenceInterval,
            descriptorBytes: entries.count * MemoryLayout<UInt64>.size
        )
    }

    /// Seeds 1001…1006. Seeds from 2001 upward are reserved for uncatalogued demo works.
    public static func makeDefault() -> SyntheticCatalogue {
        let works = (1...6).map { n in
            SyntheticWork(id: String(format: "SYN-W%02d", n),
                          title: String(format: "Synthetic Work %02d", n),
                          seed: UInt64(1000 + n))
        }
        return SyntheticCatalogue(works: works)
    }

    /// Exhaustive nearest neighbour; ties resolve to the earliest entry.
    public func nearest(to hash: UInt64) -> (entry: ReferenceEntry, distance: Int)? {
        var best: (entry: ReferenceEntry, distance: Int)?
        for entry in entries {
            let d = PerceptualHash.distance(entry.hash, hash)
            if best == nil || d < best!.distance {
                best = (entry, d)
            }
        }
        return best
    }
}
