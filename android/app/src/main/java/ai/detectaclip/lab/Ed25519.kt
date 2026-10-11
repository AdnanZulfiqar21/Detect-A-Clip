package ai.detectaclip.lab

import java.math.BigInteger
import java.security.MessageDigest

/**
 * Pure-Kotlin Ed25519 signature verification (RFC 8032 §5.1.7), used by [PackLoader] only
 * when no platform provider can process an Ed25519 key (observed: the Android 16 emulator's
 * providers serve `Signature("Ed25519")` but reject the X.509 key spec; Android 17 and the
 * JVM verify through the platform). Verification only: no signing, no private keys.
 *
 * Checks: 32-byte key and 64-byte signature; canonical point encodings (y < p, valid square
 * root, x = 0 only with sign 0); S < L; [S]B == R + [k]A with k = SHA-512(R ‖ A ‖ M) mod L.
 * Constant time is not required for verification of public data. Self-implemented: listed
 * for independent review (P06-T08) and checked against the 68 manifest cases signed by
 * Python's `cryptography` (OpenSSL) and the RFC 8032 §7.1 vectors (Ed25519Test).
 */
object Ed25519 {
    private val P: BigInteger = BigInteger.TWO.pow(255).subtract(BigInteger.valueOf(19))
    val L: BigInteger = BigInteger.TWO.pow(252).add(BigInteger("27742317777372353535851937790883648493"))
    private val D: BigInteger = BigInteger.valueOf(-121665).multiply(BigInteger.valueOf(121666).modInverse(P)).mod(P)
    private val D2: BigInteger = D.shiftLeft(1).mod(P)
    private val SQRT_M1: BigInteger = BigInteger.TWO.modPow(P.subtract(BigInteger.ONE).shiftRight(2), P)
    private val SQRT_EXP: BigInteger = P.add(BigInteger.valueOf(3)).shiftRight(3)
    private val BY: BigInteger = BigInteger.valueOf(4).multiply(BigInteger.valueOf(5).modInverse(P)).mod(P)
    private val BASE: Point = Point(recoverX(BY, 0)!!, BY)
    private val IDENTITY = Point(BigInteger.ZERO, BigInteger.ONE, BigInteger.ONE, BigInteger.ZERO)

    /** Extended twisted Edwards coordinates (a = -1): x = X/Z, y = Y/Z, T = XY/Z. */
    private class Point(val x: BigInteger, val y: BigInteger, val z: BigInteger, val t: BigInteger) {
        constructor(x: BigInteger, y: BigInteger) : this(x, y, BigInteger.ONE, x.multiply(y).mod(P))
    }

    private fun m(a: BigInteger, b: BigInteger) = a.multiply(b).mod(P)

    /** RFC 8032 §5.1.4 addition (complete formulas). */
    private fun add(p: Point, q: Point): Point {
        val a = m(p.y.subtract(p.x), q.y.subtract(q.x))
        val b = m(p.y.add(p.x), q.y.add(q.x))
        val c = m(m(p.t, D2), q.t)
        val d = m(p.z.shiftLeft(1), q.z)
        val e = b.subtract(a); val f = d.subtract(c); val g = d.add(c); val h = b.add(a)
        return Point(m(e, f), m(g, h), m(f, g), m(e, h))
    }

    private fun double(p: Point): Point {
        val a = m(p.x, p.x); val b = m(p.y, p.y); val c = m(p.z, p.z).shiftLeft(1)
        val h = a.add(b)
        val xy = p.x.add(p.y)
        val e = h.subtract(m(xy, xy)); val g = a.subtract(b); val f = c.add(g)
        return Point(m(e, f), m(g, h), m(f, g), m(e, h))
    }

    private fun mul(p: Point, k: BigInteger): Point {
        var r = IDENTITY
        for (i in k.bitLength() - 1 downTo 0) {
            r = double(r)
            if (k.testBit(i)) r = add(r, p)
        }
        return r
    }

    private fun equal(p: Point, q: Point): Boolean =
        m(p.x, q.z) == m(q.x, p.z) && m(p.y, q.z) == m(q.y, p.z)

    private fun recoverX(y: BigInteger, sign: Int): BigInteger? {
        if (y >= P) return null
        val y2 = m(y, y)
        val u = y2.subtract(BigInteger.ONE).mod(P)
        val v = m(D, y2).add(BigInteger.ONE).mod(P)
        if (v.signum() == 0) return null
        val uv = m(u, v.modInverse(P))
        var x = uv.modPow(SQRT_EXP, P)
        if (m(x, x) != uv) x = m(x, SQRT_M1)
        if (m(x, x) != uv) return null
        if (x.signum() == 0 && sign == 1) return null
        if (x.testBit(0) != (sign == 1)) x = P.subtract(x)
        return x
    }

    private fun littleEndian(b: ByteArray): BigInteger = BigInteger(1, b.reversedArray())

    private fun decode(b: ByteArray): Point? {
        if (b.size != 32) return null
        val sign = (b[31].toInt() ushr 7) and 1
        val yBytes = b.copyOf().also { it[31] = (it[31].toInt() and 0x7F).toByte() }
        val y = littleEndian(yBytes)
        val x = recoverX(y, sign) ?: return null
        return Point(x, y)
    }

    fun verify(publicKey: ByteArray, message: ByteArray, signature: ByteArray): Boolean {
        if (publicKey.size != 32 || signature.size != 64) return false
        val a = decode(publicKey) ?: return false
        val r = decode(signature.copyOfRange(0, 32)) ?: return false
        val s = littleEndian(signature.copyOfRange(32, 64))
        if (s >= L) return false
        val h = MessageDigest.getInstance("SHA-512").run {
            update(signature, 0, 32); update(publicKey); update(message); digest()
        }
        val k = littleEndian(h).mod(L)
        return equal(mul(BASE, s), add(r, mul(a, k)))
    }
}
