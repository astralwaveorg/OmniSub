#!/bin/sh
# Package the UI pinned by this checkout for the same-origin web gateway.
set -eu

if [ "$#" -ne 1 ] || [ -z "$1" ]; then
    printf 'Usage: %s <new-output-directory>\n' "$0" >&2
    exit 2
fi

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
ui="$root/OmniSubUI"
out=$1
[ ! -e "$out" ] || { printf 'Output already exists: %s\n' "$out" >&2; exit 2; }

pinned=$(git -C "$root" ls-files --stage -- OmniSubUI | awk '$1 == "160000" {print $2}')
revision=$(git -C "$ui" rev-parse --verify HEAD 2>/dev/null) || revision=
if [ -z "$pinned" ] || [ "$revision" != "$pinned" ] ||
        [ -n "$(git -C "$ui" status --porcelain)" ]; then
    printf 'OmniSubUI must be initialized at the staged submodule revision with a clean checkout.\n' >&2
    exit 1
fi

(
    cd "$ui"
    npm ci --no-audit --no-fund
    APP_REVISION=$revision npm run build:hosted
)
expected="app.js
style.css"
actual=$(LC_ALL=C ls -1 "$ui/dist/assets")
[ "$actual" = "$expected" ] || { printf 'Unexpected hosted asset set.\n' >&2; exit 1; }
grep -Fq "/assets/app.js?v=$revision" "$ui/dist/index.html"
grep -Fq "/assets/style.css?v=$revision" "$ui/dist/index.html"

mkdir -- "$out"
cp -- "$ui/dist/index.html" "$ui/dist/assets/app.js" "$ui/dist/assets/style.css" "$ui/dist/favicon.svg" "$out"
