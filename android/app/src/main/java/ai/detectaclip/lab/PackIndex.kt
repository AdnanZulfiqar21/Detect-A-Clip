package ai.detectaclip.lab

import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * Bounded, untrusted parser for the index payload, implementing the format contract in
 * docs/PACK_FORMAT.md / l0/dac_l0/index/format.py: writer idx-flat-4, reader idx-flat-3 and
 * idx-flat-4. Every verdict must match Python on golden_format_cases.txt.
 *
 * This engine accepts only DACDHASH payloads (DAC-CROP-v1 + DAC-QUAL-v1 + DAC-DHASH-v1).
 * Signature/manifest checks happen in [PackLoader] before this parser runs.
 * Ranking is distance ascending, then vector index ascending (portable; ED-16).
 */
class PackIndex private constructor(
    val formatVersion: String,
    val samplingIntervalS: Double,
    val hashes: LongArray,
    private val locators: IntArray, // 3 ints per vector: work, edition, tMs
    val works: List<Recognition.WorkEntry>,
    val names: List<Map<String, String>>,
    val aliases: List<List<String>>,
    val sharedScenes: List<SharedScene>,
) {
    data class SharedSceneMember(val workIndex: Int, val editionIndex: Int, val startMs: Long, val endMs: Long)
    data class SharedScene(val groupId: String, val members: List<SharedSceneMember>)

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

    /** Same order as Python resolve_display_name: exact locale, same language, English, first, fallback. */
    fun displayName(workIndex: Int, preferences: List<String>): String =
        resolveDisplayName(names[workIndex], preferences, works[workIndex].workId)

    companion object {
        private val MAGIC = "DACL0IDX".toByteArray(Charsets.US_ASCII)
        const val FORMAT_V3 = "idx-flat-3"
        const val FORMAT_V4 = "idx-flat-4"
        const val EXACT_PREPROCESSING = "dac-crop-v1+dac-qual-v1+dac-dhash-v1"
        private const val HEADER = 8 + 2 + 2 + 4 + 4 + 8
        private const val MAX_VECTORS = 20_000_000
        private const val MAX_META = 64 * 1024 * 1024
        private val ID = Regex("^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
        private val EPISODE = Regex("^[A-Za-z0-9_.-]{1,64}$")
        private val EDITION = Regex("^[A-Za-z0-9_]{1,64}$")
        private val LOCALE = Regex("^[a-z]{2,3}(-[A-Za-z0-9]{2,8}){0,3}$")
        private val WORK_KEYS_V3 = setOf("work_index", "work_id", "synthetic_title", "editions", "durations_s", "series_id", "episode_id", "names")
        private val META_KEYS_V3 = setOf("index_format_version", "generator_version", "preprocessing_version", "family", "works")

        private fun fail(msg: String): Nothing = throw IllegalArgumentException(msg)

        /** Python `len()` counts code points; so do we. Control characters (< 32) are refused. */
        private fun text(v: Any?, what: String, max: Int = 200): String {
            val s = v as? String ?: fail("bad $what")
            val n = s.codePointCount(0, s.length)
            if (n < 1 || n > max || s.any { it.code < 32 }) fail("bad $what")
            return s
        }

        private fun int(v: Any?, what: String): Long = (v as? Long) ?: fail("bad $what")   // Double / Boolean refused

        private fun number(v: Any?, what: String): Double = when (v) {
            is Long -> v.toDouble()
            is Double -> v
            else -> fail("bad $what")
        }

        fun resolveDisplayName(names: Map<String, String>, preferences: List<String>, fallback: String): String {
            for (p in preferences) names[p]?.let { return it }
            for (p in preferences) {
                val lang = p.substringBefore('-')
                for (k in names.keys.sorted()) if (k.substringBefore('-') == lang) return names.getValue(k)
            }
            names["en"]?.let { return it }
            return if (names.isEmpty()) fallback else names.getValue(names.keys.sorted().first())
        }

        fun parse(data: ByteArray, maxPayloadBytes: Long = 250_000_000L): PackIndex {
            if (data.size > maxPayloadBytes) fail("payload exceeds installed index budget")
            if (data.size < HEADER + 4) fail("payload too short")
            val bb = ByteBuffer.wrap(data).order(ByteOrder.LITTLE_ENDIAN)
            val magic = ByteArray(8).also { bb.get(it) }
            if (!magic.contentEquals(MAGIC)) fail("bad magic")
            if (bb.short.toInt() != 1) fail("bad version")
            val dBytes = bb.short.toInt() and 0xFFFF
            val n = bb.int.toLong() and 0xFFFFFFFFL
            val nWorks = bb.int.toLong() and 0xFFFFFFFFL
            val interval = bb.double
            if (dBytes != 8) fail("only 8-byte hash descriptors are supported by this engine")
            if (n > MAX_VECTORS || nWorks > 1_000_000) fail("count out of bounds")
            if (!(interval >= 0.1 && interval <= 60.0)) fail("sampling interval out of bounds")
            val metaLen = bb.int.toLong() and 0xFFFFFFFFL
            if (metaLen > MAX_META || bb.remaining() < metaLen) fail("bad metadata length")
            val metaBytes = ByteArray(metaLen.toInt()).also { bb.get(it) }
            val metaText = Charsets.UTF_8.newDecoder().decode(ByteBuffer.wrap(metaBytes)).toString()
            val meta = MiniJson.parse(metaText) as? Map<*, *> ?: fail("metadata not an object")

            val fmt = meta["index_format_version"] as? String
            if (fmt != FORMAT_V3 && fmt != FORMAT_V4) fail("incompatible index format version")
            val v4 = fmt == FORMAT_V4
            if (meta.keys != (if (v4) META_KEYS_V3 + "shared_scenes" else META_KEYS_V3)) fail("metadata keys mismatch")
            for (k in listOf("generator_version", "preprocessing_version", "family")) text(meta[k], k)
            if (meta["family"] != "DACDHASH") fail("this engine only accepts DACDHASH packs")
            if (meta["preprocessing_version"] != EXACT_PREPROCESSING) fail("preprocessing version does not match the descriptor family")

            val worksRaw = meta["works"] as? List<*> ?: fail("work table mismatch")
            if (worksRaw.size.toLong() != nWorks) fail("work table mismatch")
            val workKeys = if (v4) WORK_KEYS_V3 + "aliases" else WORK_KEYS_V3
            val works = ArrayList<Recognition.WorkEntry>()
            val names = ArrayList<Map<String, String>>()
            val aliases = ArrayList<List<String>>()
            val durations = ArrayList<DoubleArray>()
            val seenIds = HashSet<String>()
            val seenEpisodes = HashSet<Pair<String, String>>()
            for ((i, w) in worksRaw.withIndex()) {
                val m = w as? Map<*, *> ?: fail("bad work entry")
                if (m.keys != workKeys) fail("bad work entry")
                if (int(m["work_index"], "work_index") != i.toLong()) fail("work_index out of order")
                val wid = m["work_id"] as? String ?: fail("bad work_id")
                if (!ID.matches(wid)) fail("bad work_id")
                if (!seenIds.add(wid)) fail("duplicate work_id")
                text(m["synthetic_title"], "synthetic_title")
                val eds = m["editions"] as? List<*> ?: fail("bad editions")
                if (eds.isEmpty() || eds.size > 16) fail("bad editions")
                val edIds = eds.map { (it as? String)?.takeIf { s -> EDITION.matches(s) } ?: fail("bad or duplicate edition id") }
                if (edIds.toSet().size != edIds.size) fail("bad or duplicate edition id")
                val durs = m["durations_s"] as? List<*> ?: fail("durations/editions mismatch")
                if (durs.size != edIds.size) fail("durations/editions mismatch")
                val d = DoubleArray(durs.size) { k ->
                    val x = number(durs[k], "duration")
                    if (!x.isFinite() || !(x > 0.0 && x <= 1e6)) fail("bad duration")
                    x
                }
                val sid = m["series_id"]
                if (sid != null && (sid !is String || !ID.matches(sid))) fail("bad series_id")
                val eid = m["episode_id"]
                if (eid != null) {
                    if (sid == null) fail("episode_id without series_id")
                    if (eid !is String || !EPISODE.matches(eid)) fail("bad episode_id")
                    if (!seenEpisodes.add((sid as String) to eid)) fail("duplicate episode")
                }
                val nm = m["names"] as? Map<*, *> ?: fail("bad names table")
                if (nm.size > 16) fail("bad names table")
                val nameMap = LinkedHashMap<String, String>()
                for ((k, v) in nm) {
                    val key = k as? String ?: fail("bad locale tag")
                    if (!LOCALE.matches(key)) fail("bad locale tag")
                    nameMap[key] = text(v, "display name")
                }
                val al = if (v4) {
                    val a = m["aliases"] as? List<*> ?: fail("bad aliases")
                    if (a.size > 32) fail("bad aliases")
                    val list = a.map { text(it, "alias") }
                    if (list.toSet().size != list.size) fail("duplicate alias")
                    list
                } else emptyList()
                works += Recognition.WorkEntry(i, wid, sid as String?, eid as String?, edIds)
                names += nameMap; aliases += al; durations += d
            }

            val scenes = ArrayList<SharedScene>()
            if (v4) {
                val raw = meta["shared_scenes"] as? List<*> ?: fail("bad shared_scenes")
                if (raw.size > 10_000) fail("bad shared_scenes")
                val gids = HashSet<String>()
                for (g in raw) {
                    val gm = g as? Map<*, *> ?: fail("bad shared scene")
                    if (gm.keys != setOf("group_id", "members")) fail("bad shared scene")
                    val gid = gm["group_id"] as? String ?: fail("bad shared scene group_id")
                    if (!ID.matches(gid) || !gids.add(gid)) fail("bad or duplicate shared scene group_id")
                    val mem = gm["members"] as? List<*> ?: fail("bad shared scene")
                    if (mem.size < 2 || mem.size > 64) fail("shared scene needs 2..64 members")
                    val members = mem.map { x ->
                        val mm = x as? Map<*, *> ?: fail("bad shared scene member")
                        if (mm.keys != setOf("work_index", "edition_index", "start_ms", "end_ms")) fail("bad shared scene member")
                        val wi = int(mm["work_index"], "member work"); val ei = int(mm["edition_index"], "member edition")
                        val s = int(mm["start_ms"], "member start"); val e = int(mm["end_ms"], "member end")
                        if (wi < 0 || wi >= works.size || ei < 0 || ei >= works[wi.toInt()].editions.size) fail("shared scene references a missing work/edition")
                        val durMs = Math.ceil(durations[wi.toInt()][ei.toInt()] * 1000.0).toLong()
                        if (!(s >= 0 && s < e && e <= durMs)) fail("shared scene interval out of range")
                        SharedSceneMember(wi.toInt(), ei.toInt(), s, e)
                    }
                    scenes += SharedScene(gid, members)
                }
            }

            if (bb.remaining().toLong() != n * 24) fail("body length mismatch")
            val count = n.toInt()
            val hashes = LongArray(count)
            val locs = IntArray(3 * count)
            val seen = HashSet<Long>(count * 2)
            for (i in 0 until count) {
                hashes[i] = bb.long
                val work = bb.int.toLong() and 0xFFFFFFFFL
                val edition = bb.short.toInt() and 0xFFFF
                val tMs = bb.int.toLong() and 0xFFFFFFFFL
                val segment = bb.short.toInt() and 0xFFFF
                val reserved = bb.int
                if (work >= works.size) fail("locator references unknown work")
                if (edition >= works[work.toInt()].editions.size) fail("locator references unknown edition")
                if (tMs > Math.ceil(durations[work.toInt()][edition] * 1000.0).toLong()) fail("locator time beyond the edition duration")
                if (segment != 0 || reserved != 0) fail("locator segment/reserved fields must be zero")
                if (!seen.add((work shl 40) or (edition.toLong() shl 32) or tMs)) fail("duplicate locator")
                locs[3 * i] = work.toInt(); locs[3 * i + 1] = edition; locs[3 * i + 2] = tMs.toInt()
            }
            return PackIndex(fmt, interval, hashes, locs, works, names, aliases, scenes)
        }
    }
}

/** Minimal bounded JSON reader (objects, arrays, strings, numbers, true/false/null). Rejects
 *  duplicate keys and NaN/Infinity, like the Python strict loader. Integers -> Long, others -> Double. */
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
                else -> if (c == '-' || c.isDigit()) num() else throw IllegalArgumentException("bad token at $i")
            }
        }
        fun lit(w: String, v: Any?): Any? { require(s.startsWith(w, i)) { "bad literal" }; i += w.length; return v }
        fun num(): Any {
            val st = i
            while (i < s.length && (s[i].isDigit() || s[i] in "+-.eE")) i++
            val t = s.substring(st, i)
            require(Regex("-?(0|[1-9][0-9]*)(\\.[0-9]+)?([eE][+-]?[0-9]+)?").matches(t)) { "bad number" }
            if (!t.contains('.') && !t.contains('e') && !t.contains('E')) t.toLongOrNull()?.let { return it }
            val d = t.toDouble()
            require(d.isFinite()) { "number out of range" }
            return d
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
                        require(i < s.length) { "bad escape" }
                        when (val e = s[i++]) {
                            '"', '\\', '/' -> sb.append(e)
                            'b' -> sb.append('\b'); 'f' -> sb.append('\u000C'); 'n' -> sb.append('\n'); 'r' -> sb.append('\r'); 't' -> sb.append('\t')
                            'u' -> { require(i + 4 <= s.length) { "bad escape" }; sb.append(s.substring(i, i + 4).toInt(16).toChar()); i += 4 }
                            else -> throw IllegalArgumentException("bad escape")
                        }
                    }
                    else -> { require(c.code >= 0x20) { "control character in string" }; sb.append(c) }
                }
                require(sb.length <= 1_000_000) { "string too long" }
            }
        }
        fun arr(d: Int): List<Any?> {
            i++; val out = ArrayList<Any?>(); ws()
            require(i < s.length) { "unexpected end" }
            if (s[i] == ']') { i++; return out }
            while (true) {
                out += value(d + 1); ws()
                require(i < s.length) { "unexpected end" }
                when (s[i++]) { ',' -> continue; ']' -> return out; else -> throw IllegalArgumentException("bad array") }
            }
        }
        fun obj(d: Int): Map<String, Any?> {
            i++; val out = LinkedHashMap<String, Any?>(); ws()
            require(i < s.length) { "unexpected end" }
            if (s[i] == '}') { i++; return out }
            while (true) {
                ws(); require(i < s.length && s[i] == '"') { "bad key" }
                val k = str(); ws(); require(i < s.length && s[i++] == ':') { "missing colon" }
                require(!out.containsKey(k)) { "duplicate key" }
                out[k] = value(d + 1); ws()
                require(i < s.length) { "unexpected end" }
                when (s[i++]) { ',' -> continue; '}' -> return out; else -> throw IllegalArgumentException("bad object") }
            }
        }
    }
}
