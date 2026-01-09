#!/bin/bash

# Requires Conda for setting up environments.
if ! command -v conda &> /dev/null
then
    echo "conda could not be found. Please install conda before executing this tests."
    exit 1
fi

GREEN='\033[0;32m'
NC='\033[0m'

# Python 3.10
conda create -y --name py310 python=3.10
conda activate py310
pip install -e .
python ./integration_test_all.py
conda activate base
conda env remove -y --name py310
echo -e "${GREEN}Successfully finished test on Python 3.10${NC}"

# Python 3.11
conda create -y --name py311 python=3.11
conda activate py311
pip install -e .
python ./integration_test_all.py
conda activate base
conda env remove -y --name py311
echo -e "${GREEN}Successfully finished test on Python 3.11${NC}"

# Python 3.12
conda create -y --name py312 python=3.12
conda activate py312
pip install -e .
python ./integration_test_all.py
conda activate base
conda env remove -y --name py312
echo -e "${GREEN}Successfully finished test on Python 3.12${NC}"

# Python 3.13
conda create -y --name py313 python=3.13
conda activate py313
pip install -e .
python ./integration_test_all.py
conda activate base
conda env remove -y --name py313
echo -e "${GREEN}Successfully finished test on Python 3.13${NC}"

# Python 3.14
conda create -y --name py314 python=3.14
conda activate py314
pip install -e .
python ./integration_test_all.py
conda activate base
conda env remove -y --name py314
echo -e "${GREEN}Successfully finished test on Python 3.14${NC}"

echo -e "${GREEN}Successfully finished all integration tests !!${NC}"