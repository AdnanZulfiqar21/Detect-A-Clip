package ai.detectaclip.lab

import java.nio.ByteBuffer
import java.time.OffsetDateTime

/**
 * Framework-neutral runner for every committed golden file, shared by the JVM unit tests and
 * the instrumented test that runs the same engine on Android's ART runtime (EngineOnArtTest).
 * Each check returns a [Report]; nothing here depends on JUnit or on the file system, the
 * caller supplies the golden lines (files on the JVM, APK assets on Android).
 */
object GoldenRunner {
    data class Report(val name: String, val cases: Int, val mismatches: List<String>, val elapsedMs: Long = 0) {
        val ok: Boolean get() = mismatches.isEmpty()
        override fun toString() = "$name: $cases cases, ${mismatches.size} mismatches, $elapsedMs ms" +
            (if (mismatches.isEmpty()) "" else "\n  " + mismatches.take(10).joinToString("\n  "))
    }

    fun hex(s: String) = ByteArray(s.length / 2) { s.substring(2 * it, 2 * it + 2).toInt(16).toByte() }

    private fun body(lines: List<String>) = lines.filter { it.isNotBlank() && !it.startsWith("#") }

    private fun thresholds(t: List<String>) = Recognition.Thresholds(
        minQualifiedFrames = t[1].toInt(), verifiedMinSupport = t[2].toInt(), verifiedMinSupportFraction = t[3].toDouble(),
        verifiedMinSpanMs = t[4].toInt(), verifiedMaxMeanDistFrac = t[5].toDouble(), verifiedMinMargin = t[6].toInt(),
        possibleMinSupport = t[7].toInt(), possibleMinSpanMs = t[8].toInt(), possibleMaxMeanDistFrac = t[9].toDouble(),
        possibleOnCompetition = t[10] == "1", episodeMargin = t[11].toInt(), radius = t[12].toDouble(),
    )

    fun decisionLine(r: Recognition.Decision): String {
        val segs = r.segments.joinToString("|") { s ->
            "${s.workId}@${s.editionId ?: "-"}@${s.queryStartMs}@${s.queryEndMs}@${s.referenceOffsetMs ?: "-"}@${s.supportingFrames}"
        }.ifEmpty { "-" }
        return "R ${r.state} ${r.workId ?: "-"} ${r.editionId ?: "-"} ${r.episodeId ?: "-"} ${r.flags.joinToString(",").ifEmpty { "-" }} $segs"
    }

    /** Python repr and Kotlin may print the same double differently; compare field 5 by value. */
    private fun normaliseDoubles(line: String): String {
        val p = line.split(" ").toMutableList()
        p[5] = java.lang.Double.toString(p[5].toDouble())
        return p.joinToString(" ")
    }

    // ---------------------------------------------------------------- golden_recognition.txt (verify + decide)
    fun recognition(raw: List<String>): Report {
        val lines = body(raw); val t0 = System.nanoTime()
        var i = 0
        val nWorks = lines[i++].removePrefix("WORKS ").toInt()
        val works = (0 until nWorks).map {
            val p = lines[i++].split(" ")
            Recognition.WorkEntry(p[1].toInt(), p[2], p[3].takeIf { s -> s != "-" }, p[4].takeIf { s -> s != "-" }, p[5].split(","))
        }
        val mismatches = ArrayList<String>(); var cases = 0
        while (i < lines.size) {
            val header = lines[i++]; check(header.startsWith("CASE ")) { header }
            val f = lines[i++].split(" ")
            val frames = Recognition.FrameSummary(f[1].toInt(), f[2].toInt(), f[3].toInt())
            val th = thresholds(lines[i++].split(" "))
            val perFrame = ArrayList<Pair<Int, List<Recognition.Candidate>>>()
            while (lines[i].startsWith("PF ")) {
                val p = lines[i++].split(" ")
                val cands = if (p[2] == "-") emptyList() else p[2].split(";").map { c ->
                    val q = c.split(":")
                    Recognition.Candidate(Recognition.Locator(q[0].toInt(), q[1].toInt(), q[2].toInt()), q[3].toDouble())
                }
                perFrame += p[1].toInt() to cands
            }
            val expectedH = ArrayList<String>()
            while (lines[i].startsWith("H ")) expectedH += lines[i++]
            val expectedR = lines[i++]
            check(lines[i++] == "END")
            val hyps = Recognition.verify(perFrame, 2000)
            val gotH = hyps.map { h ->
                "H ${h.work} ${h.edition ?: -1} ${h.offsetMs} ${h.support} ${h.meanDistance} ${h.queryStartMs} ${h.queryEndMs} " +
                    (h.ambiguousEditions.joinToString(",").ifEmpty { "-" })
            }
            if (expectedH.map(::normaliseDoubles) != gotH.map(::normaliseDoubles)) mismatches += "$header hypotheses"
            val gotR = decisionLine(Recognition.decide(hyps, frames, works, th))
            if (gotR != expectedR) mismatches += "$header: $gotR vs $expectedR"
            cases++
        }
        return Report("recognition", cases, mismatches, (System.nanoTime() - t0) / 1_000_000)
    }

    // ---------------------------------------------------------------- golden_dac_dhash_v1.txt
    fun dacDhash(raw: List<String>): Report {
        val t0 = System.nanoTime(); val mismatches = ArrayList<String>(); var n = 0
        for (line in body(raw)) {
            val p = line.split(" ")
            val seed = p[1].toInt(); val w = p[2].toInt(); val h = p[3].toInt()
            val expected = java.lang.Long.parseUnsignedLong(p[4], 16)
            val got = DacDhash.hash(DacDhash.testFrame(seed, w, h), w, h)
            if (got != expected) mismatches += "seed=$seed ${w}x$h: %016x vs %016x".format(got, expected)
            n++
        }
        return Report("dac_dhash", n, mismatches, (System.nanoTime() - t0) / 1_000_000)
    }

    // ---------------------------------------------------------------- golden_exact.txt
    private fun composeExact(w: Int, h: Int, seed: Int, iw: Int, ih: Int, ox: Int, oy: Int, bg: Int, bx: Int, by: Int): ByteArray {
        val out = ByteArray(w * h * 3) { bg.toByte() }
        if (iw > 0 && ih > 0) {
            val c = DacDhash.contentFrame(seed, iw, ih, bx, by)
            for (y in 0 until ih) for (x in 0 until iw) for (ch in 0 until 3) out[((oy + y) * w + ox + x) * 3 + ch] = c[(y * iw + x) * 3 + ch]
        }
        return out
    }

    fun exact(raw: List<String>): Report {
        val lines = body(raw); val t0 = System.nanoTime()
        val size = lines[0].split(" "); val w = size[1].toInt(); val h = size[2].toInt()
        val mismatches = ArrayList<String>(); var n = 0
        for (line in lines.drop(1)) {
            val p = line.split(" ")
            val seed = p[2].toInt()
            val a = p.subList(3, 10).map { it.toInt() }
            var prev: LongArray? = null
            val rects = ArrayList<String>(); val flags = ArrayList<String>(); val hashes = ArrayList<String>()
            for (s in listOf(seed, seed, seed + 1000)) {
                val f = composeExact(w, h, s, a[0], a[1], a[2], a[3], a[4], a[5], a[6])
                val y = DacDhash.luma(f, w, h)
                val r = DacDhash.cropRect(y, w, h)
                val (flag, means) = DacDhash.quality(y, w, r, prev)
                if (flag == "OK") prev = means
                rects += r.joinToString(","); flags += flag
                hashes += "%016x:%016x".format(DacDhash.dhashRegion(y, w, r), DacDhash.dhashRegion(y, w, r, mirrored = true))
            }
            val got = "${rects.joinToString("/")} ${flags.joinToString("/")} ${hashes.joinToString("/")}"
            if (got != "${p[10]} ${p[11]} ${p[12]}") mismatches += "${p[1]}: $got"
            n++
        }
        return Report("exact", n, mismatches, (System.nanoTime() - t0) / 1_000_000)
    }

    // ---------------------------------------------------------------- golden_e2e.txt
    fun e2e(raw: List<String>): Report {
        val lines = body(raw); val t0 = System.nanoTime()
        val pack = PackIndex.parse(hex(lines[0].removePrefix("PACKHEX ")))
        val t = lines[1].split(" "); val th = thresholds(t); val topK = t[13].toInt()
        val rest = lines.drop(2)
        val mismatches = ArrayList<String>(); var i = 0; var queries = 0
        while (i < rest.size) {
            val q = rest[i++].split(" "); val n = q[2].toInt()
            val perFrame = ArrayList<Pair<Int, List<Recognition.Candidate>>>()
            repeat(n) {
                val f = rest[i++].split(" ")
                var frame = DacDhash.contentFrame(f[2].toInt(), 64, 36)
                val b = f[3].toInt()
                if (b != 0) frame = ByteArray(frame.size) { ((frame[it].toInt() and 0xFF) + b).coerceIn(0, 255).toByte() }
                perFrame += f[1].toInt() to pack.search(DacDhash.hash(frame, 64, 36), topK, th.radius)
            }
            val expected = rest[i++]
            val hyps = Recognition.verify(perFrame, (pack.samplingIntervalS * 1000).toInt())
            val got = decisionLine(Recognition.decide(hyps, Recognition.FrameSummary(n, n, 0), pack.works, th))
            if (got != expected) mismatches += "${q[1]}: $got vs $expected"
            queries++
        }
        return Report("e2e", queries, mismatches, (System.nanoTime() - t0) / 1_000_000)
    }

    // ---------------------------------------------------------------- golden_format_cases.txt (+ DISPLAY rows)
    fun format(raw: List<String>): Report {
        val t0 = System.nanoTime(); val mismatches = ArrayList<String>(); var n = 0
        var v4: PackIndex? = null
        for (line in raw) {
            if (!line.startsWith("CASE ")) continue
            val p = line.split(" ")
            val parsed = try { PackIndex.parse(hex(p[3])) } catch (e: IllegalArgumentException) { null } catch (e: java.nio.charset.CharacterCodingException) { null }
            if ((parsed != null) != (p[2] == "ACCEPT")) mismatches += "${p[1]}: expected ${p[2]}"
            if (p[1] == "valid_v5_series_names_aliases_shared_scene") v4 = parsed
            n++
        }
        val pack = v4 ?: error("v5 sample pack missing")
        for (line in raw) {
            if (!line.startsWith("DISPLAY ")) continue
            val c = line.split(" ")
            val prefs = if (c[3] == "-") emptyList() else c[3].split(",")
            val expected = if (c[4] == "-") null else String(hex(c[4]), Charsets.UTF_8)
            val got = pack.resultDisplayName(c[1].takeIf { it != "-" }, c[2].takeIf { it != "-" }, prefs)
            if (got != expected) mismatches += "$line: got $got"
            n++
        }
        return Report("format", n, mismatches, (System.nanoTime() - t0) / 1_000_000)
    }

    // ---------------------------------------------------------------- golden_manifest_cases.txt (Ed25519 through the platform)
    fun manifest(raw: List<String>): Report {
        val t0 = System.nanoTime()
        val pub = raw.first { it.startsWith("PUBKEY ") }.split(" ")
        val payloads = raw.filter { it.startsWith("PAYLOAD ") }.associate { val p = it.split(" "); p[1] to hex(p[2]) }
        val mismatches = ArrayList<String>(); var n = 0
        for (line in raw.filter { it.startsWith("CASE ") }) {
            val p = line.split(" ")
            val kv = p.drop(3).associate { it.substringBefore("=") to it.substringAfter("=") }
            val st = PackLoader.DeviceRightsState().apply {
                minimumRightsEpoch = kv.getValue("epoch").toLong()
                trustedKeys[pub[1]] = hex(pub[2])
                if (kv["revoked"] == "1") revokedKeyIds += pub[1]
                if (kv["floors"] != "-") for (item in kv.getValue("floors").split(",")) {
                    minimumPackVersions[item.substringBefore(":")] = PackLoader.parseVersion(item.substringAfter(":"), "floor")
                }
            }
            val before = Triple(st.minimumRightsEpoch, HashMap(st.installedIndexBytes), HashMap(st.minimumPackVersions))
            val now = kv["now"]?.takeIf { it != "UNTRUSTED" }?.let { OffsetDateTime.parse(it) }
            val accepted = try {
                PackLoader(st).load(hex(kv.getValue("manifest")), hex(kv.getValue("sig")), payloads.getValue(kv.getValue("payload")), now, kv["release"] == "1")
                true
            } catch (e: PackLoader.Rejected) { false }
            if (accepted != (p[2] == "ACCEPT")) mismatches += "${p[1]}: expected ${p[2]}"
            if (!accepted && before != Triple(st.minimumRightsEpoch, HashMap(st.installedIndexBytes), HashMap(st.minimumPackVersions)))
                mismatches += "${p[1]}: state changed on rejection"
            n++
        }
        return Report("manifest", n, mismatches, (System.nanoTime() - t0) / 1_000_000)
    }

    /** Which provider (if any) serves Ed25519 on this runtime; null when unavailable. */
    fun ed25519Provider(): String? = try { java.security.Signature.getInstance("Ed25519").provider.name } catch (e: Exception) { null }

    // ---------------------------------------------------------------- golden_pipeline.txt (full device path)
    private fun scaleNearest(src: ByteArray, w: Int, h: Int, nw: Int, nh: Int): ByteArray {
        val out = ByteArray(nw * nh * 3)
        for (y in 0 until nh) for (x in 0 until nw) {
            val sy = (y * h) / nh; val sx = (x * w) / nw
            for (c in 0 until 3) out[(y * nw + x) * 3 + c] = src[(sy * w + sx) * 3 + c]
        }
        return out
    }

    private fun place(dst: ByteArray, w: Int, src: ByteArray, sw: Int, sh: Int, ox: Int, oy: Int) {
        for (y in 0 until sh) System.arraycopy(src, y * sw * 3, dst, ((oy + y) * w + ox) * 3, sw * 3)
    }

    fun compose(seed: Int, variant: String, bright: Int, w: Int, h: Int): ByteArray {
        if (variant == "black") return ByteArray(w * h * 3)
        val c = DacDhash.contentFrame(seed, w, h)
        var out = when (variant) {
            "full" -> c
            "mirror" -> ByteArray(c.size).also { o -> for (y in 0 until h) for (x in 0 until w) for (k in 0 until 3) o[(y * w + x) * 3 + k] = c[(y * w + (w - 1 - x)) * 3 + k] }
            "letterbox" -> ByteArray(w * h * 3).also { place(it, w, scaleNearest(c, w, h, w, 26), w, 26, 0, 5) }
            "pillarbox" -> ByteArray(w * h * 3).also { place(it, w, scaleNearest(c, w, h, 48, h), 48, h, 8, 0) }
            "pip" -> ByteArray(w * h * 3) { 235.toByte() }.also { o ->
                for (i in 0 until 5 * w * 3) o[i] = 60
                place(o, w, scaleNearest(c, w, h, 40, 22), 40, 22, 12, 9)
            }
            else -> error(variant)
        }
        if (bright != 0) out = ByteArray(out.size) { ((out[it].toInt() and 0xFF) + bright).coerceIn(0, 255).toByte() }
        return out
    }

    /** RGB -> padded RGBA plane (rowStride > width * 4), like an ImageReader plane. */
    fun toPaddedRgba(rgb: ByteArray, w: Int, h: Int, pad: Int): Pair<ByteBuffer, Int> {
        val rowStride = w * 4 + pad
        val buf = ByteBuffer.allocateDirect(rowStride * h)
        for (y in 0 until h) for (x in 0 until w) {
            val p = y * rowStride + x * 4
            buf.put(p, rgb[(y * w + x) * 3]); buf.put(p + 1, rgb[(y * w + x) * 3 + 1]); buf.put(p + 2, rgb[(y * w + x) * 3 + 2]); buf.put(p + 3, -1)
            if (x == w - 1) for (k in 0 until pad) buf.put(y * rowStride + w * 4 + k, 0x5A)
        }
        return buf to rowStride
    }

    data class PipelineTiming(val frames: Int, val perFrameUs: Long, val finishUs: Long)

    fun pipeline(raw: List<String>, timing: MutableList<PipelineTiming>? = null): Report {
        val lines = body(raw); val t0 = System.nanoTime()
        val size = lines[0].split(" "); val w = size[1].toInt(); val h = size[2].toInt()
        val pack = PackIndex.parse(hex(lines[1].removePrefix("PACKHEX ")))
        val t = lines[2].split(" "); val th = thresholds(t); val topK = t[13].toInt()
        var i = 3; var queries = 0
        val mismatches = ArrayList<String>()
        while (i < lines.size) {
            val q = lines[i++].split(" "); val n = q[2].toInt()
            val selector = FrameSelector()
            val session = RecognitionSession(pack, th, topK, mirrorInvariant = true)
            var offered = 0; var frameNs = 0L; var processed = 0
            repeat(n) {
                val f = lines[i++].split(" ")
                val ts = f[1].toLong()
                offered += 1
                if (selector.offer(ts)) {
                    try {
                        val (buf, stride) = toPaddedRgba(compose(f[2].toInt(), f[3], f[4].toInt(), w, h), w, h, pad = 12)
                        val a = System.nanoTime()
                        val luma = FrameView(buf, w, h, stride, 4).toLuma()
                        session.process(ts, luma, w, h)
                        frameNs += System.nanoTime() - a; processed++
                    } finally { selector.release() }
                }
            }
            selector.close()
            val s = lines[i++]
            val expectedR = lines[i++]
            val a = System.nanoTime()
            val d = session.finish { false }!!
            val finishNs = System.nanoTime() - a
            timing?.add(PipelineTiming(processed, if (processed > 0) frameNs / processed / 1000 else 0, finishNs / 1000))
            val gotS = "S $offered ${session.selected} ${session.qualified} ${session.unusable}"
            if (gotS != s) mismatches += "${q[1]} summary: $gotS vs $s"
            val gotR = decisionLine(d)
            if (gotR != expectedR) mismatches += "${q[1]}: $gotR vs $expectedR"
            queries++
        }
        return Report("pipeline", queries, mismatches, (System.nanoTime() - t0) / 1_000_000)
    }

    val expectedCounts = mapOf("recognition" to 400, "dac_dhash" to 42, "exact" to 9, "e2e" to 6, "format" to 75, "manifest" to 68, "pipeline" to 12)
}
