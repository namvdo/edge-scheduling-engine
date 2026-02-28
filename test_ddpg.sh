#!/bin/bash
export PYTHONUNBUFFERED=1
source .venv/bin/activate
export PYTHONPATH=.
python services/scheduler/ml/train.py
