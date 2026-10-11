package ai.detectaclip.lab

/**
 * Pure-Kotlin port of the reference temporal verification and decision policy
 * (l0/dac_l0/verify.py and l0/dac_l0/decision.py, ED-11). Must reproduce the Python outputs
 * exactly on the golden vectors (`RecognitionGoldenTest`): same ordering rules (insertion
 * order + stable sorts), same float operations in the same order.
 *
 * Descriptor extraction is NOT ported here: it depends on OpenCV blur/resize semantics and
 * needs a platform-exact descriptor spec before device work (P04-T08).
 *
 * No result carries an image, frame or descriptor. OUTSIDE_CATALOGUE is not representable.
 */
object Recognition {

    data class Locator(val work: Int, val edition: Int, val tMs: Int)
    data class Candidate(val locator: Locator, val distance: Double)

    class Hypothesis(
        val work: Int,
        var edition: Int?,
        val offsetMs: Int,
        val support: Int,
        val meanDistance: Double,
        val queryStartMs: Int,
        val queryEndMs: Int,
        var ambiguousEditions: List<Int> = emptyList(),
    ) {
        val spanMs: Int get() = queryEndMs - queryStartMs
    }

    data class WorkEntry(val index: Int, val workId: String, val seriesId: String?, val episodeId: String?, val editions: List<String>)

    data class Thresholds(
        val minQualifiedFrames: Int = 4,
        val verifiedMinSupport: Int = 6,
        val verifiedMinSupportFraction: Double = 0.5,
        val verifiedMinSpanMs: Int = 2500,
        val verifiedMaxMeanDistFrac: Double = 0.8,
        val verifiedMinMargin: Int = 3,
        val possibleMinSupport: Int = 3,
        val possibleMinSpanMs: Int = 1000,
        val possibleMaxMeanDistFrac: Double = 0.9,
        val possibleOnCompetition: Boolean = false,
        val episodeMargin: Int = 3,
        val radius: Double = 9.0,
    )

    data class FrameSummary(val selected: Int, val qualified: Int, val unusable: Int)

    enum class State { VERIFIED_MATCH, POSSIBLE_MATCH, NO_CONFIDENT_MATCH, INSUFFICIENT_SIGNAL, UNSUPPORTED_CAPTURE, PERMISSION_DENIED, CANCELLED, ERROR }

    data class Segment(val workId: String, val editionId: String?, val queryStartMs: Int, val queryEndMs: Int, val referenceOffsetMs: Int?, val supportingFrames: Int)

    data class Decision(
        val state: State,
        val workId: String?,
        val editionId: String?,
        val episodeId: String?,
        val flags: List<String>,
        val segments: List<Segment>,
    ) {
        init {
            val match = state == State.VERIFIED_MATCH || state == State.POSSIBLE_MATCH
            require(match == (workId != null)) { "match states need a candidate; others must not name one" }
        }
    }

    // ------------------------------------------------------------------ verification

    private data class Pair3(val qt: Int, val off: Int, val d: Double)

    private fun clusterOffsets(pairs: List<Pair3>, tolMs: Int): kotlin.Pair<Int, List<Pair3>> {
        var bestCentre = 0
        var best: List<Pair3> = emptyList()
        val offs = pairs.map { it.off }.toSortedSet()
        for (c in offs) {
            val members = LinkedHashMap<Int, Pair3>()
            for (p in pairs) {
                if (kotlin.math.abs(p.off - c) <= tolMs) {
                    val prev = members[p.qt]
                    if (prev == null || p.d < prev.d) members[p.qt] = p
                }
            }
            if (members.size > best.size) { bestCentre = c; best = members.values.toList() }
        }
        return kotlin.Pair(bestCentre, best)
    }

    private val hypOrder = compareBy<Hypothesis>({ -it.support }, { it.meanDistance })

    fun verify(perFrame: List<kotlin.Pair<Int, List<Candidate>>>, samplingIntervalMs: Int, minSupport: Int = 2, editionMargin: Int = 3): List<Hypothesis> {
        val tol = samplingIntervalMs / 2 + 250
        val byWe = LinkedHashMap<kotlin.Pair<Int, Int>, MutableList<Pair3>>()
        for ((qt, cands) in perFrame) for (c in cands) {
            byWe.getOrPut(kotlin.Pair(c.locator.work, c.locator.edition)) { ArrayList() }.add(Pair3(qt, c.locator.tMs - qt, c.distance))
        }
        val raw = ArrayList<Hypothesis>()
        for ((we, pairs) in byWe) {
            val (centre, members) = clusterOffsets(pairs, tol)
            if (members.size < minSupport) continue
            var sum = 0.0
            for (m in members) sum += m.d
            raw += Hypothesis(we.first, we.second, centre, members.size, sum / members.size, members.minOf { it.qt }, members.maxOf { it.qt })
        }
        val byWork = LinkedHashMap<Int, MutableList<Hypothesis>>()
        for (h in raw) byWork.getOrPut(h.work) { ArrayList() }.add(h)
        val merged = ArrayList<Hypothesis>()
        for ((_, hs0) in byWork) {
            val hs = hs0.sortedWith(hypOrder)
            val top = hs[0]
            val tied = hs.filter { it.support > top.support - editionMargin && it.edition != top.edition }
            if (tied.isNotEmpty()) {
                top.ambiguousEditions = (listOf(top.edition!!) + tied.map { it.edition!! }).toSortedSet().toList()
                top.edition = null
            }
            merged += top
        }
        return merged.sortedWith(hypOrder)
    }

    fun segmentMontage(hyps: List<Hypothesis>, minSupport: Int = 3): List<Hypothesis> {
        val segments = ArrayList<Hypothesis>()
        for (h in hyps.filter { it.support >= minSupport }) {
            var overlap = false
            for (s in segments) {
                val lo = maxOf(h.queryStartMs, s.queryStartMs)
                val hi = minOf(h.queryEndMs, s.queryEndMs)
                if (hi - lo > 0.5 * maxOf(1, minOf(h.queryEndMs - h.queryStartMs, s.queryEndMs - s.queryStartMs))) { overlap = true; break }
            }
            if (!overlap) segments += h
        }
        return segments.sortedBy { it.queryStartMs }
    }

    // ----------------------------------------------------------------------- decision

    fun decide(hyps: List<Hypothesis>, frames: FrameSummary, works: List<WorkEntry>, th: Thresholds, entitlementOk: Boolean = true): Decision {
        fun plain(s: State, f: List<String>) = Decision(s, null, null, null, f, emptyList())
        if (!entitlementOk) return plain(State.ERROR, listOf("ENTITLEMENT_RECHECK_FAILED"))
        if (frames.selected > 0 && frames.unusable == frames.selected) return plain(State.UNSUPPORTED_CAPTURE, listOf("ALL_FRAMES_BLANK"))
        if (frames.qualified < th.minQualifiedFrames) return plain(State.INSUFFICIENT_SIGNAL, listOf("QUALIFIED_FRAMES=${frames.qualified}"))
        if (hyps.isEmpty()) return plain(State.NO_CONFIDENT_MATCH, emptyList())

        fun groupKey(h: Hypothesis): String {
            val w = works[h.work]
            return if (w.seriesId != null) "SERIES:${w.seriesId}" else "WORK:${w.workId}"
        }
        fun strong(h: Hypothesis, minSupport: Int, minSpan: Int, maxFrac: Double) =
            h.support >= minSupport && h.spanMs >= minSpan && h.meanDistance <= maxFrac * th.radius

        val groups = LinkedHashMap<String, MutableList<Hypothesis>>()
        for (h in hyps) groups.getOrPut(groupKey(h)) { ArrayList() }.add(h)
        val sortedGroups = groups.entries.map { it.key to it.value.sortedWith(hypOrder) }
        val ranked = sortedGroups.sortedWith(compareBy({ -it.second[0].support }, { it.second[0].meanDistance }))
        val topList = ranked[0].second
        val top = topList[0]
        val competitor = if (ranked.size > 1) ranked[1].second[0] else null
        val margin = top.support - (competitor?.support ?: 0)

        val flags = ArrayList<String>()
        val segments = segmentMontage(hyps, th.possibleMinSupport)
        val montage = segments.map { groupKey(it) }.toSet().size > 1
        val competing = competitor != null && margin < th.verifiedMinMargin && !montage

        val tw = works[top.work]
        var episodeAmbiguous = false
        if (tw.seriesId != null) {
            episodeAmbiguous = topList.drop(1).any { it.work != top.work && it.support > top.support - th.episodeMargin }
        }
        if (top.ambiguousEditions.isNotEmpty()) flags += "EDITION_AMBIGUOUS"
        if (episodeAmbiguous) flags += "EPISODE_AMBIGUOUS"
        if (montage) flags += "MULTI_TITLE_SEGMENTS"
        if (competing) flags += "COMPETING_WORKS"

        fun names(h: Hypothesis, epAmb: Boolean): Triple<String, String?, String?> {
            val w = works[h.work]
            val ed = h.edition?.let { w.editions[it] }
            if (w.seriesId != null) return if (epAmb) Triple(w.seriesId, null, null) else Triple(w.seriesId, ed, w.episodeId)
            return Triple(w.workId, ed, null)
        }
        fun seg(h: Hypothesis, epAmb: Boolean): Segment {
            val (work, ed, _) = names(h, epAmb)
            val uniqueTime = ed != null && !epAmb
            return Segment(work, ed, h.queryStartMs, h.queryEndMs, if (uniqueTime) h.offsetMs else null, h.support)
        }
        fun match(s: State, h: Hypothesis, segs: List<Segment>, extra: List<String>, epAmb: Boolean): Decision {
            val (work, ed, ep) = names(h, epAmb)
            return Decision(s, work, ed, ep, flags + extra, segs)
        }
        fun possibleStrength(h: Hypothesis) = strong(h, th.possibleMinSupport, th.possibleMinSpanMs, th.possibleMaxMeanDistFrac)

        if (montage) {
            val strongSegs = segments.filter { possibleStrength(it) }
            if (strongSegs.isEmpty()) return plain(State.NO_CONFIDENT_MATCH, flags)
            var lead = strongSegs[0]
            for (s in strongSegs) if (s.support > lead.support || (s.support == lead.support && -s.meanDistance > -lead.meanDistance)) lead = s
            return match(State.POSSIBLE_MATCH, lead, strongSegs.map { seg(it, true) }, emptyList(), true)
        }
        val frac = top.support.toDouble() / maxOf(1, frames.selected)
        val verified = !competing &&
            strong(top, th.verifiedMinSupport, th.verifiedMinSpanMs, th.verifiedMaxMeanDistFrac) &&
            frac >= th.verifiedMinSupportFraction && margin >= th.verifiedMinMargin
        if (verified) return match(State.VERIFIED_MATCH, top, listOf(seg(top, episodeAmbiguous)), emptyList(), episodeAmbiguous)
        if (competing && !th.possibleOnCompetition) return plain(State.NO_CONFIDENT_MATCH, flags)
        if (possibleStrength(top)) return match(State.POSSIBLE_MATCH, top, listOf(seg(top, episodeAmbiguous)), listOf("WEAK_SUPPORT"), episodeAmbiguous)
        return plain(State.NO_CONFIDENT_MATCH, flags)
    }
}
