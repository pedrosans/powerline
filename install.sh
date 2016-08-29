#!/bin/bash
echo 'y' | pip uninstall powerline-status
pip install --user .
powerline-daemon -k
powerline-daemon -q
