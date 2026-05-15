"""Compile the Vertex AI pipeline to a JSON spec."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from kfp import compiler


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", default="ml_vertex/pipeline.json",
        help="Output path for the compiled pipeline spec",
    )
    parser.add_argument(
        "--image",
        default=os.environ.get("PIPELINE_IMAGE"),
        help="Pipeline image URI (also read from PIPELINE_IMAGE env)",
    )
    args = parser.parse_args()

    if not args.image:
        sys.exit("ERROR: --image or PIPELINE_IMAGE env required")

    # Make image available to the pipeline module at import time
    os.environ["PIPELINE_IMAGE"] = args.image

    # Import AFTER setting env so component decorators pick up the image
    from ml_vertex.pipeline import retrain_pipeline

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    compiler.Compiler().compile(pipeline_func=retrain_pipeline, package_path=str(out))
    print(f"Compiled to: {out}")


if __name__ == "__main__":
    main()
