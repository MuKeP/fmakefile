#!/bin/bash
sudo rm /usr/bin/fmakefile 2>/dev/null
sudo ln -s $PWD/run.py /usr/bin/fmakefile