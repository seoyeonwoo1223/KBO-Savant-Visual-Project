"""Execute the research companion in a local kernel with writable task caches."""
import json
import os
from pathlib import Path
import sys


def main():
    root = Path(__file__).resolve().parents[2]
    runtime = root / ".cache/arm_angle/notebook-runtime"
    # Cloud machines can have read-only home directories. Keep this process's
    # Jupyter/font caches in the checkout's already-ignored local cache.
    for name, directory in {
        "JUPYTER_CONFIG_DIR": "jupyter-config", "JUPYTER_DATA_DIR": "jupyter-data",
        "JUPYTER_RUNTIME_DIR": "jupyter-runtime", "IPYTHONDIR": "ipython",
        "MPLCONFIGDIR": "matplotlib", "XDG_CACHE_HOME": "xdg-cache",
    }.items():
        path = runtime / directory
        path.mkdir(parents=True, exist_ok=True)
        os.environ[name] = str(path)
    kernel = runtime / "jupyter-data/kernels/arm_angle_venv"
    kernel.mkdir(parents=True, exist_ok=True)
    (kernel / "kernel.json").write_text(json.dumps({
        "argv": [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"],
        "display_name": "Arm Angle Python 3.12", "language": "python",
    }))
    import nbformat
    from nbclient import NotebookClient
    from nbconvert import HTMLExporter

    path = root / "analysis/arm_angle/arm_angle_analysis.ipynb"
    notebook = nbformat.read(path, as_version=4)
    nbformat.validate(notebook)
    NotebookClient(notebook, timeout=180, kernel_name="arm_angle_venv",
                   resources={"metadata": {"path": str(root)}}).execute()
    nbformat.validate(notebook)
    nbformat.write(notebook, path)
    html, _ = HTMLExporter().from_notebook_node(notebook)
    preview = root / ".cache/arm_angle/notebook.html"
    preview.write_text(html)
    print(f"Executed {sum(cell.cell_type == 'code' for cell in notebook.cells)} code cells; saved notebook and {preview}")


if __name__ == "__main__":
    main()
