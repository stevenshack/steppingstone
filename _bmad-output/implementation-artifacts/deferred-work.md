## Deferred from: code review of 1-1-project-scaffold-with-uv (2026-05-12)

- CLI path arguments not validated — Positional args (`macho`, `source_dir`) and `--output-dir` are not checked for existence, readability, or writability. Deferred because `run()` is a stub that raises `NotImplementedError`, so issues won't surface until pipeline implementation.

## Deferred from: code review of 2-1-binary-parser-extracts-sections-and-metadata-from-a-nextstep-mach-o-file (2026-05-12)

- Recursion in `read_method_list` — unlikely in real NeXTSTEP binaries [`lib/binary_reader.py:249-274`]
- No 32/64-bit check — spec says i386 only [`lib/binary_reader.py:1-321`]
- `read_method_list` treats vm==0 as invalid — vm==0 extremely unlikely for method lists [`lib/binary_reader.py:249`]
- Duplicate section names silently overwrite — won't happen in valid Mach-O [`lib/binary_reader.py:90`]
- `type_encoding.py` not imported — module exists per spec, integration is future concern
