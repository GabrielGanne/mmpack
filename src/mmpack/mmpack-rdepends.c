/*
 * @mindmaze_header@
 */

#if defined (HAVE_CONFIG_H)
# include <config.h>
#endif

#include <mmargparse.h>
#include <mmerrno.h>
#include <mmlib.h>
#include <mmsysio.h>
#include <string.h>

#include "action-solver.h"
#include "cmdline.h"
#include "common.h"
#include "context.h"
#include "mmpack-install.h"
#include "mmpack-rdepends.h"
#include "mmstring.h"
#include "package-utils.h"
#include "utils.h"


static int recursive = 0;
static int sumsha = 0;
static const char* repo_name = NULL;

static const struct mmarg_opt cmdline_optv[] = {
	{"repo", MMOPT_NEEDSTR, NULL, {.sptr = &repo_name},
	 "Specify @REPO_NAME as the address of package repository"},
	{"r|recursive", MMOPT_NOVAL|MMOPT_INT, "1", {.iptr = &recursive},
	 "Print recursively the reverse dependencies"},
	{"sumsha", MMOPT_NOVAL|MMOPT_INT, "1", {.iptr = &sumsha},
	 "Search the reverse dependencies of the package referenced thanks to "
	 "its sumsha"},
};


struct list_pkgs {
	struct mmpkg const * pkg;
	struct list_pkgs * next;
};


static
void add_elt_list_pkgs(struct list_pkgs ** list, struct mmpkg const * pkg)
{
	struct list_pkgs * elt = malloc(sizeof(struct list_pkgs));

	elt->pkg = pkg;

	elt->next = *list;
	*list = elt;
}


static
int search_elt_list_pkgs(struct list_pkgs * list, struct mmpkg const * pkg)
{
	struct list_pkgs * curr;

	for (curr = list; curr != NULL; curr = curr->next) {
		if (curr->pkg == pkg)
			return 0;
	}

	return -1;
}


static
void destroy_all_elt(struct list_pkgs ** list)
{
	struct list_pkgs * next;
	struct list_pkgs * curr = *list;

	while (curr) {
		next = curr->next;
		free(curr);
		curr = next;
	}
}


static
void dump_reverse_dependencies(struct list_pkgs * list)
{
	struct list_pkgs * curr;

	for (curr = list; curr != NULL; curr = curr->next) {
		printf("%s (%s)\n", curr->pkg->name, curr->pkg->version);
	}
}


static
int package_in_repo(struct mmpkg const * pkg, mmstr const * repo_name)
{
	struct from_repo * from;

	for (from = pkg->from_repo; from != NULL; from = from->next) {
		if (strcmp(from->repo->name, repo_name) == 0) {
			return 1;
		}
	}

	return 0;
}


static
int find_reverse_dependencies(struct binindex binindex,
                              struct mmpkg const* pkg,
                              const char * repo_name,
                              struct list_pkgs** rdep_list)
{
	struct rdeps_iter rdep_it;
	struct mmpkg * rdep;

	if (!pkg || (repo_name && !package_in_repo(pkg, repo_name)))
		return -1;

	// iterate over all the potential reverse dependencies of pkg
	for (rdep = rdeps_iter_first(&rdep_it, pkg, &binindex); rdep != NULL;
	     rdep = rdeps_iter_next(&rdep_it)) {
		// check that the reverse dependency belongs to the
		// repository inspected
		if (repo_name && !package_in_repo(rdep, repo_name))
			continue;

		//check that the dependency is not already written
		if (search_elt_list_pkgs(*rdep_list, rdep))
			add_elt_list_pkgs(rdep_list, rdep);

		if (recursive)
			find_reverse_dependencies(binindex, rdep, repo_name,
			                          rdep_list);
	}

	return 0;
}


/**
 * mmpack_rdepends() - main function for the rdepends command
 * @ctx: mmpack context
 * @argc: number of arguments
 * @argv: array of arguments
 *
 * show given package reverse dependencies.
 *
 * Return: 0 on success, -1 otherwise
 */
LOCAL_SYMBOL
int mmpack_rdepends(struct mmpack_ctx * ctx, int argc, const char* argv[])
{
	struct mmpkg const* pkg;
	int arg_index, rv = -1;
	struct list_pkgs * rdep_list = NULL;

	struct mmarg_parser parser = {
		.flags = mmarg_is_completing() ? MMARG_PARSER_COMPLETION : 0,
		.args_doc = RDEPENDS_SYNOPSIS,
		.optv = cmdline_optv,
		.num_opt = MM_NELEM(cmdline_optv),
		.execname = "mmpack",
	};

	arg_index = mmarg_parse(&parser, argc, (char**)argv);
	if (mmarg_is_completing()) {
		if (arg_index + 1 < argc)
			return 0;

		return complete_pkgname(ctx, argv[argc - 1], AVAILABLE_PKGS);
	}

	if (arg_index + 1 != argc) {
		fprintf(stderr, "Bad usage of rdepends command.\n"
		        "Usage:\n\tmmpack "RDEPENDS_SYNOPSIS "\n");
		return -1;
	}

	// Load prefix configuration and caches
	if (mmpack_ctx_use_prefix(ctx, 0))
		return -1;

	if (!sumsha) {
		if ((pkg = parse_pkg(ctx, argv[arg_index])) == NULL)
			return -1;
	} else {
		if (!(pkg = find_package_by_sumsha(ctx, argv[arg_index])))
			return -1;
	}


	if (find_reverse_dependencies(ctx->binindex, pkg, repo_name,
	                              &rdep_list)) {
		printf("No package found\n");
		goto exit;
	}

	dump_reverse_dependencies(rdep_list);

	rv = 0;

exit:
	destroy_all_elt(&rdep_list);
	return rv;
}
