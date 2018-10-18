/*
 * @mindmaze_header@
 */
#ifndef SYSDEPS_H
#define SYSDEPS_H

enum {
	DEPS_OK = 0,
	DEPS_MISSING
};

int check_sysdeps_installed(const struct strset* sysdeps);

#endif
