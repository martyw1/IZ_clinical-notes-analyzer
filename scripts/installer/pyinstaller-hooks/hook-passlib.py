from PyInstaller.utils.hooks import collect_all, is_module_or_submodule


def _include_runtime_submodule(name: str) -> bool:
    return not is_module_or_submodule(name, "passlib.tests")


datas, binaries, hiddenimports = collect_all(
    "passlib",
    filter_submodules=_include_runtime_submodule,
    exclude_datas=["tests"],
)

hiddenimports += ["configparser"]
