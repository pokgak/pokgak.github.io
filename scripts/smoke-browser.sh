#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   npm run test:browser
#   npm run test:browser -- https://<portal-url>
#   BASE_URL=https://<portal-url> npm run test:browser
BASE_URL="${1:-${BASE_URL:-http://127.0.0.1:3000}}"
BASE_URL="${BASE_URL%/}"
SESSION="pokgak-smoke-$$"

command -v agent-browser >/dev/null
command -v curl >/dev/null

browser() {
  agent-browser --session "$SESSION" "$@"
}

cleanup() {
  browser close >/dev/null 2>&1 || true
}
trap cleanup EXIT

assert_equal() {
  local expected="$1"
  local actual="$2"
  local label="$3"
  if [[ "$actual" != "$expected" ]]; then
    printf 'FAIL: %s\n  expected: %s\n  actual:   %s\n' "$label" "$expected" "$actual" >&2
    exit 1
  fi
  printf 'PASS: %s\n' "$label"
}

assert_contains() {
  local expected="$1"
  local actual="$2"
  local label="$3"
  if [[ "$actual" != *"$expected"* ]]; then
    printf 'FAIL: %s\n  expected to contain: %s\n  actual:              %s\n' "$label" "$expected" "$actual" >&2
    exit 1
  fi
  printf 'PASS: %s\n' "$label"
}

echo "Running browser smoke tests against $BASE_URL"
browser open "$BASE_URL"
browser wait --load domcontentloaded
browser snapshot -i >/dev/null
assert_equal "Aiman Ismail" "$(browser get title)" "home page title"
assert_equal "Latest Writing" "$(browser get text 'main h1')" "home page heading"

pressed_before="$(browser get attr '#theme-toggle' aria-pressed)"
browser click '#theme-toggle'
pressed_after="$(browser get attr '#theme-toggle' aria-pressed)"
if [[ "$pressed_before" == "$pressed_after" ]]; then
  echo "FAIL: theme toggle did not update aria-pressed" >&2
  exit 1
fi
echo "PASS: theme toggle updates its accessible state"

browser click 'header a[href="/articles/"]'
browser wait --url '**/articles/'
assert_equal "Articles" "$(browser get text 'main h1')" "Articles navigation"

browser click 'main li:first-child a'
browser wait --load domcontentloaded
assert_contains "/articles/" "$(browser get url)" "article detail navigation"
article_title="$(browser get text 'main article h1')"
[[ -n "$article_title" ]] || { echo "FAIL: article detail heading is empty" >&2; exit 1; }
echo "PASS: article detail renders a heading"

for section in notes experiments talks; do
  browser click "header a[href=\"/$section/\"]"
  browser wait --url "**/$section/"
  heading="$(browser get text 'main h1')"
  expected="${section^}"
  assert_equal "$expected" "$heading" "$expected navigation"
done

browser click 'header > a[href="/"]'
browser wait --url "$BASE_URL/"
assert_equal "Latest Writing" "$(browser get text 'main h1')" "home navigation"

llms_txt="$(curl -fsS "$BASE_URL/llms.txt")"
grep -q '^# Aiman Ismail$' <<<"$llms_txt"
echo "PASS: llms.txt is served"
sitemap_xml="$(curl -fsS "$BASE_URL/sitemap.xml")"
grep -q '<urlset ' <<<"$sitemap_xml"
echo "PASS: sitemap.xml is served"
robots_txt="$(curl -fsS "$BASE_URL/robots.txt")"
grep -q '^Sitemap: https://pokgak.xyz/sitemap.xml$' <<<"$robots_txt"
echo "PASS: robots.txt is served"

echo "Browser smoke tests passed."
