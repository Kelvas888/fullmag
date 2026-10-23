"""Publish the existing ring example for viewport QA, waiting before Compute."""

from pathlib import Path
import runpy


repository = Path(__file__).resolve().parents[4]
example = repository / "examples/permalloy_layer_cofeb_rings_relax_300nm.py"
namespace = runpy.run_path(str(example))
namespace["study"].wait_for_solve(True)
