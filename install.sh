#!/bin/bash
echo "*** Creating Python Venv"
python3 -m venv venv
source ./venv/bin/activate

echo "*** Installing Python requirements"
pip install -r requirements.txt
