package ai.detectaclip.lab

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.io.IOException
import java.nio.file.Files
import java.nio.file.Path
import java.time.OffsetDateTime
import kotlin.system.exitProcess

/**
 * Installed pack store (P03-T06, IDX-01, RIGHTS-02): staged validation, single commit point,
 * floors that a restored state cannot lower, fail-closed recovery, and recovery after the
 * process is halted (Runtime.halt in a child JVM) before or in the middle of every I/O step.
 * Packs come from golden_manifest_cases.txt (signed by a throwaway key, private half discarded).
 */
class PackStoreTest {
    class Golden(val pubId: String, val pub: ByteArray, val packs: Map<String, Triple<ByteArray, ByteArray, ByteArray>>)

    companion object {
        val NOW: OffsetDateTime = OffsetDateTime.parse("2026-10-10T12:00:00+00:00")
        private const val HALTED = 77

        private fun hex(s: String) = ByteArray(s.length / 2) { s.substring(2 * it, 2 * it + 2).toInt(16).toByte() }

        fun goldenFile(): File = listOf("src/test/resources/golden_manifest_cases.txt", "android/app/src/test/resources/golden_manifest_cases.txt",
            "app/src/test/resources/golden_manifest_cases.txt").map(::File).first { it.exists() }

        /** name -> (manifest, signature, payload) */
        fun golden(f: File): Golden {
            val lines = f.readLines()
            val pub = lines.first { it.startsWith("PUBKEY ") }.split(" ")
            val payloads = lines.filter { it.startsWith("PAYLOAD ") }.associate { val p = it.split(" "); p[1] to hex(p[2]) }
            val packs = lines.filter { it.startsWith("CASE ") }.associate { line ->
                val p = line.split(" ")
                val kv = p.drop(3).associate { it.substringBefore("=") to it.substringAfter("=") }
                p[1] to Triple(hex(kv.getValue("manifest")), hex(kv.getValue("sig")), payloads.getValue(kv.getValue("payload")))
            }
            return Golden(pub[1], hex(pub[2]), packs)
        }

        fun rights(g: Golden) = PackLoader.DeviceRightsState().also { it.trustedKeys[g.pubId] = g.pub }

        /** Fails at, or halts the JVM at, the [at]-th I/O call (1-based). */
        class FaultIo(private val at: Int, private val mode: String) : PackStore.Io {
            var calls = 0
            private fun step(torn: (() -> Unit)? = null) {
                calls += 1
                if (calls != at) return
                when (mode) {
                    "throw" -> throw IOException("injected failure at I/O step $at")
                    "halt" -> Runtime.getRuntime().halt(HALTED)
                    "torn" -> { torn?.invoke(); Runtime.getRuntime().halt(HALTED) }
                }
            }
            override fun writeBytes(p: Path, b: ByteArray) {
                step { Files.write(p, b.copyOf(b.size / 2)) }     // half the bytes, no fsync, then halt
                PackStore.Io.Durable.writeBytes(p, b)
            }
            override fun replace(src: Path, dst: Path) { step(); PackStore.Io.Durable.replace(src, dst) }
            override fun rmtree(p: Path) { step(); PackStore.Io.Durable.rmtree(p) }
            override fun mkdir(p: Path) { step(); PackStore.Io.Durable.mkdir(p) }
        }

        /** Child JVM: open the store, then install the upgrade with a halting Io. */
        @JvmStatic fun main(args: Array<String>) {
            val g = golden(File(args[2]))
            val store = PackStore(Path.of(args[0]), rights(g), FaultIo(args[1].toInt(), args[3]))
            val (m, s, p) = g.packs.getValue("version_numeric_order_2_10_over_2_9")
            store.install(m, s, p, NOW)
            exitProcess(0)
        }
    }

    private val g = golden(goldenFile())
    private fun pack(name: String) = g.packs.getValue(name)
    private fun tmp(): Path = Files.createTempDirectory("dac-store")
    private fun PackStore.install(name: String) = pack(name).let { (m, s, p) -> install(m, s, p, NOW) }
    private fun tree(root: Path): List<String> = Files.walk(root).use { s ->
        s.iterator().asSequence().filter { Files.isRegularFile(it) }.map { root.relativize(it).toString().replace('\\', '/') }.sorted().toList()
    }

    @Test fun installPersistsAndReopenReVerifies() {
        val root = tmp()
        val s = PackStore(root, rights(g))
        s.install("valid_dev_no_expiry")
        val again = PackStore(root, rights(g))
        assertEquals("1.0.0", again.state.packs.getValue("L0-E2E").version)
        assertEquals("L0-E2E", again.active("L0-E2E", NOW).manifest["pack_id"])
        assertEquals("L0-E2E", again.active("L0-E2E", null).manifest["pack_id"])   // dev pack, no expiry: untrusted time ok
        assertTrue(again.recoveryActions.isEmpty())
    }

    @Test fun rejectedPackLeavesStateAndFilesUnchanged() {
        val root = tmp()
        val r = rights(g)
        val s = PackStore(root, r)
        s.install("valid_dev_no_expiry")
        val before = tree(root); val stateBefore = s.state; val bytesBefore = HashMap(r.installedIndexBytes)
        for (bad in listOf("bad_signature_bit", "future_valid_from", "below_declared_minimum", "payload_hash_mismatch", "duplicate_json_key")) {
            assertThrows(bad, PackLoader.Rejected::class.java) { s.install(bad) }
            assertEquals(bad, before, tree(root))
            assertEquals(bad, stateBefore, s.state)
            assertEquals(bad, bytesBefore, HashMap(r.installedIndexBytes))
        }
    }

    @Test fun upgradeReplacesSlotAndFloorBlocksRollback() {
        val root = tmp()
        val s = PackStore(root, rights(g))
        s.install("valid_dev_no_expiry")
        val oldSlot = s.state.packs.getValue("L0-E2E").slot
        s.install("version_numeric_order_2_10_over_2_9")
        val e = s.state.packs.getValue("L0-E2E")
        assertEquals("2.10.0", e.version)
        assertNotEquals(oldSlot, e.slot)
        assertFalse(Files.exists(root.resolve("packs/L0-E2E/$oldSlot")))
        assertEquals(Triple(2L, 0L, 0L), s.state.floors["L0-E2E"])
        assertThrows(PackLoader.Rejected::class.java) { s.install("valid_dev_no_expiry") }   // 1.0.0 < floor 2.0.0
        assertEquals("2.10.0", s.state.packs.getValue("L0-E2E").version)
    }

    @Test fun restoredOldStateCannotLowerFloors() {
        val root = tmp()
        val s = PackStore(root, rights(g))
        s.install("valid_dev_no_expiry")
        val oldState = Files.readAllBytes(root.resolve(PackStore.STATE_FILE))
        val oldSlot = s.state.packs.getValue("L0-E2E").slot
        val oldSlotFiles = PackStore.run { listOf(PAYLOAD, MANIFEST, SIGNATURE) }.associateWith { Files.readAllBytes(root.resolve("packs/L0-E2E/$oldSlot/$it")) }
        s.install("version_numeric_order_2_10_over_2_9")
        // Simulate a backup restore of the old state and slot.
        Files.write(root.resolve(PackStore.STATE_FILE), oldState)
        Files.createDirectories(root.resolve("packs/L0-E2E/$oldSlot"))
        for ((n, b) in oldSlotFiles) Files.write(root.resolve("packs/L0-E2E/$oldSlot/$n"), b)
        val r = rights(g)
        val restored = PackStore(root, r)
        assertEquals(Triple(2L, 0L, 0L), r.minimumPackVersions["L0-E2E"])                   // floor kept
        assertThrows(PackLoader.Rejected::class.java) { restored.active("L0-E2E", NOW) }   // old pack now fails closed
    }

    /** SEC-03: a signer revoked after installation stops the installed pack from activating. */
    @Test fun revokedSignerBlocksActivationOfAnInstalledPack() {
        val root = tmp()
        PackStore(root, rights(g)).install("valid_dev_no_expiry")
        val r = rights(g).also { it.revokedKeyIds += g.pubId }
        val s = PackStore(root, r)
        assertThrows(PackLoader.Rejected::class.java) { s.active("L0-E2E", NOW) }
        val t = rights(g).also { it.trustedKeys.clear() }
        assertThrows(PackLoader.Rejected::class.java) { PackStore(root, t).active("L0-E2E", NOW) }   // key no longer trusted
    }

    @Test fun corruptOrDanglingStateFailsClosed() {
        val root = tmp()
        PackStore(root, rights(g)).install("valid_dev_no_expiry")
        val state = root.resolve(PackStore.STATE_FILE)
        val good = Files.readAllBytes(state)
        Files.write(state, "{\"format\":\"store-v2\"".toByteArray())
        assertThrows(PackStore.StoreError::class.java) { PackStore(root, rights(g)) }
        Files.write(state, good)
        val slot = PackStore.parseState(good).packs.getValue("L0-E2E").slot
        Files.delete(root.resolve("packs/L0-E2E/$slot/${PackStore.PAYLOAD}"))
        assertThrows(PackStore.StoreError::class.java) { PackStore(root, rights(g)) }
    }

    @Test fun injectedIoFailureAtEveryStepLeavesOldOrNewPack() {
        var at = 1
        while (true) {
            val root = tmp()
            PackStore(root, rights(g)).install("valid_dev_no_expiry")
            val io = FaultIo(at, "throw")
            val s = PackStore(root, rights(g), io)
            val failed = try { s.install("version_numeric_order_2_10_over_2_9"); false } catch (e: IOException) { true }
            val reopened = PackStore(root, rights(g))
            val v = reopened.state.packs.getValue("L0-E2E").version
            assertTrue("step $at: $v", v == "1.0.0" || v == "2.10.0")
            reopened.active("L0-E2E", NOW)
            assertEquals("step $at", 1, Files.list(root.resolve("packs/L0-E2E")).use { it.count() })
            if (!failed) break
            at += 1
            assertTrue("runaway", at < 60)
        }
        assertTrue("expected several I/O steps, got $at", at > 5)
    }

    @Test fun haltedProcessAtEveryStepRecoversToOldOrNewPack() {
        val java = ProcessHandle.current().info().command().orElse("java")
        val cp = listOf(PackStoreTest::class.java, PackStore::class.java, Unit::class.java)
            .map { File(it.protectionDomain.codeSource.location.toURI()).path }.distinct().joinToString(File.pathSeparator)
        val golden = goldenFile().absolutePath
        val seen = HashSet<String>()
        for (mode in listOf("halt", "torn")) {
            var at = 1
            while (true) {
                val root = tmp()
                PackStore(root, rights(g)).install("valid_dev_no_expiry")
                val proc = ProcessBuilder(java, "-cp", cp, PackStoreTest::class.java.name, root.toString(), at.toString(), golden, mode)
                    .redirectErrorStream(true).start()
                val out = proc.inputStream.bufferedReader().readText()
                val code = proc.waitFor()
                assertTrue("child failed at $mode/$at with $code: $out", code == HALTED || code == 0)
                val r = PackStore(root, rights(g))
                val v = r.state.packs.getValue("L0-E2E").version
                assertTrue("$mode/$at: $v", v == "1.0.0" || v == "2.10.0")
                seen += v
                assertEquals("L0-E2E", r.active("L0-E2E", NOW).manifest["pack_id"])
                assertEquals(emptyList<String>(), tree(root).filter { it.startsWith("staging/") || it.endsWith(".tmp") })
                assertEquals("$mode/$at", 1, Files.list(root.resolve("packs/L0-E2E")).use { it.count() })
                if (code == 0) break
                at += 1
                assertTrue("runaway", at < 60)
            }
        }
        assertEquals(setOf("1.0.0", "2.10.0"), seen)
    }
}
