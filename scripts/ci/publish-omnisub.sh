#!/usr/bin/env bash
set -euo pipefail

: "${VERSION:?}" "${REVISION:?}" "${BUILD_DATE:?}" "${IMAGE:?}" "${GH_TOKEN:?}"
test "$IMAGE" = ghcr.io/astralwaveorg/omnisub
test "$GITHUB_REPOSITORY" = astralwaveorg/OmniSub
test "$GITHUB_REF" = refs/heads/release
test "$(git rev-parse HEAD)" = "$REVISION"

remote="https://github.com/$GITHUB_REPOSITORY.git"
assert_current() {
  test "$(git ls-remote "$remote" refs/heads/release | cut -f1)" = "$REVISION"
}
assert_current
tag_rev="$(git ls-remote "$remote" "refs/tags/$VERSION^{}" | cut -f1)"
if [[ -z "$tag_rev" ]]; then
  tag_rev="$(git ls-remote "$remote" "refs/tags/$VERSION" | cut -f1)"
fi
if [[ -n "$tag_rev" && "$tag_rev" != "$REVISION" ]]; then
  echo "Refusing to replace existing version tag $VERSION" >&2
  exit 1
fi

mkdir release-assets
find artifacts -type f -name 'SubConverter-Extended-*' -exec sh -c '
  for file do
    dest="release-assets/${file##*/}"
    test ! -e "$dest" || exit 1
    cp "$file" "$dest"
  done
' sh {} +
(cd release-assets && sha256sum SubConverter-Extended-* > SHA256SUMS)

# Before any registry write, verify completeness and package names.
python3 scripts/ci/release_manifest.py build --root release-assets \
  --output release-assets/RELEASE-MANIFEST.json --version "$VERSION" \
  --revision "$REVISION" --build-date "$BUILD_DATE" \
  --ghcr-digest "sha256:$(printf '%064d' 0)"

printf '%s' "$GH_TOKEN" | docker login ghcr.io -u "$GITHUB_ACTOR" --password-stdin
references=()
platforms=(linux/amd64 linux/arm64 linux/arm/v7)
arches=(amd64 arm64 armv7)
for i in "${!arches[@]}"; do
  arch="${arches[$i]}"
  archive="subconverter-extended-$arch.tar.gz"
  dir="artifacts/docker-image-$arch"
  (cd "$dir" && sha256sum -c "$archive.sha256")
  gzip -dc "$dir/$archive" | docker load
  local_image="subconverter-extended:$arch-ci"
  test "$(docker image inspect --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}' "$local_image")" = "$REVISION"
  test "$(docker image inspect --format '{{ index .Config.Labels "org.opencontainers.image.version" }}' "$local_image")" = "$VERSION"
  test "$(docker image inspect --format '{{.Os}}/{{.Architecture}}{{if .Variant}}/{{.Variant}}{{end}}' "$local_image")" = "${platforms[$i]}"
  candidate="$IMAGE:build-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}-$arch"
  docker tag "$local_image" "$candidate"
  docker push "$candidate"
  references+=("$candidate")
done

digest_of() {
  docker buildx imagetools inspect "$1" | awk '/^Digest:/ {print $2; exit}'
}
# Use a separate index while validation runs. Version and latest move only after
# their artifacts are ready and this revision still heads release.
index="$IMAGE:build-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"
docker buildx imagetools create --tag "$index" "${references[@]}"
digest="$(digest_of "$index")"
[[ "$digest" =~ ^sha256:[0-9a-f]{64}$ ]]
existing="$(digest_of "$IMAGE:$VERSION" 2>/dev/null || true)"
if [[ -n "$existing" ]]; then
  # On retry, keep the already published digest if all its platforms carry this SHA.
  for i in "${!platforms[@]}"; do
    platform="${platforms[$i]}"
    docker pull --platform "$platform" "$IMAGE@$existing"
    test "$(docker image inspect --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}' "$IMAGE@$existing")" = "$REVISION"
    test "$(docker image inspect --format '{{ index .Config.Labels "org.opencontainers.image.version" }}' "$IMAGE@$existing")" = "$VERSION"
  done
  digest="$existing"
fi
python3 scripts/ci/release_manifest.py build --root release-assets \
  --output release-assets/RELEASE-MANIFEST.json --version "$VERSION" \
  --revision "$REVISION" --build-date "$BUILD_DATE" --ghcr-digest "$digest"
python3 scripts/ci/release_manifest.py verify --root release-assets \
  --manifest release-assets/RELEASE-MANIFEST.json
(cd release-assets && sha256sum -c SHA256SUMS)

assert_current
if [[ -z "$tag_rev" ]]; then
  gh api "repos/$GITHUB_REPOSITORY/git/refs" -f "ref=refs/tags/$VERSION" -f "sha=$REVISION" >/dev/null
fi
# Keep any interrupted draft intact unless it belongs to the same tag and is
# still unpublished. A published release is immutable.
draft="$(gh release view "$VERSION" --json isDraft --jq .isDraft 2>/dev/null || true)"
if [[ "$draft" != false ]]; then
  if [[ "$draft" == true ]]; then
    gh release upload "$VERSION" release-assets/* --clobber
  else
    gh release create "$VERSION" release-assets/* --verify-tag --draft \
      --title "OmniSub $VERSION" --notes-file RELEASE-NOTES.md
  fi
fi
assert_current
if [[ -z "$existing" ]]; then
  docker buildx imagetools create --tag "$IMAGE:$VERSION" "$IMAGE@$digest"
fi
test "$(digest_of "$IMAGE:$VERSION")" = "$digest"
if [[ "$draft" != false ]]; then
  gh release edit "$VERSION" --draft=false --latest
fi
assert_current
docker buildx imagetools create --tag "$IMAGE:latest" "$IMAGE@$digest"
test "$(digest_of "$IMAGE:latest")" = "$digest"
