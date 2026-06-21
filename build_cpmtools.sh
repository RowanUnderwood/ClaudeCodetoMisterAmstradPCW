#!/usr/bin/env bash
#
# build_cpmtools.sh -- compile libdsk + cpmtools (WITH libdsk) inside MSYS2 and
# stage a self-contained, relocatable copy into the project.
#
# This is NOT meant to be run by hand. install_cpmtools.py drives it: it finds
# (or winget-installs) MSYS2, then runs this script through MSYS2's bash with the
# right environment. See that file and CLAUDE.md.
#
# Why MSYS subsystem (not ucrt64 native):
#   cpmtools bakes the diskdefs path in at compile time (e.g. <prefix>/share/
#   diskdefs) and has no flag to override it -- CPMTOOLSFMT only sets the default
#   *format name*, not the file path. A native ucrt64 exe can't resolve that
#   POSIX path once moved. An MSYS-subsystem exe carries msys-2.0.dll, whose
#   directory determines the runtime root, so a relocated bin\ + a diskdefs file
#   placed under the staging root resolves correctly. We also copy diskdefs to
#   every plausible baked location, belt-and-suspenders.
#
# Inputs (exported by install_cpmtools.py):
#   STAGE_BIN     msys path to <project>\cpmtools\bin   (exes + DLLs land here)
#   STAGE_ROOT    msys path to <project>\cpmtools       (diskdefs tree roots here)
#   LIBDSK_VER    libdsk version to fetch   (default 1.5.22)
#   CPMTOOLS_VER  cpmtools version to fetch (default 2.23)
#
set -euo pipefail

LIBDSK_VER="${LIBDSK_VER:-1.5.22}"
CPMTOOLS_VER="${CPMTOOLS_VER:-2.23}"
LIBDSK_URL="https://www.seasip.info/Unix/LibDsk/libdsk-${LIBDSK_VER}.tar.gz"
CPMTOOLS_URL="https://www.moria.de/~michael/cpmtools/files/cpmtools-${CPMTOOLS_VER}.tar.gz"

: "${STAGE_BIN:?STAGE_BIN not set (install_cpmtools.py exports it)}"
: "${STAGE_ROOT:?STAGE_ROOT not set (install_cpmtools.py exports it)}"

# Build under $HOME (no spaces) -- autotools dislikes spaces in build paths.
# The project path has spaces, so we only ever *copy* there at the end.
BUILD_ROOT="$HOME/cpmtools-build"
PREFIX="$BUILD_ROOT/prefix"

say() { printf '\n>> %s\n' "$*"; }

# ---------------------------------------------------------------------------
say "Installing build toolchain via pacman (MSYS environment)"
# binutils -> 'strings' (to read the baked diskdefs path); base-devel -> make,
# autotools; gcc -> the MSYS-subsystem compiler.
pacman -S --needed --noconfirm \
    base-devel gcc binutils wget tar gzip >/dev/null

mkdir -p "$BUILD_ROOT"
cd "$BUILD_ROOT"

# ---------------------------------------------------------------------------
say "Downloading sources"
# Fetch only if we don't already have a *valid* gzip (a half-finished download
# from a previous failed run must not be cached -- it'd break tar below).
fetch() {
    local out="$1" url="$2"
    if [ -f "$out" ] && gzip -t "$out" 2>/dev/null; then
        echo "   cached: $out"; return
    fi
    rm -f "$out"
    echo "   downloading: $url"
    wget -q -O "$out" "$url"
    gzip -t "$out"   # fail loudly (set -e) if the archive is bad
}
fetch "libdsk-${LIBDSK_VER}.tar.gz"     "$LIBDSK_URL"
fetch "cpmtools-${CPMTOOLS_VER}.tar.gz" "$CPMTOOLS_URL"

rm -rf "libdsk-${LIBDSK_VER}" "cpmtools-${CPMTOOLS_VER}"
tar xzf "libdsk-${LIBDSK_VER}.tar.gz"
tar xzf "cpmtools-${CPMTOOLS_VER}.tar.gz"

# Portability patch: libdsk's rcpmfs driver picks the 1-arg Windows mkdir()
# whenever <windows.h> exists -- but MSYS/Cygwin ship POSIX 2-arg mkdir(), so it
# fails to compile. MSYS defines __CYGWIN__; exclude it so the POSIX branch wins.
RCPM="$BUILD_ROOT/libdsk-${LIBDSK_VER}/lib/drvrcpm.c"
if [ -f "$RCPM" ]; then
    sed -i 's/^#elif defined HAVE_WINDOWS_H$/#elif defined HAVE_WINDOWS_H \&\& !defined(__CYGWIN__)/' "$RCPM"
fi

# ---------------------------------------------------------------------------
say "Building libdsk $LIBDSK_VER -> $PREFIX"
cd "$BUILD_ROOT/libdsk-${LIBDSK_VER}"
# We build as an MSYS (Cygwin-like) subsystem, but <windows.h> exists, so
# configure would otherwise pull in libdsk's Win32 raw-floppy drivers
# (drvwin32.c, drvntwdm.c) -- which don't compile under MSYS gcc and which we
# don't need (we only read CPCEMU .DSK *images*, the portable drvcpcem driver).
# Force the windows.h check to "no" so those drivers are dropped and mkdir() &
# friends take their POSIX branches.
./configure --prefix="$PREFIX" ac_cv_header_windows_h=no
make -j"$(nproc)"
make install

# Make libdsk discoverable for cpmtools' configure test program + at link time.
export PATH="$PREFIX/bin:$PATH"
export PKG_CONFIG_PATH="$PREFIX/lib/pkgconfig:${PKG_CONFIG_PATH:-}"
export CPPFLAGS="-I$PREFIX/include"
export LDFLAGS="-L$PREFIX/lib"
export LIBS="-ldsk"

# ---------------------------------------------------------------------------
say "Building cpmtools $CPMTOOLS_VER (with libdsk)"
cd "$BUILD_ROOT/cpmtools-${CPMTOOLS_VER}"
# The flag has been spelled both ways across versions; try the documented one,
# fall back if configure rejects it.
if ! ./configure --prefix="$PREFIX" --with-libdsk 2>/dev/null; then
    say "  --with-libdsk rejected; retrying with --enable-libdsk"
    ./configure --prefix="$PREFIX" --enable-libdsk
fi
make -j"$(nproc)"
make install

# Confirm libdsk really got linked in (so -T dsk will work).
if ! ldd "$PREFIX/bin/cpmcp.exe" | grep -qi 'libdsk'; then
    echo "WARNING: cpmcp.exe does not link libdsk -- '-T dsk' may not work." >&2
    echo "         Check the configure output above for a missing libdsk." >&2
fi

# ---------------------------------------------------------------------------
say "Staging native binaries -> $STAGE_BIN"
mkdir -p "$STAGE_BIN"
EXES="cpmcp cpmls cpmrm cpmchattr cpmchmod cpmcheck mkfs.cpm fsck.cpm"
for e in $EXES; do
    [ -f "$PREFIX/bin/$e.exe" ] && cp -f "$PREFIX/bin/$e.exe" "$STAGE_BIN/"
done

# Bundle every non-Windows DLL the exes need (msys-2.0.dll, libdsk, libgcc,
# libwinpthread, ...). Windows loads DLLs from the exe's own dir first, so
# placing them beside the exes makes the folder self-contained -- no PATH edits.
say "Bundling dependent DLLs"
for e in "$STAGE_BIN"/*.exe; do
    ldd "$e" 2>/dev/null | awk '{print $3}' | while read -r dll; do
        case "$dll" in
            ""|/c/[Ww][Ii][Nn][Dd][Oo][Ww][Ss]/*) continue ;;  # skip OS DLLs
        esac
        [ -f "$dll" ] && cp -f "$dll" "$STAGE_BIN/" 2>/dev/null || true
    done
done

# ---------------------------------------------------------------------------
say "Staging diskdefs (format database)"
DISKDEFS_SRC="$(find "$PREFIX" -name diskdefs -type f | head -1 || true)"
if [ -z "$DISKDEFS_SRC" ]; then
    echo "ERROR: diskdefs not found under $PREFIX after install." >&2
    exit 1
fi

# Collect candidate baked paths: whatever 'strings' shows ending in /diskdefs,
# plus the conventional locations. Place a copy at each so the relocated exe
# finds it no matter how the path was compiled in. STAGE_ROOT becomes the msys
# runtime root (msys-2.0.dll sits in STAGE_ROOT/bin), so POSIX paths resolve
# under it.
declare -A seen=()
place() {
    local posix="$1" dir
    [ -z "$posix" ] && return
    [ -n "${seen[$posix]:-}" ] && return
    seen[$posix]=1
    dir="$STAGE_ROOT$(dirname "$posix")"
    mkdir -p "$dir"
    cp -f "$DISKDEFS_SRC" "$dir/diskdefs"
}

# From the binary itself:
for e in "$STAGE_BIN"/cpmls.exe "$STAGE_BIN"/cpmcp.exe; do
    [ -f "$e" ] || continue
    while read -r p; do place "$p"; done < <(strings "$e" | grep -E '/diskdefs$' || true)
done
# Conventional fallbacks:
place "$PREFIX/share/diskdefs"
place "/usr/local/share/diskdefs"
place "/usr/share/diskdefs"
place "/etc/cpmtools/diskdefs"
# And right beside the exes, in case a build looks next to argv[0]:
cp -f "$DISKDEFS_SRC" "$STAGE_BIN/diskdefs"

say "Build complete. Staged to:"
echo "   $STAGE_BIN"
ls -1 "$STAGE_BIN"
