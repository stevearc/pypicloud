#!/bin/bash
set -e
declare -r HELP="usage: $0 [all]

Run autopep8 on all staged and unstaged *.py files in the git index

If you specified \"all\" as an argument, it will run autopep8 on all *.py files
in the repository, regardless of staging.
"


main() {
    local _autopep="autopep8 -j 0 -i -v"
    if [ "$1" == "-h" ]; then
        echo "$HELP"
    elif [ "$1" == "all" ]; then
        $_autopep -r pypicloud tests
    else
        local _diff=$(git diff --name-only --diff-filter=ACMRT | grep '.py$')
        if [ -n "$_diff" ]; then
            for file in $_diff; do
                $_autopep "$file"
            done
        fi
        local _diff_cached=$(git diff --cached --name-only --diff-filter=ACMRT | grep '.py$')
        if [ -n "$_diff_cached" ]; then
            for file in $_diff_cached; do
                $_autopep "$file"
            done
        fi
    fi
}

main "$@"
