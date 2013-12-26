#!/bin/bash -e
declare -r CONF=".pep8.ini"
declare -r ARGS=(ignore select max-line-length)
declare -r HELP="usage: $0 [all]

Run autopep8 on all staged and unstaged *.py files in the git index

If you specified \"all\" as an argument, it will run autopep8 on all *.py files
in the repository, regardless of staging.
"


# Parse a value out of the CONF file and return it with a '--' in front
get_arg() {
    set +e
    local _value=$(grep $1 $CONF)
    set -e
    if [ "$_value" ]; then
        echo "--$_value"
    fi
}

main() {
    local _autopep="autopep8 -j 0 -i"
    for _arg in ${ARGS[@]}; do
        _autopep="$_autopep $(get_arg $_arg)"
    done
    if [ "$1" == "-h" ]; then
        echo "$HELP"
    elif [ "$1" == "all" ]; then
        local _package=$(basename $(readlink -f .))
        find $_package -name '*.py' | xargs $_autopep
    else
        local _diff=$(git diff --name-only --diff-filter=ACMRT | grep '.py$')
        if [ "$_diff" ]; then
            echo "$_diff" | xargs $_autopep
        fi
        local _diff_cached=$(git diff --cached --name-only --diff-filter=ACMRT | grep '.py$')
        if [ "$_diff_cached" ]; then
            echo "$_diff_cached" | xargs $_autopep
        fi
    fi
}

main "$@"
