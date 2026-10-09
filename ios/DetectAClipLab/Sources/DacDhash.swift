// DAC-DHASH-v1 Swift port (see l0/dac_l0/index/exact.py and android DacDhash.kt).
// Status: IMPLEMENTED_NOT_VERIFIED — DacDhashGoldenTests must pass on a Mac (B-02).

public enum DacDhash {
    public static let spec = "DAC-DHASH-v1"

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
                        sum += Int64((77 * Int(rgb[p]) + 150 * Int(rgb[p + 1]) + 29 * Int(rgb[p + 2]) + 128) >> 8)
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
                    let base = inside ? col[ch] : (((x * 255) / max(1, w - 1) + (y * 255) / max(1, h - 1) * (ch + 1)) & 255)
                    let noise = Int(rng.next() >> 28) - 8
                    out[(y * w + x) * 3 + ch] = UInt8(min(255, max(0, base + noise)))
                }
            }
        }
        return out
    }
}
