"""Standalone deep-dive program, also invoked by run_research.py."""
import argparse
from pathlib import Path
from research.common import ROOT, read_json, write_json
from research.mean_reversion import analyze_mean_reversion, markdown_report, VERSION


def run(path, news=None):
    path = Path(path)
    if not path.is_absolute():
        path = ROOT / path
    snapshot = read_json(path)
    cfg = snapshot["config"]
    result = analyze_mean_reversion(snapshot, cfg)
    folder = path.parent / VERSION
    write_json(folder / "mean_reversion.json", result)
    (folder / "mean_reversion.md").write_text(markdown_report(result), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", required=True)
    args = parser.parse_args()
    result = run(args.snapshot)
    print("Mean reversion complete:", result["version"], result["mode"])
    print("Output: snapshot folder /", VERSION, "/ mean_reversion.md")
