"""Shared local and CI commands for the immutable semantic worker release."""
from __future__ import annotations

import argparse
import json
import os
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
    run(["npm", "--prefix", "explorer", "ci", "--no-audit", "--no-fund"])
    run(["npm", "--prefix", "explorer", "run", "build"])
    run(["uv", "build", "--wheel", "--out-dir", str(output)])


def release_matrix(include_gpu: bool) -> dict:
    config = load_config()
    runners = {"darwin-arm64": "macos-14", "linux-x64": "ubuntu-24.04", "win-x64": "windows-2022"}
    return {"include": [
        {"runner": runners[target], "target": target,
         "python": config["targets"][target]["python"], "acceleration": profile}
        for profile, settings in config["accelerationProfiles"].items()
        if profile == "cpu" or include_gpu
        for target in settings["targets"]
    ]}


def build_bundle(args: argparse.Namespace) -> None:
    config = load_config()
    target = config["targets"].get(args.target)
    if target is None:
        raise ValueError(f"unsupported target: {args.target}")
    profile = config["accelerationProfiles"].get(args.acceleration)
    if profile is None or args.target not in profile["targets"]:
        raise ValueError(f"{args.acceleration} is not supported on {args.target}")
    suffix = "" if args.acceleration == "cpu" else f"-{args.acceleration}"
    constraint = ROOT / f".github/requirements/semantic-worker-{args.target}{suffix}.lock"
    if not constraint.is_file():
        raise ValueError(f"missing immutable runtime constraints: {constraint}")
    os.environ["UV_CONSTRAINT"] = str(constraint)
    os.environ["UV_TORCH_BACKEND"] = profile["torchBackend"]
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
        "--acceleration", args.acceleration,
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

    matrix = subparsers.add_parser("matrix")
    matrix.add_argument("--include-gpu", action="store_true")

    bundle = subparsers.add_parser("bundle")
    bundle.add_argument("--target", required=True)
    bundle.add_argument("--acceleration", choices=["cpu", "cuda", "directml"], default="cpu")
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
    elif args.command == "matrix":
        print(json.dumps(release_matrix(args.include_gpu), separators=(",", ":")))
    else:
        build_bundle(args)


if __name__ == "__main__":
    main()
