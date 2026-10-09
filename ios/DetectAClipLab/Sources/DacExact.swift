// Swift port of DAC-CROP-v1 / DAC-QUAL-v1 / mirrored DAC-DHASH-v1 (l0/dac_l0/index/exact.py,
// android DacDhash.kt). Status: IMPLEMENTED_NOT_VERIFIED — ExactPathGoldenTests on a Mac (B-02).

extension DacDhash {
    public static func luma(_ rgb: [UInt8], width: Int, height: Int, stride: Int = 3) -> [Int] {
        (0..<(width * height)).map { k in
            let p = k * stride
            return (77 * Int(rgb[p]) + 150 * Int(rgb[p + 1]) + 29 * Int(rgb[p + 2]) + 128) >> 8
        }
    }

    private static func trim(_ f: [Bool]) -> (Int, Int) {
        var lo = 0, hi = f.count
        while lo < hi && f[lo] { lo += 1 }
        while hi > lo && f[hi - 1] { hi -= 1 }
        return (lo, hi)
    }

    /// [top, bottom, left, right) half-open.
    public static func cropRect(_ y: [Int], w: Int, h: Int) -> [Int] {
        var top = 0, bot = h, left = 0, right = w
        for _ in 0..<2 {
            if bot <= top || right <= left { break }
            let rows = (top..<bot).map { r -> Bool in
                var mx = Int.min, mn = Int.max
                for x in left..<right { let v = y[r * w + x]; mx = max(mx, v); mn = min(mn, v) }
                return mx < 16 || mx - mn <= 8
            }
            let (t, b) = trim(rows); let t0 = top
            top = t0 + t; bot = t0 + b
            if bot <= top { break }
            let cols = (left..<right).map { c -> Bool in
                var mx = Int.min, mn = Int.max
                for yy in top..<bot { let v = y[yy * w + c]; mx = max(mx, v); mn = min(mn, v) }
                return mx < 16 || mx - mn <= 8
            }
            let (l, r) = trim(cols); let l0 = left
            left = l0 + l; right = l0 + r
        }
        if 10 * (bot - top) < 4 * h || 10 * (right - left) < 4 * w { return [0, h, 0, w] }
        return [top, bot, left, right]
    }

    public static func cellMeans(_ y: [Int], w: Int, rect: [Int], gx: Int, gy: Int, mirrored: Bool = false) -> [Int64] {
        let rh = rect[1] - rect[0], rw = rect[3] - rect[2]
        precondition(rw >= gx && rh >= gy, "frame too small")
        var out = [Int64](repeating: 0, count: gx * gy)
        for j in 0..<gy {
            let y0 = (j * rh) / gy, y1 = ((j + 1) * rh) / gy
            for i in 0..<gx {
                let x0 = (i * rw) / gx, x1 = ((i + 1) * rw) / gx
                var sum: Int64 = 0
                for yy in y0..<y1 { for xx in x0..<x1 {
                    let sx = mirrored ? rw - 1 - xx : xx
                    sum += Int64(y[(rect[0] + yy) * w + rect[2] + sx])
                } }
                out[j * gx + i] = sum / Int64((y1 - y0) * (x1 - x0))
            }
        }
        return out
    }

    public static func dhashRegion(_ y: [Int], w: Int, rect: [Int], mirrored: Bool = false) -> UInt64 {
        let m = cellMeans(y, w: w, rect: rect, gx: 9, gy: 8, mirrored: mirrored)
        var v: UInt64 = 0
        for j in 0..<8 { for i in 0..<8 { v = (v << 1) | (m[j * 9 + i + 1] > m[j * 9 + i] ? 1 : 0) } }
        return v
    }

    public static func quality(_ y: [Int], w: Int, rect: [Int], prev: [Int64]?) -> (String, [Int64]) {
        let m = cellMeans(y, w: w, rect: rect, gx: 16, gy: 9)
        let mx = m.max()!, mn = m.min()!
        if mx < 12 { return ("BLANK", m) }
        if mx - mn < 6 { return ("FLAT", m) }
        if let p = prev, zip(m, p).allSatisfy({ abs($0 - $1) <= 1 }) { return ("STATIC", m) }
        return ("OK", m)
    }
}
