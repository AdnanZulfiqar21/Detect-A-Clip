package ai.detectaclip.lab

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/** Pure-Kotlin Ed25519 verifier: RFC 8032 §7.1 vectors, agreement with the platform provider on
 *  every signed manifest case, and refusal of tampered or malformed inputs. */
class Ed25519Test {
    private fun hex(s: String) = ByteArray(s.length / 2) { s.substring(2 * it, 2 * it + 2).toInt(16).toByte() }
    private fun manifestLines(): List<String> = listOf("src/test/resources/golden_manifest_cases.txt", "android/app/src/test/resources/golden_manifest_cases.txt",
        "app/src/test/resources/golden_manifest_cases.txt").map(::File).first { it.exists() }.readLines()

    // RFC 8032 section 7.1, TEST 1..3 (public key, message, signature).
    private val rfc = listOf(
        Triple("d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a", "",
            "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"),
        Triple("3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c", "72",
            "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00"),
        Triple("fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025", "af82",
            "6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac18ff9b538d16f290ae67f760984dc6594a7c15e9716ed28dc027beceea1ec40a"),
    )

    @Test fun rfc8032VectorsVerify() {
        for ((pk, msg, sig) in rfc) {
            assertEquals(64, sig.length / 2)
            assertTrue(pk.take(8), Ed25519.verify(hex(pk), hex(msg), hex(sig)))
            assertTrue(pk.take(8), PackLoader.verifyEd25519(hex(pk), hex(msg), hex(sig)))
        }
    }

    @Test fun tamperedInputsAreRefused() {
        val (pk, msg, sig) = rfc[2]
        val s = hex(sig); val m = hex(msg); val k = hex(pk)
        assertFalse(Ed25519.verify(k, m + byteArrayOf(0), s))                               // message changed
        assertFalse(Ed25519.verify(k, m, s.copyOf().also { it[0] = (it[0].toInt() xor 1).toByte() }))   // R bit flipped
        assertFalse(Ed25519.verify(k, m, s.copyOf().also { it[63] = (it[63].toInt() xor 1).toByte() })) // S bit flipped
        assertFalse(Ed25519.verify(hex(rfc[1].first), m, s))                                 // other key
        assertFalse(Ed25519.verify(k, m, s.copyOf(63)))                                       // short signature
        assertFalse(Ed25519.verify(k.copyOf(31), m, s))                                       // short key
        // Non-canonical S (S + L) is refused even though it would satisfy the group equation.
        val sPlusL = java.math.BigInteger(1, s.copyOfRange(32, 64).reversedArray()).add(Ed25519.L)
        val enc = sPlusL.toByteArray().reversedArray().copyOf(32)
        assertFalse(Ed25519.verify(k, m, s.copyOfRange(0, 32) + enc))
        // Invalid point encodings: y >= p, and x = 0 with the sign bit set.
        assertFalse(Ed25519.verify(ByteArray(32) { 0xFF.toByte() }.also { it[31] = 0x7F }, m, s))
        assertFalse(Ed25519.verify(ByteArray(32).also { it[0] = 1; it[31] = 0x80.toByte() }, m, s))
    }

    @Test fun pureVerifierAgreesWithThePlatformOnEveryManifestCase() {
        val r = GoldenRunner.pureEd25519AgreesWithPlatform(manifestLines())
        assertEquals(r.toString(), emptyList<String>(), r.mismatches)
        assertTrue(r.cases >= 68)
        assertTrue(PackLoader.ed25519Backend().startsWith("platform:"))   // the JVM verifies through its provider
    }
}
