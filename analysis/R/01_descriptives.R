# ---------------------------------------------------------------------------
# 01 - Descriptives: what is in the dataset, and how much of it is missing.
#
#   Rscript analysis/R/01_descriptives.R
#
# Base R only. Writes output/tables/01_*.csv.
# ---------------------------------------------------------------------------

# Locate the loader relative to THIS file, so the script runs from anywhere.
govtn_script_dir <- function() {
  args <- commandArgs(trailingOnly = FALSE)
  file_arg <- grep("^--file=", args, value = TRUE)
  if (length(file_arg)) {
    return(dirname(normalizePath(sub("^--file=", "", file_arg[1]))))
  }
  frame <- sys.frame(1)$ofile              # set when run via source()
  if (!is.null(frame)) return(dirname(normalizePath(frame)))
  getwd()
}
source(file.path(govtn_script_dir(), "load_govtn.R"))

out_dir <- file.path(dirname(dirname(govtn_script_dir())), "output", "tables")
dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)

persons      <- govtn_load("persons")
appointments <- govtn_load("appointments")
cabinets     <- govtn_load("cabinets")

cat("GovMembersTN\n")
cat(sprintf("  %d persons, %d appointments, %d cabinets\n",
            nrow(persons), nrow(appointments), nrow(cabinets)))
cat(sprintf("  appointments dated %s to %s\n",
            format(min(appointments$start_date, na.rm = TRUE)),
            format(max(appointments$start_date, na.rm = TRUE))))

# --- 1. Attribute coverage -------------------------------------------------
# The first thing to look at in a dataset built from encyclopaedic sources.
# Every share computed below is conditional on these.
interesting <- c("birth_date", "birth_place", "birth_governorate", "gender",
                 "education", "parties", "occupations", "wikidata_qid")
coverage <- data.frame(
  variable = interesting,
  present  = sapply(interesting, function(v) sum(!is.na(persons[[v]]))),
  coverage = sapply(interesting, function(v) mean(!is.na(persons[[v]]))),
  row.names = NULL
)
cat("\nPerson-level coverage\n")
print(transform(coverage, coverage = sprintf("%.0f%%", coverage * 100)),
      row.names = FALSE)
write.csv(coverage, file.path(out_dir, "01_attribute_coverage.csv"),
          row.names = FALSE, fileEncoding = "UTF-8")

# --- 2. Appointments per decade --------------------------------------------
# Catches silent holes: a seventy-year trend computed over a half-empty decade
# is a statement about the sources, not about Tunisia.
decade <- (as.integer(format(appointments$start_date, "%Y")) %/% 10) * 10
by_decade <- as.data.frame(table(decade = decade[!is.na(decade)]))
names(by_decade)[2] <- "appointments"
cat("\nAppointments per decade\n")
print(by_decade, row.names = FALSE)
write.csv(by_decade, file.path(out_dir, "01_appointments_by_decade.csv"),
          row.names = FALSE, fileEncoding = "UTF-8")

# --- 3. Women in government, by era ----------------------------------------
# Counted once per person per era: a minister serving under two regimes counts
# in each, which is the convention used throughout the dataset.
pairs <- unique(appointments[!is.na(appointments$era), c("person_id", "era")])
pairs <- merge(pairs, persons[, c("person_id", "gender")], by = "person_id")
known <- pairs[!is.na(pairs$gender), ]

era_levels <- c("protectorate", "protectorate_end", "monarchy", "bourguiba",
                "ben_ali", "transition", "second_republic", "saied_exception")
gender <- do.call(rbind, lapply(era_levels, function(e) {
  block <- known[known$era == e, ]
  if (!nrow(block)) return(NULL)
  data.frame(era = e, ministers = nrow(block),
             women = sum(block$gender == "female"),
             share_women = mean(block$gender == "female"))
}))
cat("\nWomen in government, by era\n")
print(transform(gender, share_women = sprintf("%.1f%%", share_women * 100)),
      row.names = FALSE)
write.csv(gender, file.path(out_dir, "01_women_by_era.csv"),
          row.names = FALSE, fileEncoding = "UTF-8")

cat("\nWrote 3 tables to ", out_dir, "\n", sep = "")
