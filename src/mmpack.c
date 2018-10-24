/*
 * @mindmaze_header@
 */

#if defined (HAVE_CONFIG_H)
# include <config.h>
#endif

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <mmargparse.h>
#include <mmerrno.h>
#include <mmsysio.h>

#include "common.h"
#include "mmpack-install.h"
#include "mmpack-mkprefix.h"
#include "mmpack-remove.h"
#include "mmpack-runprefix.h"
#include "mmpack-search.h"
#include "mmpack-update.h"

static const char mmpack_doc[] =
	"mmpack is a cross-platform package manager."
	"\n\n"
	"It is designed to work without any need for root access, and to allow "
	"multiple coexisting project versions within project prefixes (akin to "
	"python's virtualenv sandboxes)"
	"\n\n"
	"mmpack is the entry point for many package management commands (update, "
	"install, remove...)."
;

static const char arguments_docs[] =
	"[options] "MKPREFIX_SYNOPSIS"\n"
	"[options] "UPDATE_SYNOPSIS"\n"
	"[options] "INSTALL_SYNOPSIS"\n"
	"[options] "REMOVE_SYNOPSIS"\n"
	"[options] "RUNPREFIX_SYNOPSIS"\n"
	"[options] "SEARCH_SYNOPSIS"\n";

static struct mmpack_opts cmdline_opts;

static const struct mmarg_opt cmdline_optv[] = {
	{"p|prefix", MMOPT_NEEDSTR, NULL, {.sptr = &cmdline_opts.prefix},
	 "Use @PATH as install prefix."},
	{"version", MMOPT_NOVAL, "set", {.sptr = &cmdline_opts.version},
	 "Display mmpack version"},
};

int main(int argc, char* argv[])
{
	int rv, arg_index, cmd_argc;
	const char** cmd_argv;
	const char* cmd;
	struct mmpack_ctx ctx = {0};
	struct mmarg_parser parser = {
		.doc = mmpack_doc,
		.args_doc = arguments_docs,
		.optv = cmdline_optv,
		.num_opt = MM_NELEM(cmdline_optv),
		.execname = "mmpack",
	};

	/* Parse command line options */
	rv = 0;
	arg_index = mmarg_parse(&parser, argc, argv);

	/* handle non-command options */
	if (cmdline_opts.version) {
		printf("%s\n", PACKAGE_STRING);
		goto exit;
	}

	/* Check command is supplied */
	if (arg_index+1 > argc) {
		fprintf(stderr, "Invalid number of argument."
		                " Run \"%s --help\" to see Usage\n", argv[0]);
		rv = -1;
		goto exit;
	}
	cmd = argv[arg_index];
	cmd_argv = (const char**)argv + arg_index;
	cmd_argc = argc - arg_index;

	/* Initialize context according to command line options */
	rv = mmpack_ctx_init(&ctx, &cmdline_opts);
	if (rv != 0)
		goto exit;

	/* Dispatch command */
	if (STR_EQUAL(cmd, strlen(cmd), "mkprefix")) {
		rv = mmpack_mkprefix(&ctx, cmd_argc, cmd_argv);
	} else if (STR_EQUAL(cmd, strlen(cmd), "update")) {
		rv = mmpack_update_all(&ctx);
	} else if (STR_EQUAL(cmd, strlen(cmd), "install")) {
		rv = mmpack_install(&ctx, cmd_argc, cmd_argv);
	} else if (STR_EQUAL(cmd, strlen(cmd), "remove")
	           || STR_EQUAL(cmd, strlen(cmd), "uninstall")) {
		rv = mmpack_remove(&ctx, cmd_argc, cmd_argv);
	} else if (STR_EQUAL(cmd, strlen(cmd), "runprefix")) {
		rv = mmpack_runprefix(&ctx, cmd_argc, cmd_argv);
	} else if (STR_EQUAL(cmd, strlen(cmd), "search")) {
		rv = mmpack_search(&ctx, cmd_argc, cmd_argv);
	} else {
		fprintf(stderr, "Invalid command: %s."
		                " Run \"%s --help\" to see Usage\n", cmd, argv[0]);
		rv = -1;
	}

exit:
	mmpack_ctx_deinit(&ctx);

	return (rv == 0) ? EXIT_SUCCESS : EXIT_FAILURE;
}
