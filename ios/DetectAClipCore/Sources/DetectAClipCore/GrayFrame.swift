import Foundation

/// An 8-bit grayscale frame held in memory only. Frames are never written to disk (D08).
public struct GrayFrame: Sendable, Equatable {
    public let width: Int
    public let height: Int
    public var pixels: [UInt8]

    public init(width: Int, height: Int, pixels: [UInt8]) {
        precondition(width > 0 && height > 0 && pixels.count == width * height,
                     "pixel buffer does not match frame size")
        self.width = width
        self.height = height
        self.pixels = pixels
    }

    /// Population standard deviation of the pixel values; a flat frame carries no signal.
    public var standardDeviation: Double {
        let n = Double(pixels.count)
        var sum = 0.0
        var sumSquares = 0.0
        for p in pixels {
            let v = Double(p)
            sum += v
            sumSquares += v * v
        }
        let mean = sum / n
        return (max(0, sumSquares / n - mean * mean)).squareRoot()
    }
}
