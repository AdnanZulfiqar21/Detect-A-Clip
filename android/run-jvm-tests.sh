#!/usr/bin/env bash
# Compile and run the pure-Kotlin sources and their JUnit tests on a plain JVM, without the
# Android SDK. Files that import android.* are excluded automatically; they are NOT compiled
# by this script (Android compile needs the SDK, see docs/BLOCKERS.md B-09).
#
# Expects (git-ignored) tools/: Temurin JDK 17, kotlinc, junit-4.13.2.jar, hamcrest-core-1.3.jar.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
T="$ROOT/tools"
JDK="$(ls -d "$T"/jdk-17* | head -1)"; JAVA="$JDK/bin/java"; [ -x "$JAVA.exe" ] && JAVA="$JAVA.exe"
KC="$T/kotlinc/lib/kotlin-compiler.jar"
STD="$T/kotlinc/lib/kotlin-stdlib.jar"
JU="$T/jars/junit-4.13.2.jar"
HC="$T/jars/hamcrest-core-1.3.jar"
SEP=":"; W() { printf '%s' "$1"; }
case "$(uname -s)" in MINGW*|MSYS*|CYGWIN*) SEP=";"; W() { cygpath -w "$1"; };; esac
OUT="$T/kbuild"
rm -rf "$OUT"; mkdir -p "$OUT"

MAIN=(); while IFS= read -r f; do MAIN+=("$(W "$f")"); done < <(grep -L "^import android\." "$ROOT"/android/app/src/main/java/ai/detectaclip/lab/*.kt)
TESTS=(); while IFS= read -r f; do TESTS+=("$(W "$f")"); done < <(ls "$ROOT"/android/app/src/test/java/ai/detectaclip/lab/*.kt)
echo "pure-Kotlin sources: ${#MAIN[@]} main, ${#TESTS[@]} test"
"$JAVA" -cp "$(W "$KC")" org.jetbrains.kotlin.cli.jvm.K2JVMCompiler -no-stdlib -cp "$(W "$STD")$SEP$(W "$JU")" -jvm-target 17 -d "$(W "$OUT")" "${MAIN[@]}" "${TESTS[@]}"
CLASSES=$(for f in "$ROOT"/android/app/src/test/java/ai/detectaclip/lab/*.kt; do b="$(basename "$f" .kt)"; echo "ai.detectaclip.lab.$b"; done)
"$JAVA" -cp "$(W "$OUT")$SEP$(W "$STD")$SEP$(W "$JU")$SEP$(W "$HC")" org.junit.runner.JUnitCore $CLASSES
