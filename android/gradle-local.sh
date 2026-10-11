#!/usr/bin/env bash
# Run Gradle for the Android LAB module with the git-ignored local toolchain in ../tools.
# Android Studio users do not need this script.
#
# Why the extra flags: on the authoring host, sockets between Gradle processes are blocked,
# so the build must run inside the client JVM (no daemon, no worker daemon, in-process
# Kotlin compiler and javac). The JVM arguments are therefore passed identically to the
# client (GRADLE_OPTS) and as org.gradle.jvmargs, and an init script disables javac forking.
#
#   bash android/gradle-local.sh :app:assembleDebug
#   DAC_GRADLE_TMP=/c/somewhere/without/spaces bash android/gradle-local.sh :app:lintDebug
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TOOLS="$ROOT/tools"
JDK="$(ls -d "$TOOLS"/jdk-17* | head -1)"
GRADLE="$(ls -d "$TOOLS"/gradle-9* | head -1)/bin/gradle"
W() { if command -v cygpath >/dev/null; then cygpath -w "$1"; else printf '%s' "$1"; fi; }
M() { if command -v cygpath >/dev/null; then cygpath -m "$1"; else printf '%s' "$1"; fi; }

TMPD="${DAC_GRADLE_TMP:-${TMP:-/tmp}}"
case "$TMPD" in *" "*) echo "DAC_GRADLE_TMP must not contain spaces: $TMPD" >&2; exit 2;; esac
mkdir -p "$TMPD/dac-gradle"
TMPM="$(M "$TMPD/dac-gradle")"

INIT="$TMPD/dac-gradle/inprocess.init.gradle.kts"
cat > "$INIT" <<'EOF'
allprojects { tasks.withType<JavaCompile>().configureEach { options.isFork = false } }
EOF

X="--add-exports=jdk.compiler/com.sun.tools.javac.api=ALL-UNNAMED --add-exports=jdk.compiler/com.sun.tools.javac.util=ALL-UNNAMED"
export JAVA_HOME="$(W "$JDK")"
export GRADLE_OPTS="-Xmx2g -Dfile.encoding=UTF-8 -Djdk.net.unixdomain.tmpdir=$TMPM -Djava.io.tmpdir=$TMPM $X"

if [ ! -f "$ROOT/android/local.properties" ]; then
  # Properties files need the drive colon escaped (C\:/path).
  SDK="$(M "$TOOLS/android-sdk")"
  printf 'sdk.dir=%s\n' "${SDK/:/\\:}" > "$ROOT/android/local.properties"
fi

cd "$ROOT/android"
exec "$GRADLE" --no-daemon -I "$(M "$INIT")" "-Dorg.gradle.jvmargs=-Xms64m -Xmx2g -Dfile.encoding=UTF-8 $X" \
  -Pkotlin.compiler.execution.strategy=in-process "$@"
