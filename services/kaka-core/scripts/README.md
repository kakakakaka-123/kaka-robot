# kaka-core scripts

These scripts are developer fallback tools. Daily memory and data operations should use
the local web console at `/admin`; scripts stay available for tests, debugging, and
one-off repair work.

The current web console covers conversations, input analysis status, memory candidate
status, candidate merge preview/apply, memory archive/restore/delete, memory search,
and system status. Prefer extending `kaka_core.admin` plus `apps/web-console` for
new user-facing management features.

The candidate merge core logic now lives in `kaka_core.memory.merge`. The
`merge_memory_candidates.py` script is a thin CLI wrapper around that module, and
`/admin` reuses the same functions directly.

Current policy:

- Keep every write operation preview-first unless an explicit `--apply` style flag is used.
- Keep CLI arguments stable because tests and future automation rely on them.
- Keep reusable behavior importable; avoid hiding core logic inside `main()`.
- Prefer adding web-console API behavior under `kaka_core.admin` instead of adding more
  user-facing scripts.

Recommended daily entry points for developers:

```powershell
python scripts/doctor.py
python -m pytest
python services/kaka-core/scripts/analyze_inputs.py --limit 50
python services/kaka-core/scripts/merge_memory_candidates.py --ids 1,2 --apply
python services/kaka-core/scripts/manage_memories.py --ids 1,2 --status archived --apply
```
