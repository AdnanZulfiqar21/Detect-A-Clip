import Foundation

/// Procedural generator for self-created synthetic L0 "works" (roadmap P00-T07, ED-03/ED-04).
/// A work is fully defined by its seed; frames are rendered on demand from (seed, time) and no
/// third-party footage, font or trademark is involved. Output is visibly synthetic: drifting
/// interference patterns with moving discs, cut into 4-second "shots".
public enum SyntheticRenderer {
    public static let width = 64
    public static let height = 48
    public static let shotLength: Double = 4.0

    struct Wave {
        let fx: Double
        let fy: Double
        let phase: Double
        let speed: Double
        let amplitude: Double
    }

    struct Disc {
        let cx: Double
        let cy: Double
        let vx: Double
        let vy: Double
        let radius: Double
        let value: Double
    }

    static func shot(seed: UInt64, index: Int) -> (waves: [Wave], discs: [Disc]) {
        var rng = SplitMix64(seed: seed ^ (UInt64(index + 1) &* 0x9E37_79B9_7F4A_7C15))
        var waves: [Wave] = []
        for _ in 0..<3 {
            let fx = rng.uniform(-0.35, 0.35)
            let fy = rng.uniform(-0.35, 0.35)
            let phase = rng.uniform(0, 2 * Double.pi)
            let speed = rng.uniform(-0.6, 0.6)
            let amplitude = rng.uniform(0.5, 1.0)
            waves.append(Wave(fx: fx, fy: fy, phase: phase, speed: speed, amplitude: amplitude))
        }
        var discs: [Disc] = []
        for _ in 0..<2 {
            let cx = rng.uniform(0, Double(width))
            let cy = rng.uniform(0, Double(height))
            let vx = rng.uniform(-4, 4)
            let vy = rng.uniform(-4, 4)
            let radius = rng.uniform(4, 9)
            let value = rng.unit() < 0.5 ? 0.8 : -0.8
            discs.append(Disc(cx: cx, cy: cy, vx: vx, vy: vy, radius: radius, value: value))
        }
        return (waves, discs)
    }

    /// Renders the frame of work `seed` at playback time `t` (seconds, t ≥ 0).
    public static func frame(seed: UInt64, at t: Double) -> GrayFrame {
        let time = max(0, t)
        let shotIndex = Int((time / shotLength).rounded(.down))
        let local = time - Double(shotIndex) * shotLength
        let (waves, discs) = shot(seed: seed, index: shotIndex)
        let amplitudeSum = waves.reduce(0) { $0 + $1.amplitude }
        let positions = discs.map { d -> (x: Double, y: Double, r2: Double, value: Double) in
            (wrap(d.cx + d.vx * local, Double(width)),
             wrap(d.cy + d.vy * local, Double(height)),
             d.radius * d.radius,
             d.value)
        }
        var pixels = [UInt8](repeating: 0, count: width * height)
        for y in 0..<height {
            for x in 0..<width {
                var v = 0.0
                for w in waves {
                    v += w.amplitude * sin(w.fx * Double(x) + w.fy * Double(y) + w.phase + w.speed * local)
                }
                v /= amplitudeSum
                for p in positions {
                    let dx = Double(x) - p.x
                    let dy = Double(y) - p.y
                    if dx * dx + dy * dy < p.r2 {
                        v = p.value
                    }
                }
                pixels[y * width + x] = UInt8(Int(min(255, max(0, 128 + 100 * v))))
            }
        }
        return GrayFrame(width: width, height: height, pixels: pixels)
    }

    private static func wrap(_ value: Double, _ modulus: Double) -> Double {
        let r = value.truncatingRemainder(dividingBy: modulus)
        return r < 0 ? r + modulus : r
    }
}

/// A self-created synthetic work. Titles say "Synthetic" so no result can be mistaken for a
/// real film, series, drama or anime.
public struct SyntheticWork: Sendable, Hashable, Identifiable {
    public let id: String
    public let title: String
    public let seed: UInt64

    public init(id: String, title: String, seed: UInt64) {
        self.id = id
        self.title = title
        self.seed = seed
    }
}

/// What the in-app synthetic playback source shows. Stands in for "a clip playing in another
/// app" while screen capture stays disabled in this build (P02-T02: no frames before G00).
public enum SyntheticClip: Sendable, Equatable {
    case catalogued(SyntheticWork, startOffset: Double)
    /// A synthetic work that is deliberately not in the pack (AI-02 style absent case).
    case uncatalogued(seed: UInt64, startOffset: Double)
    /// Flat grey picture with sensor-like noise (INSUFFICIENT_SIGNAL case).
    case blank

    /// Frame shown at `elapsed` seconds after playback start, with brightness shift and
    /// per-pixel noise so the query never equals a reference frame byte-for-byte.
    public func frame(at elapsed: Double, rng: inout SplitMix64) -> GrayFrame {
        var frame: GrayFrame
        switch self {
        case let .catalogued(work, offset):
            frame = SyntheticRenderer.frame(seed: work.seed, at: offset + elapsed)
        case let .uncatalogued(seed, offset):
            frame = SyntheticRenderer.frame(seed: seed, at: offset + elapsed)
        case .blank:
            frame = GrayFrame(width: SyntheticRenderer.width, height: SyntheticRenderer.height,
                              pixels: [UInt8](repeating: 128,
                                              count: SyntheticRenderer.width * SyntheticRenderer.height))
        }
        let shift = rng.uniform(-10, 10)
        for i in frame.pixels.indices {
            let v = Double(frame.pixels[i]) + shift + rng.uniform(-12, 12)
            frame.pixels[i] = UInt8(Int(min(255, max(0, v))))
        }
        return frame
    }
}
