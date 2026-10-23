import Foundation

/// 64-bit difference hash (dHash): box-downsample to 9×8, then compare horizontal neighbours.
/// This is the F04 "hash/flat lookup" baseline, not a learned embedding.
public enum PerceptualHash {
    public static func dHash(_ frame: GrayFrame) -> UInt64 {
        precondition(frame.width >= 9 && frame.height >= 8, "frame too small for dHash")
        var cells = [Double](repeating: 0, count: 72)
        for gy in 0..<8 {
            let y0 = gy * frame.height / 8
            let y1 = (gy + 1) * frame.height / 8
            for gx in 0..<9 {
                let x0 = gx * frame.width / 9
                let x1 = (gx + 1) * frame.width / 9
                var sum = 0
                for y in y0..<y1 {
                    let row = y * frame.width
                    for x in x0..<x1 {
                        sum += Int(frame.pixels[row + x])
                    }
                }
                cells[gy * 9 + gx] = Double(sum) / Double((y1 - y0) * (x1 - x0))
            }
        }
        var hash: UInt64 = 0
        for gy in 0..<8 {
            for gx in 0..<8 {
                hash = (hash << 1) | (cells[gy * 9 + gx] < cells[gy * 9 + gx + 1] ? 1 : 0)
            }
        }
        return hash
    }

    public static func distance(_ a: UInt64, _ b: UInt64) -> Int {
        (a ^ b).nonzeroBitCount
    }
}
