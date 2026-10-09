package ai.detectaclip.lab

import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * Bounded, untrusted parser for the L0 index payload (format idx-flat-3, see
 * l0/dac_l0/index/builder.py) and a flat Hamming retriever for 8-byte hashes.
 *
 * Signature/manifest verification happens before this parser in the pack loader; this file
 * only parses a payload whose hash was already checked. Every count and length is bounded.
 * Ranking is distance ascending, then vector index ascending (portable; ED-16).
 *
 * Status: JVM-tested against the Python builder (golden_e2e.txt); no device test.
 */
class PackIndex private constructor(
    val descriptorBytes: Int,
    val samplingIntervalS: Double,
    val hashes: LongArray,
    private val locators: IntArray, // 3 ints per vector: work, edition, tMs
    val works: List<Recognition.WorkEntry>,
    val names: List<Map<String, String>>,
) {
    val vectorCount: Int get() = hashes.size

    fun locator(i: Int) = Recognition.Locator(locators[3 * i], locators[3 * i + 1], locators[3 * i + 2])

    fun search(query: Long, topK: Int, maxDistance: Double): List<Recognition.Candidate> {
        val n = hashes.size
        if (n == 0) return emptyList()
        val dist = IntArray(n) { java.lang.Long.bitCount(hashes[it] xor query) }
        val order = (0 until n).sortedWith(compareBy<Int>({ dist[it] }, { it }))
        val out = ArrayList<Recognition.Candidate>()
        for (i in order.take(minOf(topK, n))) {
            if (dist[i] > maxDistance) continue
            out += Recognition.Candidate(locator(i), dist[i].toDouble())
        }
        return out
    }

    companion object {
        private val MAGIC = "DACL0IDX".toByteArray(Charsets.US_ASCII)
        const val FORMAT = "idx-flat-3"
        private const val HEADER = 8 + 2 + 2 + 4 + 4 + 8
        private const val MAX_VECTORS = 20_000_000
        private const val MAX_META = 64 * 1024 * 1024

        fun parse(data: ByteArray, maxPayloadBytes: Long = 250_000_000L): PackIndex {
            require(data.size <= maxPayloadBytes) { "payload exceeds installed index budget" }
            require(data.size >= HEADER + 4) { "payload too short" }
            val bb = ByteBuffer.wrap(data).order(ByteOrder.LITTLE_ENDIAN)
            val magic = ByteArray(8).also { bb.get(it) }
            require(magic.contentEquals(MAGIC)) { "bad magic" }
            require(bb.short.toInt() == 1) { "bad version" }
            val dBytes = bb.short.toInt() and 0xFFFF
            val n = bb.int
            val nWorks = bb.int
            val interval = bb.double
            require(dBytes == 8) { "only 8-byte hash descriptors are supported by this engine" }
            require(n in 0..MAX_VECTORS && nWorks in 0..1_000_000) { "count out of bounds" }
            require(interval in 0.1..60.0) { "sampling interval out of bounds" }
            val metaLen = bb.int
            require(metaLen in 0..MAX_META && bb.remaining() >= metaLen) { "bad metadata length" }
            val metaBytes = ByteArray(metaLen).also { bb.get(it) }
            val meta = MiniJson.parse(String(metaBytes, Charsets.UTF_8)) as? Map<*, *> ?: error("metadata not an object")
            require(meta["index_format_version"] == FORMAT) { "incompatible index format version" }
            require(meta["family"] == "HASH64") { "family mismatch" }
            val worksRaw = meta["works"] as? List<*> ?: error("no works")
            require(worksRaw.size == nWorks) { "work table mismatch" }
            val works = ArrayList<Recognition.WorkEntry>()
            val names = ArrayList<Map<String, String>>()
            for (w in worksRaw) {
                val m = w as? Map<*, *> ?: error("bad work entry")
                require(m.keys == setOf("work_index", "work_id", "synthetic_title", "editions", "durations_s", "series_id", "episode_id", "names")) { "bad work entry keys" }
                val eds = (m["editions"] as List<*>).map { it as String }
                val nm = (m["names"] as Map<*, *>).entries.associate { (it.key as String) to (it.value as String) }
                require(nm.size <= 16 && nm.all { it.key.matches(Regex("^[a-z]{2,3}(-[A-Za-z0-9]{2,8}){0,3}$")) && it.value.length in 1..200 && it.value.none { c -> c.code < 32 } }) { "bad names" }
                works += Recognition.WorkEntry((m["work_index"] as Number).toInt(), m["work_id"] as String, m["series_id"] as String?, m["episode_id"] as String?, eds)
                names += nm
            }
            val vec = dBytes + 16
            require(bb.remaining().toLong() == n.toLong() * vec) { "body length mismatch" }
            val hashes = LongArray(n)
            val locs = IntArray(3 * n)
            for (i in 0 until n) {
                hashes[i] = bb.long
                val work = bb.int
                val edition = bb.short.toInt() and 0xFFFF
                val tMs = bb.int
                bb.short; bb.int // segment, reserved
                require(work in 0 until nWorks) { "locator references unknown work" }
                require(edition < works[work].editions.size) { "locator references unknown edition" }
                locs[3 * i] = work; locs[3 * i + 1] = edition; locs[3 * i + 2] = tMs
            }
            return PackIndex(dBytes, interval, hashes, locs, works, names)
        }
    }
}

/** Minimal bounded JSON reader for pack metadata (objects, arrays, strings, numbers, true/false/null). */
object MiniJson {
    fun parse(s: String): Any? {
        val p = P(s)
        val v = p.value(0)
        p.ws()
        require(p.i == s.length) { "trailing data" }
        return v
    }

    private class P(val s: String) {
        var i = 0
        fun ws() { while (i < s.length && s[i] in " \t\r\n") i++ }
        fun value(depth: Int): Any? {
            require(depth < 32) { "nesting too deep" }
            ws()
            require(i < s.length) { "unexpected end" }
            return when (val c = s[i]) {
                '{' -> obj(depth)
                '[' -> arr(depth)
                '"' -> str()
                't' -> lit("true", true)
                'f' -> lit("false", false)
                'n' -> lit("null", null)
                else -> if (c == '-' || c.isDigit()) num() else error("bad token at $i")
            }
        }
        fun lit(w: String, v: Any?): Any? { require(s.startsWith(w, i)) { "bad literal" }; i += w.length; return v }
        fun num(): Number {
            val st = i
            while (i < s.length && (s[i].isDigit() || s[i] in "+-.eE")) i++
            val t = s.substring(st, i)
            return t.toLongOrNull() ?: t.toDouble()
        }
        fun str(): String {
            i++
            val sb = StringBuilder()
            while (true) {
                require(i < s.length) { "unterminated string" }
                val c = s[i++]
                when (c) {
                    '"' -> return sb.toString()
                    '\\' -> {
                        val e = s[i++]
                        when (e) {
                            '"', '\\', '/' -> sb.append(e)
                            'b' -> sb.append('\b'); 'f' -> sb.append('\u000C'); 'n' -> sb.append('\n'); 'r' -> sb.append('\r'); 't' -> sb.append('\t')
                            'u' -> { sb.append(s.substring(i, i + 4).toInt(16).toChar()); i += 4 }
                            else -> error("bad escape")
                        }
                    }
                    else -> { require(c.code >= 0x20) { "control character in string" }; sb.append(c) }
                }
                require(sb.length <= 1_000_000) { "string too long" }
            }
        }
        fun arr(d: Int): List<Any?> {
            i++; val out = ArrayList<Any?>(); ws()
            if (s[i] == ']') { i++; return out }
            while (true) {
                out += value(d + 1); ws()
                when (s[i++]) { ',' -> continue; ']' -> return out; else -> error("bad array") }
            }
        }
        fun obj(d: Int): Map<String, Any?> {
            i++; val out = LinkedHashMap<String, Any?>(); ws()
            if (s[i] == '}') { i++; return out }
            while (true) {
                ws(); require(s[i] == '"') { "bad key" }
                val k = str(); ws(); require(s[i++] == ':') { "missing colon" }
                require(!out.containsKey(k)) { "duplicate key" }
                out[k] = value(d + 1); ws()
                when (s[i++]) { ',' -> continue; '}' -> return out; else -> error("bad object") }
            }
        }
    }
}
