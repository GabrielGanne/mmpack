/*
 * @mindmaze_header@
 */

#ifndef UTILS_H
#define UTILS_H

#include "mmstring.h"

typedef enum {
	OS_IS_UNKNOWN,
	OS_ID_DEBIAN,
	OS_ID_WINDOWS_10,
} os_id;

os_id get_os_id(void);

#define MMPACK_STATEDIR_RELPATH "/var/lib/mmpack"
#define INSTALLED_INDEX_RELPATH MMPACK_STATEDIR_RELPATH "/installed.yaml"
#define REPO_INDEX_RELPATH      MMPACK_STATEDIR_RELPATH "/binindex.yaml"
#define PKGS_CACHEDIR_RELPATH   "/var/cache/mmpack/pkgs"
#define CFG_RELPATH             "/etc/mmpack-config.yaml"

mmstr* get_default_mmpack_prefix(void);
mmstr* get_config_filename(void);

#define SHA_HEXSTR_LEN (32*2) // string of SHA-256 in hexa (\0 NOT incl.)

int sha_compute(mmstr* hash, const mmstr* filename, const mmstr* parent);


mmstr* mmstr_basename(mmstr* restrict basepath, const mmstr* restrict path);
mmstr* mmstr_dirname(mmstr* restrict dirpath, const mmstr* restrict path);
mmstr* mmstr_join_path(mmstr* restrict dst,
                       const mmstr* restrict p1, const mmstr* restrict p2);

int open_file_in_prefix(const mmstr* prefix, const mmstr* relpath, int oflag);

#endif /* UTILS_H */

