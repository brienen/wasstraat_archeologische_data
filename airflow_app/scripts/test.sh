#!/bin/bash
shopt -s globstar
for mdbfile in "$1"/**/*.mdb
do
    echo "$mdbfile"
done