package ai.detectaclip.lab

import java.io.IOException
import java.nio.ByteBuffer
import java.nio.channels.FileChannel
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.StandardCopyOption
import java.nio.file.StandardOpenOption
import java.security.SecureRandom
import java.time.OffsetDateTime

/**
 * Installed pack store for the device (P03-T06, IDX-01, RIGHTS-02), Kotlin port of
 * l0/dac_l0/pack/store.py for manifest V2 packs. Pure java.nio, no Android types, so the same
 * code runs in JVM tests, including abrupt-termination tests that halt a child JVM.
 *
 * Layout under [root] (app-private storage on a device):
 *   staging/<pack_id>.<nonce>/     payload.pack + manifest.json + manifest.sig being validated
 *   packs/<pack_id>/<slot>/        immutable slot
 *   state.json                     COMMIT POINT: per pack {slot, version, bytes}, epoch, floors
 *   floors.json                    second record of epoch/version floors (never lowered)
 *
 * Crash-consistency: a new slot is written next to the old one and nothing state.json names
 * is changed before the commit; the only commit point is the atomic replace of state.json;
 * startup recovery deletes staging leftovers, temp files and unreferenced slots, and fails
 * closed if state.json names a missing slot. [active] re-verifies the slot through
 * [PackLoader] on every load (files are untrusted at rest). Restoring an older state.json
 * cannot lower floors because floors.json is merged by maximum.
 *
 * Not wired into the LAB app yet: the app stays in CAP-A04 DIAGNOSTIC mode (ED-25). Android
 * storage durability (fsync/rename semantics per filesystem) is a device check (B-01).
 */
class PackStore(
    private val root: Path,
    private val rights: PackLoader.DeviceRightsState,
    private val io: Io = Io.Durable,
    private val budgetBytes: Long = PackLoader.DEFAULT_BUDGET,
    private val stagingCapBytes: Long = budgetBytes,
) {
    class StoreError(message: String) : Exception(message)

    /** Injectable file operations; tests inject failures and abrupt termination. */
    interface Io {
        fun writeBytes(p: Path, b: ByteArray)
        fun replace(src: Path, dst: Path)
        fun rmtree(p: Path)
        fun mkdir(p: Path)

        object Durable : Io {
            override fun writeBytes(p: Path, b: ByteArray) {
                FileChannel.open(p, StandardOpenOption.CREATE, StandardOpenOption.WRITE, StandardOpenOption.TRUNCATE_EXISTING).use { ch ->
                    val buf = ByteBuffer.wrap(b)
                    while (buf.hasRemaining()) ch.write(buf)
                    ch.force(true)
                }
            }
            override fun replace(src: Path, dst: Path) {
                Files.move(src, dst, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING)
            }
            override fun rmtree(p: Path) = deleteTree(p)
            override fun mkdir(p: Path) { Files.createDirectories(p) }
        }
    }

    data class Entry(val slot: String, val version: String, val bytes: Long)
    data class State(val epoch: Long, val packs: Map<String, Entry>, val floors: Map<String, Triple<Long, Long, Long>>)

    var state: State; private set
    val recoveryActions: List<String>

    init {
        Files.createDirectories(root.resolve("staging"))
        Files.createDirectories(root.resolve("packs"))
        state = loadState()
        recoveryActions = recover()
        syncRights()
    }

    // ------------------------------------------------------------------ state

    private fun loadState(): State {
        var st = State(0, emptyMap(), emptyMap())
        val p = root.resolve(STATE_FILE)
        if (Files.exists(p)) st = try { parseState(Files.readAllBytes(p)) } catch (e: Exception) {
            throw StoreError("state file corrupt; refusing to guess (revalidation required)")
        }
        val f = root.resolve(FLOORS_FILE)
        if (Files.exists(f)) {
            try {
                val m = MiniJson.parse(String(Files.readAllBytes(f), Charsets.UTF_8)) as Map<*, *>
                val epoch = maxOf(st.epoch, m["minimum_rights_epoch"] as Long)
                val floors = HashMap(st.floors)
                for ((k, v) in m["minimum_pack_versions"] as Map<*, *>) floors[k as String] = maxVersion(floors[k], version(v))
                st = st.copy(epoch = epoch, floors = floors)
            } catch (e: Exception) { throw StoreError("floors file corrupt") }
        }
        return st
    }

    private fun recover(): List<String> {
        val actions = ArrayList<String>()
        list(root.resolve("staging")).forEach { io.rmtree(it); actions += "removed staging ${it.fileName}" }
        for (name in listOf("$STATE_FILE.tmp", "$FLOORS_FILE.tmp")) {
            if (Files.deleteIfExists(root.resolve(name))) actions += "removed $name"
        }
        for (packDir in list(root.resolve("packs"))) {
            val ref = state.packs[packDir.fileName.toString()]?.slot
            for (slot in list(packDir)) if (slot.fileName.toString() != ref) {
                io.rmtree(slot); actions += "removed unreferenced slot ${packDir.fileName}/${slot.fileName}"
            }
            if (ref == null && list(packDir).isEmpty()) Files.deleteIfExists(packDir)
        }
        for ((pid, e) in state.packs) {
            val slot = root.resolve("packs").resolve(pid).resolve(e.slot)
            if (SLOT_FILES.any { !Files.exists(slot.resolve(it)) }) throw StoreError("state references a missing slot for $pid; revalidation required")
        }
        return actions
    }

    /** Device rights state is derived from persisted state, never the other way round. */
    private fun syncRights() {
        rights.minimumRightsEpoch = maxOf(rights.minimumRightsEpoch, state.epoch)
        rights.installedIndexBytes.clear()
        for ((k, e) in state.packs) rights.installedIndexBytes[k] = e.bytes
        for ((k, v) in state.floors) rights.minimumPackVersions[k] = maxVersion(rights.minimumPackVersions[k], v)
    }

    private fun scratchRights(excludePack: String): PackLoader.DeviceRightsState = PackLoader.DeviceRightsState().also { s ->
        s.minimumRightsEpoch = rights.minimumRightsEpoch
        for ((k, v) in rights.installedIndexBytes) if (k != excludePack) s.installedIndexBytes[k] = v
        s.minimumPackVersions.putAll(rights.minimumPackVersions)
        s.acceptedRegionMethods.clear(); s.acceptedRegionMethods.addAll(rights.acceptedRegionMethods)
        s.trustedKeys.putAll(rights.trustedKeys)
        s.revokedKeyIds.addAll(rights.revokedKeyIds)
    }

    private fun commit(st: State) {
        val tmp = root.resolve("$STATE_FILE.tmp")
        io.writeBytes(tmp, stateJson(st))
        io.replace(tmp, root.resolve(STATE_FILE))                 // <- the commit point
        val ftmp = root.resolve("$FLOORS_FILE.tmp")
        io.writeBytes(ftmp, floorsJson(st))
        io.replace(ftmp, root.resolve(FLOORS_FILE))
    }

    // ------------------------------------------------------------------ install / load

    fun install(manifest: ByteArray, signature: ByteArray, payload: ByteArray, now: OffsetDateTime?, releaseMode: Boolean = false): PackLoader.Loaded {
        if (payload.size.toLong() + manifest.size + signature.size > stagingCapBytes) throw PackLoader.Rejected("staging cap exceeded")
        val packId = try {
            (MiniJson.parse(Charsets.UTF_8.newDecoder().decode(ByteBuffer.wrap(manifest)).toString()) as Map<*, *>)["pack_id"] as? String
        } catch (e: Exception) { null } ?: throw PackLoader.Rejected("manifest not readable")
        if (!PACK_ID.matches(packId)) throw PackLoader.Rejected("bad pack_id")
        val stage = root.resolve("staging").resolve("$packId.${hex(4)}")
        io.mkdir(stage)
        try {
            io.writeBytes(stage.resolve(PAYLOAD), payload)
            io.writeBytes(stage.resolve(MANIFEST), manifest)
            io.writeBytes(stage.resolve(SIGNATURE), signature)
            // Validate exactly what was written, against a scratch copy of the rights state.
            val loaded = PackLoader(scratchRights(packId)).load(
                Files.readAllBytes(stage.resolve(MANIFEST)), Files.readAllBytes(stage.resolve(SIGNATURE)),
                Files.readAllBytes(stage.resolve(PAYLOAD)), now, releaseMode, budgetBytes)
            val slot = hex(8)
            Files.createDirectories(root.resolve("packs").resolve(packId))
            io.replace(stage, root.resolve("packs").resolve(packId).resolve(slot))   // new immutable slot
            val declaredMin = PackLoader.parseVersion(loaded.manifest["minimum_allowed_version"], "minimum_allowed_version")
            val newState = State(
                maxOf(state.epoch, loaded.manifest["rights_epoch"] as Long),
                state.packs + (packId to Entry(slot, loaded.manifest["pack_version"] as String, payload.size.toLong())),
                state.floors + (packId to maxVersion(state.floors[packId], declaredMin)),
            )
            try {
                commit(newState)
            } catch (e: Exception) {
                // Not committed (or committed without floors): resolve from state.json alone.
                state = loadState(); recover(); syncRights()
                throw e
            }
            state = newState
            recover()                     // drop the previous slot now that state.json no longer names it
            syncRights()
            return loaded
        } finally {
            if (Files.exists(stage)) io.rmtree(stage)
        }
    }

    /** Re-verifies the referenced slot on every load. [now] null means time is not trustworthy. */
    fun active(packId: String, now: OffsetDateTime?): PackLoader.Loaded {
        val e = state.packs[packId] ?: throw StoreError("no active pack")
        val d = root.resolve("packs").resolve(packId).resolve(e.slot)
        return PackLoader(scratchRights(packId)).load(Files.readAllBytes(d.resolve(MANIFEST)), Files.readAllBytes(d.resolve(SIGNATURE)),
            Files.readAllBytes(d.resolve(PAYLOAD)), now, false, budgetBytes)
    }

    companion object {
        const val STATE_FILE = "state.json"
        const val FLOORS_FILE = "floors.json"
        const val PAYLOAD = "payload.pack"
        const val MANIFEST = "manifest.json"
        const val SIGNATURE = "manifest.sig"
        private val SLOT_FILES = listOf(PAYLOAD, MANIFEST, SIGNATURE)
        private val SLOT = Regex("^[0-9a-f]{16}$")
        private val PACK_ID = Regex("^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
        private val VERSION = Regex("^(0|[1-9][0-9]{0,8})\\.(0|[1-9][0-9]{0,8})\\.(0|[1-9][0-9]{0,8})$")
        private val rng = SecureRandom()

        private fun hex(n: Int) = ByteArray(n).also { rng.nextBytes(it) }.joinToString("") { "%02x".format(it) }

        private fun list(p: Path): List<Path> = if (!Files.isDirectory(p)) emptyList() else Files.list(p).use { s -> s.iterator().asSequence().toList() }

        fun deleteTree(p: Path) {
            if (!Files.exists(p)) return
            if (Files.isDirectory(p)) list(p).forEach { deleteTree(it) }
            try { Files.deleteIfExists(p) } catch (e: IOException) { /* best effort, like shutil.rmtree(ignore_errors) */ }
        }

        private fun cmp(a: Triple<Long, Long, Long>, b: Triple<Long, Long, Long>) =
            compareValuesBy(a, b, { it.first }, { it.second }, { it.third })

        fun maxVersion(a: Triple<Long, Long, Long>?, b: Triple<Long, Long, Long>): Triple<Long, Long, Long> =
            if (a == null || cmp(b, a) > 0) b else a

        private fun version(v: Any?): Triple<Long, Long, Long> {
            val l = v as List<*>
            require(l.size == 3)
            val t = Triple(l[0] as Long, l[1] as Long, l[2] as Long)
            require(t.first >= 0 && t.second >= 0 && t.third >= 0)
            return t
        }

        fun parseState(b: ByteArray): State {
            val m = MiniJson.parse(Charsets.UTF_8.newDecoder().decode(ByteBuffer.wrap(b)).toString()) as Map<*, *>
            require(m["format"] == "store-v2") { "unknown store format" }
            val packs = LinkedHashMap<String, Entry>()
            for ((k, v) in m["packs"] as Map<*, *>) {
                val e = v as Map<*, *>
                val id = k as String; val slot = e["slot"] as String; val ver = e["version"] as String; val bytes = e["bytes"] as Long
                require(PACK_ID.matches(id) && SLOT.matches(slot) && VERSION.matches(ver) && bytes >= 0) { "bad pack entry" }
                packs[id] = Entry(slot, ver, bytes)
            }
            val floors = HashMap<String, Triple<Long, Long, Long>>()
            for ((k, v) in m["minimum_pack_versions"] as Map<*, *>) floors[k as String] = version(v)
            val epoch = m["minimum_rights_epoch"] as Long
            require(epoch >= 0)
            return State(epoch, packs, floors)
        }

        private fun floorsMap(st: State): String =
            st.floors.toSortedMap().entries.joinToString(",", "{", "}") { (k, v) -> "\"$k\":[${v.first},${v.second},${v.third}]" }

        /** Same document shape as the Python store (sorted keys); IDs/slots/versions are validated ASCII. */
        fun stateJson(st: State): ByteArray {
            val packs = st.packs.toSortedMap().entries.joinToString(",", "{", "}") { (k, e) ->
                "\"$k\":{\"bytes\":${e.bytes},\"slot\":\"${e.slot}\",\"version\":\"${e.version}\"}"
            }
            return "{\"format\":\"store-v2\",\"minimum_pack_versions\":${floorsMap(st)},\"minimum_rights_epoch\":${st.epoch},\"packs\":$packs}"
                .toByteArray(Charsets.UTF_8)
        }

        fun floorsJson(st: State): ByteArray =
            "{\"minimum_pack_versions\":${floorsMap(st)},\"minimum_rights_epoch\":${st.epoch}}".toByteArray(Charsets.UTF_8)
    }
}
