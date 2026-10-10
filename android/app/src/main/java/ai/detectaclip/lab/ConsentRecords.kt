package ai.detectaclip.lab

import java.security.MessageDigest

/**
 * Versioned Terms receipt and separate purpose choices (F03 first use / reopen, F04
 * TermsReceipt, CONS-01/02/03, P05-T02). Pure Kotlin; persistence is behind [ReceiptStorage]
 * so the Android build can use a small private file while tests use memory.
 *
 * Rules:
 *  - A receipt binds terms version + hash, locale, rendered-text hash, governing-language
 *    version and disclosure version. Any change of legal effect, **including a translation-only
 *    change of the rendered text**, invalidates it and requires a new notice and choice.
 *  - The receipt never stores an OS permission token and is never a substitute for the native
 *    per-scan consent. Declining Terms blocks scanning but keeps legal pages readable.
 *  - Purpose choices are separate records; an optional purpose (e.g. notifications) refused
 *    affects only that feature. Nothing here widens access silently.
 *
 * Status: JVM-tested; Android storage adapter compiled with AGP, no device test (B-01). Legal text is a DRAFT.
 */
data class TermsDocument(
    val termsVersion: String,
    val locale: String,
    val renderedText: String,
    val governingLanguageVersion: String,
    val disclosureVersion: String,
) {
    val termsHash: String get() = sha256("$termsVersion|$governingLanguageVersion")
    val renderedTextHash: String get() = sha256(renderedText)
}

data class TermsReceipt(
    val termsVersion: String,
    val termsHash: String,
    val locale: String,
    val renderedTextHash: String,
    val governingLanguageVersion: String,
    val disclosureVersion: String,
    val acceptedAtEpochMs: Long,
) {
    fun matches(doc: TermsDocument): Boolean =
        termsVersion == doc.termsVersion && termsHash == doc.termsHash && locale == doc.locale &&
            renderedTextHash == doc.renderedTextHash && governingLanguageVersion == doc.governingLanguageVersion &&
            disclosureVersion == doc.disclosureVersion

    fun encode(): String = listOf(termsVersion, termsHash, locale, renderedTextHash, governingLanguageVersion, disclosureVersion, acceptedAtEpochMs.toString())
        .joinToString("\n") { it.replace("\n", " ") }

    companion object {
        fun decode(s: String): TermsReceipt? {
            val p = s.split("\n")
            if (p.size != 7) return null
            val t = p[6].toLongOrNull() ?: return null
            return TermsReceipt(p[0], p[1], p[2], p[3], p[4], p[5], t)
        }
    }
}

interface ReceiptStorage {
    fun read(key: String): String?
    fun write(key: String, value: String)
    fun delete(key: String)
}

class ConsentRecords(private val storage: ReceiptStorage, private val clock: () -> Long) {

    enum class TermsStatus { ACCEPTED_CURRENT, NOT_ACCEPTED, CHANGED_NEEDS_NEW_NOTICE, DECLINED }

    fun termsStatus(current: TermsDocument): TermsStatus {
        if (storage.read(KEY_DECLINED) == current.termsHash + "|" + current.renderedTextHash) return TermsStatus.DECLINED
        val r = storage.read(KEY_RECEIPT)?.let { TermsReceipt.decode(it) } ?: return TermsStatus.NOT_ACCEPTED
        return if (r.matches(current)) TermsStatus.ACCEPTED_CURRENT else TermsStatus.CHANGED_NEEDS_NEW_NOTICE
    }

    /** Explicit user action only. */
    fun accept(doc: TermsDocument): TermsReceipt {
        val r = TermsReceipt(doc.termsVersion, doc.termsHash, doc.locale, doc.renderedTextHash,
            doc.governingLanguageVersion, doc.disclosureVersion, clock())
        storage.write(KEY_RECEIPT, r.encode())
        storage.delete(KEY_DECLINED)
        return r
    }

    fun decline(doc: TermsDocument) {
        storage.delete(KEY_RECEIPT)
        storage.write(KEY_DECLINED, doc.termsHash + "|" + doc.renderedTextHash)
    }

    /** Scanning is allowed only with a receipt for exactly the current document. */
    fun scanningAllowed(current: TermsDocument): Boolean = termsStatus(current) == TermsStatus.ACCEPTED_CURRENT

    fun setPurpose(purpose: String, allowed: Boolean) {
        require(purpose.matches(Regex("[a-z_]{1,32}")))
        storage.write("purpose.$purpose", if (allowed) "1" else "0")
    }

    /** Unknown purpose → not allowed (default deny). */
    fun purposeAllowed(purpose: String): Boolean = storage.read("purpose.$purpose") == "1"

    companion object {
        private const val KEY_RECEIPT = "terms.receipt"
        private const val KEY_DECLINED = "terms.declined"
    }
}

internal fun sha256(s: String): String =
    MessageDigest.getInstance("SHA-256").digest(s.toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it) }
