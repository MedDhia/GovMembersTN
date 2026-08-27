# ---------------------------------------------------------------------------
# 03 - Networks: co-membership degree and regional assortativity.
#
#   Rscript analysis/R/03_networks.R
#
# Base R only. igraph is not required; if it happens to be installed the script
# uses it for community detection, and says so when it is not. Everything up to
# that point runs on a bare R installation.
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

persons <- govtn_load("persons")
edges   <- govtn_load("edges_co_membership")

cat(sprintf("Co-membership network: %d nodes, %d edges\n",
            nrow(persons), nrow(edges)))
cat("Edge weight is DAYS OF OVERLAPPING SERVICE, not a count of shared cabinets.\n")

# --- Degree and weighted degree --------------------------------------------
# The edge list is undirected and stored once per pair, so each endpoint has to
# be counted on both sides.
endpoints <- c(edges$source, edges$target)
weights   <- c(edges$weight, edges$weight)

degree <- table(endpoints)
strength <- tapply(weights, endpoints, sum)

central <- data.frame(
  person_id = names(degree),
  degree = as.integer(degree),
  weighted_degree = as.numeric(strength[names(degree)]),
  stringsAsFactors = FALSE
)
central <- merge(central, persons[, c("person_id", "name", "birth_governorate",
                                      "n_appointments")],
                 by = "person_id", all.x = TRUE)
central <- central[order(-central$degree), ]

cat("\nMost connected ministers by co-membership degree\n")
print(head(central[, c("name", "degree", "weighted_degree", "n_appointments")], 10),
      row.names = FALSE)
write.csv(central, file.path(out_dir, "03_centrality.csv"),
          row.names = FALSE, fileEncoding = "UTF-8")

# --- Regional assortativity -------------------------------------------------
# Nominal assortativity on region of birth: a direct test of regional closure.
#
# Use birth_governorate, NOT birth_region. The latter is Wikidata's raw P131
# label, which names a delegation - several hundred near-unique categories that
# drive the coefficient towards zero and make closure look absent.
#
# Vertices with no coded governorate are dropped rather than pooled: ministers
# born abroad have no governorate by design, and letting NA become its own
# category would count "born abroad" as a region and inflate the coefficient.
attr_of <- setNames(persons$birth_governorate, persons$person_id)
a <- attr_of[edges$source]
b <- attr_of[edges$target]
keep <- !is.na(a) & !is.na(b)
a <- a[keep]; b <- b[keep]
w <- edges$weight[keep]

cat(sprintf("\nEdges with both endpoints coded: %d of %d\n", sum(keep), nrow(edges)))

# Newman's nominal assortativity, computed on the edge mixing matrix.
levels_all <- sort(unique(c(a, b)))
e <- matrix(0, length(levels_all), length(levels_all),
            dimnames = list(levels_all, levels_all))
for (i in seq_along(a)) {
  # Each undirected edge contributes to both cells, so the matrix is symmetric.
  e[a[i], b[i]] <- e[a[i], b[i]] + w[i]
  e[b[i], a[i]] <- e[b[i], a[i]] + w[i]
}
e <- e / sum(e)
tr <- sum(diag(e))
sq <- sum(rowSums(e) * colSums(e))
r_weighted <- (tr - sq) / (1 - sq)

# Unweighted, so the result does not depend on tenure length.
e2 <- matrix(0, length(levels_all), length(levels_all),
             dimnames = list(levels_all, levels_all))
for (i in seq_along(a)) {
  e2[a[i], b[i]] <- e2[a[i], b[i]] + 1
  e2[b[i], a[i]] <- e2[b[i], a[i]] + 1
}
e2 <- e2 / sum(e2)
r_plain <- (sum(diag(e2)) - sum(rowSums(e2) * colSums(e2))) /
           (1 - sum(rowSums(e2) * colSums(e2)))

cat(sprintf("Assortativity by governorate of birth: %.4f (unweighted), %.4f (by overlap days)\n",
            r_plain, r_weighted))
cat("Near zero means ministers from the same governorate are no more likely to\n")
cat("serve together than chance - co-membership is set by cabinet timing, not origin.\n")

write.csv(
  data.frame(measure = c("assortativity_unweighted", "assortativity_weighted"),
             value = c(r_plain, r_weighted)),
  file.path(out_dir, "03_assortativity.csv"),
  row.names = FALSE, fileEncoding = "UTF-8")

# --- Optional: communities --------------------------------------------------
if (requireNamespace("igraph", quietly = TRUE)) {
  g <- igraph::graph_from_data_frame(
    edges[, c("source", "target", "weight")], directed = FALSE)
  communities <- igraph::cluster_louvain(g, weights = igraph::E(g)$weight)
  cat(sprintf("\nLouvain modularity: %.3f across %d communities\n",
              igraph::modularity(communities), length(communities)))
} else {
  cat("\n(igraph not installed - skipping community detection.",
      "install.packages(\"igraph\") to enable it.)\n")
}

cat("\nWrote 2 tables to ", out_dir, "\n", sep = "")
