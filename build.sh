#!/bin/sh
# Stamp issues.cgi with a SemVer build-metadata version based on local Git HEAD.

set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_dir=$(git -C "$script_dir" rev-parse --show-toplevel)
issues_file="$repo_dir/issues.cgi"

if [ ! -f "$issues_file" ]; then
    echo "issues.cgi not found at $issues_file" >&2
    exit 1
fi

version_line_count=$(grep -Ec '^ISSUES_VERSION = "[^"]*"$' "$issues_file" || true)
if [ "$version_line_count" -ne 1 ]; then
    echo "Expected exactly one ISSUES_VERSION assignment in $issues_file" >&2
    exit 1
fi

current_version=$(sed -n 's/^ISSUES_VERSION = "\([^"]*\)"$/\1/p' "$issues_file")
base_version=${current_version%%+*}

if ! printf '%s\n' "$base_version" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$'; then
    echo "ISSUES_VERSION must be a plain x.y.z version before build metadata is added: $current_version" >&2
    exit 1
fi

git_id=$(git -C "$repo_dir" rev-parse --verify HEAD)
new_version="${base_version}+${git_id}"
tmp_file="${issues_file}.build-version.$$"

trap 'rm -f "$tmp_file"' EXIT HUP INT TERM

awk -v new_version="$new_version" '
    /^ISSUES_VERSION = "[^"]*"$/ {
        print "ISSUES_VERSION = \"" new_version "\""
        next
    }
    { print }
' "$issues_file" > "$tmp_file"

if [ -x "$issues_file" ]; then
    chmod +x "$tmp_file"
fi

mv "$tmp_file" "$issues_file"
trap - EXIT HUP INT TERM

printf '%s\n' "$new_version"
