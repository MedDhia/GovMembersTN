# GovMembersTN - Tunisian government members dataset
PY ?= python3
export PYTHONPATH := src

.PHONY: help install test harvest build networks validate all clean queries

help:
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install:  ## Install Python dependencies
	$(PY) -m pip install -r requirements.txt

test:  ## Run the test suite
	$(PY) -m pytest tests/ -q

harvest:  ## Fetch from Wikidata, Wikipedia and Leaders (needs network access)
	$(PY) -m govtn.pipeline --stages wikidata,wikipedia,leaders --skip-harvest=false

build:  ## Assemble the analysis tables from whatever has been harvested
	$(PY) -m govtn.build

networks:  ## Build the edge lists and graph files
	$(PY) -m govtn.networks

validate:  ## Run data quality checks and write VALIDATION.md
	$(PY) -m govtn.validate

all:  ## Full pipeline: harvest -> build -> networks -> validate
	$(PY) -m govtn.pipeline

offline:  ## Rebuild everything from cached payloads, no network
	$(PY) -m govtn.pipeline --no-fetch

queries:  ## Print the SPARQL to run by hand at query.wikidata.org
	$(PY) -m govtn.sources.wikidata --print-queries

clean:  ## Remove generated tables (keeps the raw payload cache)
	rm -f data/processed/*.csv data/processed/*.gexf data/processed/*.graphml \
	      data/processed/MANIFEST.json data/processed/VALIDATION.md
	rm -f data/interim/*.json data/interim/*.csv
