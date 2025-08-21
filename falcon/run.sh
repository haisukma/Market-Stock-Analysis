#!/bin/bash

# tambah folder libs agar python bisa baca package
export PYTHONPATH=$(pwd)/libs:$PYTHONPATH

# FastAPI dengan uvicorn
# uvicorn main:app --reload --host 0.0.0.0 --port 8000
uvicorn appnew.main:app --reload --host 0.0.0.0 --port 8000