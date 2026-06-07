#!/usr/bin/env python3
"""Standalone ResearchClaw Stage 1 artifact generator.

This script intentionally does not import ResearchClaw project modules. It can
be copied with the skill folder and run anywhere with Python 3.9+.
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


HIGH_VRAM_THRESHOLD_MB = 8192


GoalGenerator = Callable[[Mapping[str, Any]], str]


@dataclass(frozen=True)
class Stage1Config:
    """Minimal, project-independent config for Stage 1."""

    topic: str
    project_name: str = "ResearchClaw"
    domains: tuple[str, ...] = ()
    quality_threshold: float = 0.8
    daily_paper_count: int = 5
    experiment_mode: str = "sandbox"
    sandbox_python_path: str = "python"
    stage_ref: str = "stage-01"

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "Stage1Config":
        """Create config from either flat or ResearchClaw-like nested data."""
        project = _mapping(data.get("project"))
        research = _mapping(data.get("research"))
        experiment = _mapping(data.get("experiment"))
        sandbox = _mapping(experiment.get("sandbox"))

        topic = _first_nonempty(
            data.get("topic"),
            research.get("topic"),
        )
        if not topic:
            raise ValueError("Stage 1 requires a non-empty topic")

        domains_value = data.get("domains", research.get("domains", ()))
        if isinstance(domains_value, str):
            domains = tuple(
                part.strip() for part in domains_value.split(",") if part.strip()
            )
        elif isinstance(domains_value, Sequence):
            domains = tuple(str(part).strip() for part in domains_value if str(part).strip())
        else:
            domains = ()

        return cls(
            topic=str(topic),
            project_name=str(
                _first_nonempty(data.get("project_name"), project.get("name"))
                or "ResearchClaw"
            ),
            domains=domains,
            quality_threshold=float(
                _first_nonempty(
                    data.get("quality_threshold"),
                    research.get("quality_threshold"),
                )
                or 0.8
            ),
            daily_paper_count=int(
                _first_nonempty(
                    data.get("daily_paper_count"),
                    research.get("daily_paper_count"),
                )
                or 5
            ),
            experiment_mode=str(
                _first_nonempty(data.get("experiment_mode"), experiment.get("mode"))
                or "sandbox"
            ),
            sandbox_python_path=str(
                _first_nonempty(
                    data.get("sandbox_python_path"),
                    sandbox.get("python_path"),
                )
                or "python"
            ),
            stage_ref=str(data.get("stage_ref") or "stage-01"),
        )

    def to_prompt_context(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "project_name": self.project_name,
            "domains": ", ".join(self.domains) if self.domains else "general",
            "quality_threshold": self.quality_threshold,
            "daily_paper_count": self.daily_paper_count,
        }


@dataclass(frozen=True)
class SshConfig:
    """Optional SSH target used for remote NVIDIA hardware detection."""

    host: str
    user: str = ""
    port: int = 22
    key_path: str = ""

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any] | None) -> "SshConfig | None":
        if not data:
            return None
        host = str(data.get("host") or "").strip()
        if not host:
            return None
        return cls(
            host=host,
            user=str(data.get("user") or ""),
            port=int(data.get("port") or 22),
            key_path=str(data.get("key_path") or ""),
        )


@dataclass(frozen=True)
class HardwareProfile:
    has_gpu: bool
    gpu_type: str
    gpu_name: str
    vram_mb: int | None
    tier: str
    warning: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def generate_stage1_artifacts(
    output_dir: str | Path,
    config: Stage1Config | Mapping[str, Any],
    *,
    goal_markdown: str | None = None,
    goal_generator: GoalGenerator | None = None,
    ssh_config: SshConfig | Mapping[str, Any] | None = None,
    ensure_torch: bool = False,
) -> dict[str, Any]:
    """Generate Stage 1 artifacts in *output_dir*.

    Writes:
    - goal.md
    - hardware_profile.json

    Returns a project-independent StageResult-like dictionary with artifact
    names, evidence refs, absolute paths, and the hardware profile.
    """
    cfg = config if isinstance(config, Stage1Config) else Stage1Config.from_mapping(config)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    if goal_markdown is None and goal_generator is not None:
        goal_markdown = goal_generator(cfg.to_prompt_context())
    if goal_markdown is None:
        goal_markdown = render_default_goal(cfg)

    goal_path = out / "goal.md"
    goal_path.write_text(goal_markdown, encoding="utf-8")

    ssh = (
        ssh_config
        if isinstance(ssh_config, SshConfig) or ssh_config is None
        else SshConfig.from_mapping(ssh_config)
    )
    hardware = detect_hardware(ssh_config=ssh)
    torch_available = None
    if ensure_torch and hardware.has_gpu and cfg.experiment_mode == "sandbox":
        torch_available = ensure_torch_available(
            cfg.sandbox_python_path,
            hardware.gpu_type,
        )

    hardware_data = hardware.to_dict()
    if torch_available is not None:
        hardware_data["torch_available"] = torch_available

    hardware_path = out / "hardware_profile.json"
    hardware_path.write_text(
        json.dumps(hardware_data, indent=2),
        encoding="utf-8",
    )

    return {
        "stage": 1,
        "stage_name": "TOPIC_INIT",
        "status": "done",
        "artifacts": ["goal.md", "hardware_profile.json"],
        "evidence_refs": [
            f"{cfg.stage_ref}/goal.md",
            f"{cfg.stage_ref}/hardware_profile.json",
        ],
        "paths": {
            "goal_md": str(goal_path.resolve()),
            "hardware_profile_json": str(hardware_path.resolve()),
        },
        "hardware": hardware_data,
    }


def render_default_goal(config: Stage1Config) -> str:
    """Render the same deterministic fallback goal used by Stage 1."""
    return f"""# Research Goal

## Topic
{config.topic}

## Scope
Investigate the topic with emphasis on reproducible methods and measurable outcomes.

## SMART Goal
- Specific: Build a focused research plan for {config.topic}
- Measurable: Produce literature shortlist, hypotheses, experiment plan, and final paper
- Achievable: Complete through staged pipeline with gate checks
- Relevant: Aligned with project {config.project_name}
- Time-bound: Constrained by pipeline execution budget

## Constraints
- Quality threshold: {config.quality_threshold}
- Daily paper target: {config.daily_paper_count}

## Success Criteria
- At least 2 falsifiable hypotheses
- Executable experiment code and results analysis
- Revised paper passing quality gate

## Generated
{utcnow_iso()}
"""


def detect_hardware(ssh_config: SshConfig | None = None) -> HardwareProfile:
    """Detect NVIDIA CUDA, Apple MPS, or CPU-only hardware."""
    if ssh_config is not None and ssh_config.host:
        remote = _detect_nvidia_remote(ssh_config)
        if remote is not None:
            return remote
        return HardwareProfile(
            has_gpu=False,
            gpu_type="cpu",
            gpu_name=f"Remote ({ssh_config.host}) - no GPU detected",
            vram_mb=None,
            tier="cpu_only",
            warning=(
                f"No GPU detected on remote host {ssh_config.host}. "
                "Only CPU-based experiments are supported."
            ),
        )

    nvidia = _detect_nvidia()
    if nvidia is not None:
        return nvidia

    mps = _detect_mps()
    if mps is not None:
        return mps

    return HardwareProfile(
        has_gpu=False,
        gpu_type="cpu",
        gpu_name="CPU only",
        vram_mb=None,
        tier="cpu_only",
        warning=(
            "No GPU detected. Only CPU-based experiments (NumPy, sklearn) are "
            "supported. For deep learning research ideas, use a machine with a "
            "GPU or a remote GPU server."
        ),
    )


def ensure_torch_available(python_path: str, gpu_type: str) -> bool:
    """Return True if PyTorch is importable, attempting install for GPUs."""
    python = Path(python_path)
    if not python.is_absolute():
        python = Path.cwd() / python

    if _python_can_import_torch(python):
        return True
    if gpu_type == "cpu":
        return False

    try:
        result = subprocess.run(
            [str(python), "-m", "pip", "install", "--quiet", "torch"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False
    return result.returncode == 0 and _python_can_import_torch(python)


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _detect_nvidia() -> HardwareProfile | None:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    return _parse_nvidia_smi(result.stdout, result.returncode)


def _detect_nvidia_remote(ssh_config: SshConfig) -> HardwareProfile | None:
    ssh_cmd = ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=10"]
    if ssh_config.key_path:
        ssh_cmd.extend(["-i", ssh_config.key_path])
    if ssh_config.port and ssh_config.port != 22:
        ssh_cmd.extend(["-p", str(ssh_config.port)])
    target = f"{ssh_config.user}@{ssh_config.host}" if ssh_config.user else ssh_config.host
    ssh_cmd.extend(
        [
            target,
            "nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits",
        ]
    )

    try:
        result = subprocess.run(
            ssh_cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None

    profile = _parse_nvidia_smi(result.stdout, result.returncode)
    if profile is None:
        return None
    return HardwareProfile(
        has_gpu=True,
        gpu_type="cuda",
        gpu_name=f"{profile.gpu_name} (remote: {ssh_config.host})",
        vram_mb=profile.vram_mb,
        tier=profile.tier,
        warning=(
            ""
            if profile.tier == "high"
            else (
                f"Remote GPU ({profile.gpu_name}, {profile.vram_mb} MB VRAM) "
                "has limited memory."
            )
        ),
    )


def _parse_nvidia_smi(stdout: str, returncode: int) -> HardwareProfile | None:
    if returncode != 0:
        return None
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    if not lines:
        return None

    parts = [part.strip() for part in lines[0].split(",")]
    if len(parts) < 2:
        return None
    gpu_name = parts[0]
    try:
        vram_mb = int(float(parts[1]))
    except (ValueError, IndexError):
        vram_mb = 0

    tier = "high" if vram_mb >= HIGH_VRAM_THRESHOLD_MB else "limited"
    warning = ""
    if tier == "limited":
        warning = (
            f"Local GPU ({gpu_name}, {vram_mb} MB VRAM) has limited memory. "
            "Complex deep learning experiments may be slow or run out of "
            "memory. Consider using a remote GPU server for best results."
        )
    return HardwareProfile(
        has_gpu=True,
        gpu_type="cuda",
        gpu_name=gpu_name,
        vram_mb=vram_mb,
        tier=tier,
        warning=warning,
    )


def _detect_mps() -> HardwareProfile | None:
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        return None

    gpu_name = "Apple Silicon GPU"
    try:
        result = subprocess.run(
            ["sysctl", "-n", "machdep.cpu.brand_string"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            gpu_name = result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    return HardwareProfile(
        has_gpu=True,
        gpu_type="mps",
        gpu_name=gpu_name,
        vram_mb=None,
        tier="limited",
        warning=(
            f"macOS GPU detected ({gpu_name}). PyTorch MPS backend is "
            "available but has limited performance compared to NVIDIA CUDA GPUs. "
            "For large-scale experiments, consider using a remote GPU server."
        ),
    )


def _python_can_import_torch(python: Path) -> bool:
    try:
        result = subprocess.run(
            [str(python), "-c", "import torch; print(torch.__version__)"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False
    return result.returncode == 0


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _first_nonempty(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def _load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate standalone ResearchClaw Stage 1 artifacts.",
    )
    parser.add_argument("--output-dir", required=True, help="Directory for goal.md and hardware_profile.json.")
    parser.add_argument("--config", help="Optional JSON config file, flat or ResearchClaw-like.")
    parser.add_argument("--topic", help="Research topic. Overrides --config.")
    parser.add_argument("--project-name", help="Project name. Overrides --config.")
    parser.add_argument("--domains", help="Comma-separated domain list. Overrides --config.")
    parser.add_argument("--quality-threshold", type=float, help="Quality threshold. Overrides --config.")
    parser.add_argument("--daily-paper-count", type=int, help="Daily paper target. Overrides --config.")
    parser.add_argument("--experiment-mode", help="Experiment mode. Overrides --config.")
    parser.add_argument("--sandbox-python-path", help="Python path for optional torch check.")
    parser.add_argument("--stage-ref", default="stage-01", help="Evidence ref prefix.")
    parser.add_argument("--goal-text-file", help="Use this markdown file instead of generating the fallback goal.")
    parser.add_argument("--ensure-torch", action="store_true", help="Check/install torch when a GPU is detected in sandbox mode.")
    parser.add_argument("--ssh-host", help="Remote SSH host for hardware detection.")
    parser.add_argument("--ssh-user", default="", help="Remote SSH username.")
    parser.add_argument("--ssh-port", type=int, default=22, help="Remote SSH port.")
    parser.add_argument("--ssh-key-path", default="", help="SSH private key path.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    raw_config: dict[str, Any] = _load_json(args.config) if args.config else {}

    overrides = {
        "topic": args.topic,
        "project_name": args.project_name,
        "domains": args.domains,
        "quality_threshold": args.quality_threshold,
        "daily_paper_count": args.daily_paper_count,
        "experiment_mode": args.experiment_mode,
        "sandbox_python_path": args.sandbox_python_path,
        "stage_ref": args.stage_ref,
    }
    raw_config.update({k: v for k, v in overrides.items() if v is not None})

    goal_markdown = None
    if args.goal_text_file:
        goal_markdown = Path(args.goal_text_file).read_text(encoding="utf-8")

    ssh = None
    if args.ssh_host:
        ssh = SshConfig(
            host=args.ssh_host,
            user=args.ssh_user,
            port=args.ssh_port,
            key_path=args.ssh_key_path,
        )

    result = generate_stage1_artifacts(
        args.output_dir,
        raw_config,
        goal_markdown=goal_markdown,
        ssh_config=ssh,
        ensure_torch=args.ensure_torch,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
