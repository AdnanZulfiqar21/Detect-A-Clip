#!/usr/bin/env bash
# Run the unit tests that Gradle/AGP compiled (compileDebugUnitTestKotlin) with plain JUnit.
# Use this where Gradle's own test executor cannot fork (the authoring host blocks loopback
# sockets between processes). Elsewhere, `:app:testDebugUnitTest` is the normal command.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="$ROOT/android/app"
JDK="$(ls -d "$ROOT"/tools/jdk-17* | head -1)"; JAVA="$JDK/bin/java"; [ -x "$JAVA.exe" ] && JAVA="$JAVA.exe"
CACHE="${GRADLE_USER_HOME:-$HOME/.gradle}/caches/modules-2/files-2.1"
STD="$(ls "$CACHE"/org.jetbrains.kotlin/kotlin-stdlib/2.4.*/*/kotlin-stdlib-2.4.*.jar | grep -v sources | sort | tail -1)"
JU="$(ls "$CACHE"/junit/junit/4.13.2/*/junit-4.13.2.jar | head -1)"
HC="$(ls "$CACHE"/org.hamcrest/hamcrest-core/1.3/*/hamcrest-core-1.3.jar 2>/dev/null | head -1 || true)"
[ -n "$HC" ] || HC="$ROOT/tools/jars/hamcrest-core-1.3.jar"
SEP=":"; W() { printf '%s' "$1"; }
case "$(uname -s)" in MINGW*|MSYS*|CYGWIN*) SEP=";"; W() { cygpath -w "$1"; };; esac
K="$APP/build/intermediates/built_in_kotlinc"
CP="$(W "$K/debug/compileDebugKotlin/classes")$SEP$(W "$K/debugUnitTest/compileDebugUnitTestKotlin/classes")$SEP$(W "$STD")$SEP$(W "$JU")$SEP$(W "$HC")"
CLASSES=$(for f in "$APP"/src/test/java/ai/detectaclip/lab/*.kt; do echo "ai.detectaclip.lab.$(basename "$f" .kt)"; done)
cd "$APP"
"$JAVA" -cp "$CP" org.junit.runner.JUnitCore $CLASSES
