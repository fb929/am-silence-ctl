#!/bin/bash
set -e

echo "INFO: $0 started" 1>&2

# for building rpm and deb packages via fpm
PROJECT_NAME="am-silence-ctl"
CURRENT_DIR=$(pwd)
export LANG=en_US.UTF-8

install -d \
    build/ \
    build/etc/$PROJECT_NAME \

python3 -m venv build/opt/venv/$PROJECT_NAME/
source build/opt/venv/$PROJECT_NAME/bin/activate
pip3 install --upgrade pip
pip3 install --requirement ./code/requirements.txt

# config file
rsync -avP example/config.yml build/etc/$PROJECT_NAME/example.yml

# project files
rsync -avP \
    --delete-excluded \
    --exclude='.git/' \
    --exclude='__pycache__/' \
    --exclude='*.py[cod]' \
    --exclude='*$py.class' \
    --exclude='.build-id/' \
    ./code/ build/opt/venv/$PROJECT_NAME/$PROJECT_NAME/

# fixed venv paths
perl -i -pe"s|${CURRENT_DIR}/build/|/|" $(grep -rl "${CURRENT_DIR}/" build/ | grep -v '\.pyc') || exit 1

echo "INFO: $0 ended" 1>&2
