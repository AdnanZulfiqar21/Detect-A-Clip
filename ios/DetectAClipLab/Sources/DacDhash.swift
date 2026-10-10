// DAC-DHASH-v1 Swift port (see l0/dac_l0/index/exact.py and android DacDhash.kt).
// Status: IMPLEMENTED_NOT_VERIFIED — DacDhashGoldenTests must pass on a Mac (B-02).

public enum DacDhash {
    public static let spec = "DAC-DHASH-v1"

    /// Integer BT.601 luma, (77 R + 150 G + 29 B + 128) >> 8. Split into typed steps so the
    /// type checker stays fast.
    @inline(__always) public static func lumaOf(_ r: UInt8, _ g: UInt8, _ b: UInt8) -> Int {
        let rr: Int = 77 * Int(r)
        let gg: Int = 150 * Int(g)
        let bb: Int = 29 * Int(b)
        let sum: Int = rr + gg + bb + 128
        return sum >> 8
    }

    @inline(__always) static func clampByte(_ v: Int) -> UInt8 { UInt8(Swift.min(255, Swift.max(0, v))) }

    public static func hash(_ rgb: [UInt8], width: Int, height: Int, stride: Int = 3) -> UInt64 {
        precondition(width >= 9 && height >= 8 && rgb.count >= width * height * stride)
        var means = [[Int64]](repeating: [Int64](repeating: 0, count: 9), count: 8)
        for j in 0..<8 {
            let y0 = (j * height) / 8, y1 = ((j + 1) * height) / 8
            for i in 0..<9 {
                let x0 = (i * width) / 9, x1 = ((i + 1) * width) / 9
                var sum: Int64 = 0
                for y in y0..<y1 {
                    var p = (y * width + x0) * stride
                    for _ in x0..<x1 {
                        sum += Int64(lumaOf(rgb[p], rgb[p + 1], rgb[p + 2]))
                        p += stride
                    }
                }
                means[j][i] = sum / Int64((y1 - y0) * (x1 - x0))
            }
        }
        var v: UInt64 = 0
        for j in 0..<8 { for i in 0..<8 { v = (v << 1) | (means[j][i + 1] > means[j][i] ? 1 : 0) } }
        return v
    }

    public struct XorShift32 {
        var s: UInt32
        public init(_ seed: UInt32) { s = seed == 0 ? 0x9E37_79B9 : seed }
        public mutating func next() -> UInt32 { s ^= s << 13; s ^= s >> 17; s ^= s << 5; return s }
    }

    public static func testFrame(seed: UInt32, w: Int, h: Int) -> [UInt8] {
        var rng = XorShift32(seed)
        let rx = Int(rng.next() % UInt32(w)), ry = Int(rng.next() % UInt32(h))
        let rw = 1 + Int(rng.next() % UInt32(w / 2)), rh = 1 + Int(rng.next() % UInt32(h / 2))
        let col = [Int(rng.next() & 255), Int(rng.next() & 255), Int(rng.next() & 255)]
        var out = [UInt8](repeating: 0, count: w * h * 3)
        for y in 0..<h {
            for x in 0..<w {
                let inside = x >= rx && x < rx + rw && y >= ry && y < ry + rh
                for ch in 0..<3 {
                    let gx: Int = (x * 255) / Swift.max(1, w - 1)
                    let gy: Int = (y * 255) / Swift.max(1, h - 1) * (ch + 1)
                    let base: Int = inside ? col[ch] : ((gx + gy) & 255)
                    let noise: Int = Int(rng.next() >> 28) - 8
                    out[(y * w + x) * 3 + ch] = clampByte(base + noise)
                }
            }
        }
        return out
    }
}
