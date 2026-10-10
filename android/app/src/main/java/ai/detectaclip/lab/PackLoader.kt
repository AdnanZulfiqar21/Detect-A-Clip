package ai.detectaclip.lab

import java.security.KeyFactory
import java.security.MessageDigest
import java.security.Signature
import java.security.spec.X509EncodedKeySpec
import java.time.OffsetDateTime
import java.time.format.DateTimeParseException

/**
 * Fail-closed loader for manifest V2 packs (detached Ed25519 signature over the exact manifest
 * bytes). Same rules and verdicts as l0/dac_l0/pack/loader.py; checked case by case against
 * golden_manifest_cases.txt. Device state is only changed after every check passed.
 *
 * Engine scope: DACDHASH payloads only (PackIndex). Ed25519 is used through the platform
 * provider (JDK 15+ on the JVM; on Android its availability per OS version is a device check).
 */
class PackLoader(private val state: DeviceRightsState) {

    class Rejected(val reason: String) : Exception(reason)

    /** Persistent-by-design rights state: epochs, version floors, installed bytes, keys. */
    class DeviceRightsState {
        var minimumRightsEpoch: Long = 0
        val installedIndexBytes = HashMap<String, Long>()
        val minimumPackVersions = HashMap<String, Triple<Long, Long, Long>>()
        val acceptedRegionMethods = mutableSetOf("NONE")
        val trustedKeys = HashMap<String, ByteArray>()   // key id -> raw 32-byte Ed25519 public key
        val revokedKeyIds = HashSet<String>()
        fun totalInstalledExcluding(packId: String) = installedIndexBytes.filterKeys { it != packId }.values.sum()
    }

    data class Loaded(val manifest: Map<String, Any?>, val index: PackIndex)

    companion object {
        const val MANIFEST_V2 = "L0_DEV_INTEGRITY_MANIFEST_V2"
        const val L0_GRANT_ID = "GRANT-L0-SELF-SYNTH-001"
        const val MAX_MANIFEST_BYTES = 64 * 1024
        const val DEFAULT_BUDGET = 250_000_000L
        private val KEYS = setOf(
            "pack_id", "pack_version", "payload_sha256", "payload_size_bytes", "generator_version",
            "preprocessing_version", "index_format_version", "calibration_version", "calibration_status",
            "rights_epoch", "valid_from", "valid_until", "signed_time_basis", "key_id", "tombstones",
            "minimum_allowed_version", "region_grants", "operation_grants", "region_assurance_method",
            "indexed_hours", "title_count", "descriptor_bytes", "sampling_interval_s", "descriptor_family",
            "vector_count", "grant_id", "manifest_type",
        )
        private val CALIBRATION = setOf("UNCALIBRATED", "CALIBRATED_L0_SYNTHETIC", "CALIBRATED")
        private val ACTS = setOf("INGEST_REFERENCE", "BUILD_INDEX", "LOCAL_DISTRIBUTION", "TRANSIENT_QUERY", "DECISION",
            "DISPLAY_METADATA", "DISPLAY_STILL", "DERIVATIVE_DESCRIPTOR", "EVALUATION", "TRAINING")
        private val REGION_METHODS = setOf("NONE", "STORE_COUNTRY_ATTESTATION", "ONLINE_ACTIVATION", "COARSE_LOCATION")
        private val PACK_ID = Regex("^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
        private val VERSION = Regex("^(0|[1-9][0-9]{0,8})\\.(0|[1-9][0-9]{0,8})\\.(0|[1-9][0-9]{0,8})$")
        private val INSTANT = Regex("^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,6})?(Z|[+-]\\d{2}:\\d{2})$")
        private val X509_ED25519_PREFIX = byteArrayOf(0x30, 0x2a, 0x30, 0x05, 0x06, 0x03, 0x2b, 0x65, 0x70, 0x03, 0x21, 0x00)

        fun parseInstant(v: Any?, what: String): OffsetDateTime {
            val s = v as? String ?: throw Rejected("$what malformed or missing")
            if (!INSTANT.matches(s)) throw Rejected("$what malformed or missing")
            val t = try { OffsetDateTime.parse(s) } catch (e: DateTimeParseException) { throw Rejected("$what malformed or missing") }
            if (t.year < 1) throw Rejected("$what malformed (year 0000)")   // Python datetime starts at year 1
            return t
        }

        fun parseVersion(v: Any?, what: String): Triple<Long, Long, Long> {
            val s = v as? String ?: throw Rejected("$what malformed")
            if (!VERSION.matches(s)) throw Rejected("$what malformed")
            val p = s.split(".").map { it.toLong() }
            return Triple(p[0], p[1], p[2])
        }

        private fun cmp(a: Triple<Long, Long, Long>, b: Triple<Long, Long, Long>) =
            compareValuesBy(a, b, { it.first }, { it.second }, { it.third })

        fun verifyEd25519(rawPublicKey: ByteArray, message: ByteArray, signature: ByteArray): Boolean {
            if (rawPublicKey.size != 32 || signature.size != 64) return false
            return try {
                val key = KeyFactory.getInstance("Ed25519").generatePublic(X509EncodedKeySpec(X509_ED25519_PREFIX + rawPublicKey))
                Signature.getInstance("Ed25519").run { initVerify(key); update(message); verify(signature) }
            } catch (e: Exception) { false }
        }
    }

    private fun str(m: Map<*, *>, k: String): String {
        val v = m[k] as? String ?: throw Rejected("$k must be a non-empty string")
        if (v.isBlank()) throw Rejected("$k must be a non-empty string")
        return v
    }

    private fun nonNegInt(m: Map<*, *>, k: String): Long {
        val v = m[k] as? Long ?: throw Rejected("$k must be a non-negative integer")
        if (v < 0) throw Rejected("$k must be a non-negative integer")
        return v
    }

    private fun nonNegNumber(m: Map<*, *>, k: String): Double {
        val v = when (val x = m[k]) { is Long -> x.toDouble(); is Double -> x; else -> throw Rejected("$k must be a number") }
        if (!v.isFinite() || v < 0) throw Rejected("$k must be a finite non-negative number")
        return v
    }

    /**
     * @param now trusted current time, or null when time is not trustworthy.
     */
    fun load(manifestBytes: ByteArray, signature: ByteArray, payload: ByteArray, now: OffsetDateTime?,
             releaseMode: Boolean = false, budgetBytes: Long = DEFAULT_BUDGET): Loaded {
        // 1. shape and types
        if (manifestBytes.size > MAX_MANIFEST_BYTES) throw Rejected("manifest too large")
        val m = try {
            MiniJson.parse(Charsets.UTF_8.newDecoder().decode(java.nio.ByteBuffer.wrap(manifestBytes)).toString()) as? Map<*, *>
        } catch (e: Exception) { null } ?: throw Rejected("manifest not valid JSON")
        if (m["manifest_type"] != MANIFEST_V2) throw Rejected("unknown manifest type")
        if (m.keys != KEYS) throw Rejected("manifest keys mismatch")
        for (k in listOf("payload_size_bytes", "rights_epoch", "title_count", "descriptor_bytes", "vector_count")) nonNegInt(m, k)
        val indexedHours = nonNegNumber(m, "indexed_hours")
        val sampling = nonNegNumber(m, "sampling_interval_s")
        val packId = m["pack_id"] as? String ?: throw Rejected("bad pack_id")
        if (!PACK_ID.matches(packId)) throw Rejected("bad pack_id")
        for (k in listOf("generator_version", "preprocessing_version", "index_format_version", "calibration_version",
            "signed_time_basis", "key_id", "grant_id", "payload_sha256")) str(m, k)
        val tomb = m["tombstones"] as? List<*> ?: throw Rejected("tombstones must be a list")
        if (tomb.any { it !is String }) throw Rejected("tombstones must be a list of strings")
        val regions = m["region_grants"] as? List<*> ?: throw Rejected("region_grants must be a list")
        if (regions.any { it !is String || it.isEmpty() }) throw Rejected("region_grants must be a list of strings")
        val acts = m["operation_grants"] as? List<*> ?: throw Rejected("operation_grants must be a list")
        if (acts.any { it !in ACTS }) throw Rejected("operation_grants contain an unknown act")
        val dev = m["grant_id"] == L0_GRANT_ID

        // 2. key + signature over the exact bytes
        val keyId = m["key_id"] as String
        if (keyId in state.revokedKeyIds) throw Rejected("signer revoked")
        val pub = state.trustedKeys[keyId] ?: throw Rejected("unknown signing key")
        if (!verifyEd25519(pub, manifestBytes, signature)) throw Rejected("bad signature")

        // 3. compatibility (this engine: DACDHASH only)
        if (m["index_format_version"] != PackIndex.FORMAT_V3 && m["index_format_version"] != PackIndex.FORMAT_V4) throw Rejected("incompatible index format version")
        if (m["descriptor_family"] != "DACDHASH") throw Rejected("this engine only accepts DACDHASH packs")
        if (m["descriptor_bytes"] != 8L) throw Rejected("descriptor family/bytes mismatch")
        if (m["preprocessing_version"] != PackIndex.EXACT_PREPROCESSING) throw Rejected("incompatible preprocessing")
        val calibration = m["calibration_status"] as String? ?: throw Rejected("unknown calibration_status")
        if (calibration !in CALIBRATION) throw Rejected("unknown calibration_status")
        if (dev && calibration == "CALIBRATED") throw Rejected("synthetic development pack cannot claim release calibration")
        // The synthetic generator version is provenance only for this engine; Python LAB tools
        // additionally pin it for development packs.

        // 4. versions
        val version = parseVersion(m["pack_version"], "pack_version")
        val declaredMin = parseVersion(m["minimum_allowed_version"], "minimum_allowed_version")
        if (cmp(version, declaredMin) < 0) throw Rejected("pack_version below minimum allowed version")
        val floor = state.minimumPackVersions[packId]
        if (floor != null && cmp(version, floor) < 0) throw Rejected("pack version rollback")

        // 5. size + hash
        if (m["payload_size_bytes"] != payload.size.toLong()) throw Rejected("payload size mismatch")
        if (state.totalInstalledExcluding(packId) + payload.size > budgetBytes) throw Rejected("total installed index budget exceeded")
        val digest = MessageDigest.getInstance("SHA-256").digest(payload).joinToString("") { "%02x".format(it) }
        if (digest != m["payload_sha256"]) throw Rejected("payload hash mismatch")

        // 6. region assurance (D07)
        val method = m["region_assurance_method"] as? String
        if (method !in REGION_METHODS) throw Rejected("unknown region assurance method")
        if (method !in state.acceptedRegionMethods) throw Rejected("region assurance method not accepted")

        // 7. epoch
        val epoch = m["rights_epoch"] as Long
        if (epoch < state.minimumRightsEpoch) throw Rejected("rights epoch rollback")

        // 8. validity window
        val validFrom = parseInstant(m["valid_from"], "valid_from")
        val validUntil = if (m["valid_until"] == null) null else parseInstant(m["valid_until"], "valid_until")
        if (validUntil != null && !validUntil.toInstant().isAfter(validFrom.toInstant())) throw Rejected("invalid validity window")
        if (now != null) {
            if (now.toInstant().isBefore(validFrom.toInstant())) throw Rejected("pack not yet valid")
            if (validUntil != null && !now.toInstant().isBefore(validUntil.toInstant())) throw Rejected("pack expired")
        } else if (validUntil != null || !dev || releaseMode) {
            throw Rejected("time not trustworthy")
        }
        if ((!dev || releaseMode) && validUntil == null) throw Rejected("licensed/release packs need a valid_until")

        // 9. release gate
        if (releaseMode && (dev || calibration != "CALIBRATED")) throw Rejected("release gate requires a licensed CALIBRATED pack")

        // 10. payload parse + consistency
        val index = try { PackIndex.parse(payload, budgetBytes) } catch (e: IllegalArgumentException) {
            throw Rejected("payload rejected: ${e.message}")
        } catch (e: java.nio.charset.CharacterCodingException) { throw Rejected("payload metadata not UTF-8") }
        if (index.formatVersion != m["index_format_version"]) throw Rejected("manifest/payload index format mismatch")
        if (index.vectorCount.toLong() != m["vector_count"]) throw Rejected("manifest/payload descriptor mismatch")
        if (index.works.size.toLong() != m["title_count"]) throw Rejected("manifest/payload title count mismatch")
        if (Math.abs(index.samplingIntervalS - sampling) > 1e-9) throw Rejected("manifest/payload sampling interval mismatch")
        val expectedHours = index.vectorCount * index.samplingIntervalS / 3600.0
        if (Math.abs(indexedHours - expectedHours) > 1e-6 * maxOf(1.0, expectedHours)) throw Rejected("indexed_hours inconsistent")

        // Commit only now.
        state.minimumRightsEpoch = maxOf(state.minimumRightsEpoch, epoch)
        state.installedIndexBytes[packId] = payload.size.toLong()
        state.minimumPackVersions[packId] = if (floor == null || cmp(declaredMin, floor) > 0) declaredMin else floor
        @Suppress("UNCHECKED_CAST")
        return Loaded(m as Map<String, Any?>, index)
    }
}
