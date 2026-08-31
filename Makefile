.PHONY: install build run test clean

install:
	pip install -r requirements.txt

build:            ## regenerate the plant record, refit every model, print metrics
	python -m twin.pipeline

run:              ## start the dashboard (builds first if artifacts are missing)
	python run.py

test:
	python -m pytest tests -q

clean:
	rm -rf data artifacts **/__pycache__
