# ---------------------------------------------------------------------------
# GovMembersTN — loader for R
#
# Base R only. No packages to install, nothing fetched from the network: clone
# or unzip the repository and this works offline on a fresh R installation.
#
#   source("analysis/R/load_govtn.R")
#   tn <- govtn_load_all()
#   str(tn$persons)
#
# Column types are not hard-coded here. They are read from
# `data/processed/codebook.csv`, which is generated from the tables themselves,
# so dates parse as Date and flags as logical without this file having to be
# kept in step with the schema.
# ---------------------------------------------------------------------------

# Tables and the subdirectory each lives in.
GOVTN_TABLES <- list(
  persons                       = "",
  appointments                  = "",
  cabinets                      = "",
  spells                        = "",
  portfolios                    = "",
  governorates                  = "",
  eras                          = "",
  codebook                      = "",
  representation_gini           = "indices",
  representation_changes        = "indices",
  representation_by_governorate = "indices",
  edges_bipartite               = "networks",
  edges_co_membership           = "networks",
  edges_succession              = "networks",
  edges_homophily               = "networks"
)


govtn_data_dir <- function(start = getwd()) {
  # Walk up from the working directory looking for the published tables, so the
  # scripts run whether R was started at the repository root, inside
  # analysis/R/, or from an RStudio project anywhere in the tree.
  path <- normalizePath(start, mustWork = FALSE)
  for (i in 1:6) {
    candidate <- file.path(path, "data", "processed")
    if (file.exists(file.path(candidate, "persons.csv"))) {
      return(normalizePath(candidate))
    }
    parent <- dirname(path)
    if (identical(parent, path)) break
    path <- parent
  }
  stop("could not find data/processed/persons.csv above '", start,
       "'. Set the working directory to the repository root, or pass ",
       "dir = to govtn_load().", call. = FALSE)
}


govtn_codebook <- function(dir = govtn_data_dir()) {
  path <- file.path(dir, "codebook.csv")
  if (!file.exists(path)) return(NULL)
  read.csv(path, stringsAsFactors = FALSE, encoding = "UTF-8",
           colClasses = "character")
}


govtn_load <- function(table, dir = govtn_data_dir(), typed = TRUE) {
  if (!table %in% names(GOVTN_TABLES)) {
    stop("unknown table '", table, "'. Available: ",
         paste(names(GOVTN_TABLES), collapse = ", "), call. = FALSE)
  }
  sub <- GOVTN_TABLES[[table]]
  path <- if (nzchar(sub)) file.path(dir, sub, paste0(table, ".csv")) else
                           file.path(dir, paste0(table, ".csv"))
  if (!file.exists(path)) {
    stop("missing ", path, call. = FALSE)
  }

  # Read every column as character first. Letting read.csv guess turns
  # identifiers that look numeric into numbers and drops their leading zeros,
  # and turns a column that is empty in the first rows into logical NA.
  frame <- read.csv(path, stringsAsFactors = FALSE, encoding = "UTF-8",
                    colClasses = "character", na.strings = c("", "NA"),
                    check.names = FALSE)

  # The CSVs are UTF-8. Mark the strings as such rather than trusting the
  # session locale, which is how Arabic names arrive as mojibake on a Windows
  # machine running a non-UTF-8 locale.
  for (column in names(frame)) {
    if (is.character(frame[[column]])) Encoding(frame[[column]]) <- "UTF-8"
  }

  if (!typed) return(frame)

  book <- govtn_codebook(dir)
  if (is.null(book)) {
    warning("codebook.csv not found; returning all columns as character",
            call. = FALSE)
    return(frame)
  }
  spec <- book[book$table == table, c("variable", "type")]
  for (i in seq_len(nrow(spec))) {
    column <- spec$variable[i]
    if (!column %in% names(frame)) next
    frame[[column]] <- switch(
      spec$type[i],
      date    = as.Date(frame[[column]]),
      # Python writes True/False; as.logical accepts both those and TRUE/FALSE.
      boolean = as.logical(frame[[column]]),
      integer = as.integer(frame[[column]]),
      numeric = as.numeric(frame[[column]]),
      frame[[column]]
    )
  }
  frame
}


govtn_load_all <- function(dir = govtn_data_dir(), tables = names(GOVTN_TABLES)) {
  out <- lapply(tables, function(t) govtn_load(t, dir = dir))
  names(out) <- tables
  out
}


govtn_describe <- function(table, variable = NULL, dir = govtn_data_dir()) {
  # What does this column mean? Answered without leaving the console.
  book <- govtn_codebook(dir)
  if (is.null(book)) stop("codebook.csv not found", call. = FALSE)
  rows <- book[book$table == table, ]
  if (!is.null(variable)) rows <- rows[rows$variable == variable, ]
  if (!nrow(rows)) stop("no such table or variable", call. = FALSE)
  for (i in seq_len(nrow(rows))) {
    cat(sprintf("%s  [%s]  %s%% present\n", rows$variable[i], rows$type[i],
                round(as.numeric(rows$coverage[i]) * 100)))
    if (nzchar(rows$levels[i])) cat("  values: ", rows$levels[i], "\n", sep = "")
    if (nzchar(rows$description[i])) cat("  ", rows$description[i], "\n", sep = "")
    cat("\n")
  }
  invisible(rows)
}


# `person_id` joins persons to appointments; `cabinet_id` joins appointments to
# cabinets; `spell_id` joins either to spells. Everything else is a lookup.
govtn_panel <- function(dir = govtn_data_dir()) {
  # The most common starting point: one row per appointment, with the person's
  # attributes and the cabinet's dates already attached.
  appointments <- govtn_load("appointments", dir = dir)
  persons <- govtn_load("persons", dir = dir)
  cabinets <- govtn_load("cabinets", dir = dir)

  person_cols <- setdiff(names(persons), names(appointments))
  cabinet_cols <- setdiff(names(cabinets), c(names(appointments), person_cols))

  out <- merge(appointments, persons[, c("person_id", person_cols)],
               by = "person_id", all.x = TRUE)
  out <- merge(out, cabinets[, c("cabinet_id", cabinet_cols)],
               by = "cabinet_id", all.x = TRUE, suffixes = c("", "_cabinet"))
  out
}
