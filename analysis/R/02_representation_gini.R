# ---------------------------------------------------------------------------
# 02 - Territorial representation: recompute the Gini from the raw tables.
#
#   Rscript analysis/R/02_representation_gini.R
#
# This deliberately does NOT read data/processed/indices/representation_gini.csv.
# It rebuilds the index from persons.csv, appointments.csv and governorates.csv
# in base R, then checks its own answer against the published file. If the two
# disagree the script fails loudly - which makes it a reproduction test of the
# published numbers, not a re-display of them.
# ---------------------------------------------------------------------------

govtn_script_dir <- function() {
  args <- commandArgs(trailingOnly = FALSE)
  file_arg <- grep("^--file=", args, value = TRUE)
  if (length(file_arg)) {
    return(dirname(normalizePath(sub("^--file=", "", file_arg[1]))))
  }
  frame <- sys.frame(1)$ofile
  if (!is.null(frame)) return(dirname(normalizePath(frame)))
  getwd()
}
source(file.path(govtn_script_dir(), "load_govtn.R"))

out_dir <- file.path(dirname(dirname(govtn_script_dir())), "output", "tables")
dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)

persons      <- govtn_load("persons")
appointments <- govtn_load("appointments")
governorates <- govtn_load("governorates")

# --- The measure ------------------------------------------------------------
# Governorates ordered from least to best represented by ministers per capita.
# x = cumulative share of population, y = cumulative share of ministers.
# G = 0 is exact proportionality; G = 1 is every minister from one tiny place.
#
# Governorates that supplied NO minister must stay in: they still consume their
# share of the population along the curve, and they are precisely the cases the
# measure exists to capture. Dropping them understates inequality.
representation_gini <- function(counts, populations) {
  stopifnot(!is.null(names(populations)))
  n <- counts[names(populations)]
  n[is.na(n)] <- 0
  if (sum(n) == 0) return(NA_real_)
  ordered <- order(n / populations)
  x <- c(0, cumsum(populations[ordered]) / sum(populations))
  y <- c(0, cumsum(n[ordered]) / sum(n))
  # Trapezoid area under the Lorenz curve.
  area <- sum(diff(x) * (head(y, -1) + tail(y, -1)) / 2)
  1 - 2 * area
}

# --- Partitions -------------------------------------------------------------
# The level of this index is only defined relative to a partition, and
# Tunisia's have moved: Ariana and Ben Arous were split off Greater Tunis in
# 1983 and Manouba in 2000, after most of these ministers were born. Splitting
# the capital four ways concentrates it artificially. Compute all three; the
# trend is what survives.
GREATER_TUNIS <- c("Tunis", "Ariana", "Ben Arous", "Manouba")

unit_of <- function(governorate, units) {
  switch(units,
    governorate          = governorate,
    greater_tunis_merged = ifelse(governorate %in% GREATER_TUNIS,
                                  "Greater Tunis", governorate),
    region               = governorates$region_type[
                             match(governorate, governorates$governorate)],
    stop("unknown units: ", units)
  )
}

unit_populations <- function(units) {
  key <- unit_of(governorates$governorate, units)
  tapply(governorates$population, key, sum)
}

# One row per person per era: a minister serving under two regimes counts in
# each, matching the convention used throughout the dataset.
pairs <- unique(appointments[!is.na(appointments$era), c("person_id", "era")])
pairs <- merge(pairs, persons[, c("person_id", "birth_governorate")],
               by = "person_id")
coded <- pairs[!is.na(pairs$birth_governorate), ]

# Eras with too few coded ministers, and the post-2021 cabinets whose coded
# sample is almost entirely holdovers, are not reported. See docs/CODEBOOK.md.
ERAS <- c("protectorate", "bourguiba", "ben_ali", "transition", "second_republic")
UNITS <- c("governorate", "greater_tunis_merged", "region")

result <- do.call(rbind, lapply(UNITS, function(units) {
  populations <- unit_populations(units)
  do.call(rbind, lapply(ERAS, function(era) {
    block <- coded[coded$era == era, ]
    counts <- table(unit_of(block$birth_governorate, units))
    data.frame(units = units, era = era, coded = nrow(block),
               gini = representation_gini(counts, populations))
  }))
}))

wide <- reshape(result[, c("units", "era", "gini")], idvar = "era",
                timevar = "units", direction = "wide")
names(wide) <- sub("^gini\\.", "", names(wide))
wide <- wide[match(ERAS, wide$era), ]

cat("Gini of ministerial representation, by era and partition\n\n")
print(format(wide, digits = 3), row.names = FALSE)

write.csv(result, file.path(out_dir, "02_representation_gini_recomputed.csv"),
          row.names = FALSE, fileEncoding = "UTF-8")

# --- Check against the published file --------------------------------------
published <- govtn_load("representation_gini")
published <- published[published$era %in% ERAS & !is.na(published$gini_representation), ]
merged <- merge(result, published[, c("units", "era", "gini_representation")],
                by = c("units", "era"))
stopifnot(nrow(merged) == nrow(result))
worst <- max(abs(merged$gini - merged$gini_representation))
cat(sprintf("\nAgreement with data/processed/indices/representation_gini.csv: max |diff| = %.2e\n",
            worst))
# The published file rounds to 4 decimal places, so the most two identical
# implementations can agree is 5e-5. A tolerance tighter than that would fail
# on the rounding rather than on any real disagreement.
if (worst > 1e-4) {
  stop("recomputed index does not match the published file", call. = FALSE)
}
cat("Reproduced, to the precision the published file is rounded to.\n")
