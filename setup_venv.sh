#!/bin/bash

# Create a virtual environment
python3 -m venv venv

# Activate the virtual environment
source venv/bin/activate

# Install Pyro5
python3 -m pip install pyro5

echo "Configure TouchDesigner to use additional Python path:"
echo "${PWD}/venv/lib/python3.11/site-packages"
