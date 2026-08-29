# GovMembersTN - Tunisian government members dataset
PY ?= python3
export PYTHONPATH := src

.PHONY: help install test preflight harvest build networks validate inequality codebook analysis figures bundle all clean queries

help:
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install:  ## Install Python dependencies
	$(PY) -m pip install -r requirements.txt

test:  ## Run the test suite
	$(PY) -m pytest tests/ -q

preflight:  ## Check every source host is reachable before harvesting
	$(PY) -m govtn.preflight

harvest:  ## Fetch from Wikidata, Wikipedia and Leaders (needs network access)
	$(PY) -m govtn.pipeline --stages wikidata,wikipedia,leaders

build:  ## Assemble the analysis tables from whatever has been harvested
	$(PY) -m govtn.build

networks:  ## Build the edge lists and graph files
	$(PY) -m govtn.networks

validate:  ## Run data quality checks and write VALIDATION.md
	$(PY) -m govtn.validate

inequality:  ## Territorial representation index (Gini) per era
	$(PY) -m govtn.inequality

codebook:  ## Regenerate data/processed/codebook.csv from the tables
	$(PY) -m govtn.codebook

analysis:  ## Run the example analyses in both Python and R
	$(PY) analysis/python/01_descriptives.py
	$(PY) analysis/python/02_representation_gini.py
	$(PY) analysis/python/03_networks.py
	@command -v Rscript >/dev/null 2>&1 && { \
	  Rscript analysis/R/01_descriptives.R; \
	  Rscript analysis/R/02_representation_gini.R; \
	  Rscript analysis/R/03_networks.R; \
	} || echo "Rscript not found - skipped the R examples"

figures:  ## Rebuild the publication figures in figures/
	$(PY) figures/make_figures.py

bundle:  ## Zip the analysis-ready data + docs for people who don't want the pipeline
	@rm -rf dist && mkdir -p dist/GovMembersTN
	@mkdir -p dist/GovMembersTN/data
	@cp -r data/processed dist/GovMembersTN/data/processed
	@cp -r analysis docs figures dist/GovMembersTN/
	@cp README.md LICENSE CITATION.cff dist/GovMembersTN/
	@cd dist && zip -qr GovMembersTN-data.zip GovMembersTN && rm -rf GovMembersTN
	@echo "wrote dist/GovMembersTN-data.zip ($$(du -h dist/GovMembersTN-data.zip | cut -f1))"

all: preflight  ## Full pipeline: preflight -> harvest -> build -> networks -> validate
	$(PY) -m govtn.pipeline

offline:  ## Rebuild everything from cached payloads, no network
	$(PY) -m govtn.pipeline --no-fetch

queries:  ## Print the SPARQL to run by hand at query.wikidata.org
	$(PY) -m govtn.sources.wikidata --print-queries

clean:  ## Remove generated tables (keeps the raw payload cache)
	rm -f data/processed/*.csv data/processed/*.gexf data/processed/*.graphml \
	      data/processed/MANIFEST.json data/processed/VALIDATION.md
	rm -f data/interim/*.json data/interim/*.csv
