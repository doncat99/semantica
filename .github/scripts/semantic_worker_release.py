"""Shared local and CI commands for the immutable semantic worker release."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / ".github/semantic-worker-release.json"


def load_config() -> dict:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def revision_tag(revision: str) -> str:
    config = load_config()
    if len(revision) != 40 or any(char not in "0123456789abcdef" for char in revision):
        raise ValueError("source revision must be a complete lowercase Git commit")
    return config["tagPrefix"] + revision[:12]


def run(command: list[str]) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def build_wheel(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    run(["uv", "build", "--wheel", "--out-dir", str(output)])


def build_bundle(args: argparse.Namespace) -> None:
    config = load_config()
    target = config["targets"].get(args.target)
    if target is None:
        raise ValueError(f"unsupported target: {args.target}")
    wheel = args.wheel.resolve()
    native_inputs = args.native_inputs.resolve()
    models = args.models.resolve()
    python = native_inputs / target["python"]
    run([
        str(python), "-I", "-B", "semantica/bundle.py",
        "--python-root", str(native_inputs / "python"),
        "--wheel", str(wheel),
        "--models-root", str(models),
        "--target", target["runtimeTarget"],
        "--output", str(args.output.resolve()),
        "--source-revision", args.source_revision,
    ])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG, help=argparse.SUPPRESS)
    subparsers = parser.add_subparsers(dest="command", required=True)

    tag = subparsers.add_parser("tag")
    tag.add_argument("source_revision")

    wheel = subparsers.add_parser("wheel")
    wheel.add_argument("--output", type=Path, required=True)

    bundle = subparsers.add_parser("bundle")
    bundle.add_argument("--target", required=True)
    bundle.add_argument("--native-inputs", type=Path, required=True)
    bundle.add_argument("--models", type=Path, required=True)
    bundle.add_argument("--wheel", type=Path, required=True)
    bundle.add_argument("--output", type=Path, required=True)
    bundle.add_argument("--source-revision", required=True)
    args = parser.parse_args()

    if args.command == "tag":
        print(revision_tag(args.source_revision))
    elif args.command == "wheel":
        build_wheel(args.output)
    else:
        build_bundle(args)


if __name__ == "__main__":
    main()
