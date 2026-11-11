#!/usr/bin/env bash
# Select the installed runtime; absence is an installation error, never a host fallback.
xiaobei_use_python_runtime() {
  local project_root="$1"
  local runtime="$project_root/tools/python"
  local runtime_bin="$runtime/bin"
  case "$(uname -s)" in MINGW*|MSYS*|CYGWIN*) runtime_bin="$runtime/Scripts" ;; esac
  if [ ! -f "$runtime/pyvenv.cfg" ] || { [ ! -x "$runtime_bin/python3" ] && [ ! -x "$runtime_bin/python3.exe" ]; }; then
    echo "xiaobei Python environment missing; rerun the xiaobei installer: $runtime" >&2
    return 1
  fi
  export PATH="$runtime_bin:$PATH"
  export VIRTUAL_ENV="$runtime"
  export PYTHONNOUSERSITE=1
  export PYTHON="$runtime_bin/python3"
  case "$(uname -s)" in MINGW*|MSYS*|CYGWIN*) export PYTHON="$(cygpath -w "$runtime_bin/python.exe")" ;; esac
  unset PYTHONHOME PYTHONPATH
}
