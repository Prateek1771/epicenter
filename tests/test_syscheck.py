"""syscheck.pick_tier on fake probes (phase 11, LLD §13.2): three tiers for the three demos (small, medium, real-world);
the Docker VM caps the host, every condition must hold."""

import syscheck


def probe(cpus=8, mem=32.0, vm_cpus=None, vm_mem=None, disk=100.0, docker=True, tools=True, internet=True, envs=True,
          cpu_x=1.0) -> dict:  # fmt: skip
    return {
        "docker": "28.0" if docker else None,
        "host_cpus": cpus, "host_mem_gb": mem, "vm_cpus": vm_cpus or cpus, "vm_mem_gb": vm_mem or mem,
        "disk_free_gb": disk,
        "tools": {t: tools for t in ("git", "node", "k6", "uv")},
        "internet": {"huggingface.co": internet, "openrouter.ai": internet},
        "flip_repo": envs, "demo_dir": envs,
        "bench": {"cpu_x_ref": cpu_x},
    }  # fmt: skip


def test_small_machine_runs_the_small_demo():
    assert syscheck.pick_tier(probe(cpus=2, mem=4.0, disk=30, internet=False))[0] == 1


def test_the_docker_vm_wins_over_the_host():
    tier, why = syscheck.pick_tier(probe(cpus=8, mem=16.0, vm_mem=8.0))
    assert tier == 2 and "8.0 GB memory < 16" in why


def test_full_box_with_the_demo_clone_is_real_world_and_tier_only_lowers():
    assert syscheck.pick_tier(probe(cpus=8, mem=32.0, disk=60))[0] == 3
    assert syscheck.pick_tier(probe(cpus=8, mem=32.0, disk=60), explicit=1)[0] == 1
    assert syscheck.pick_tier(probe(cpus=2, mem=4.0, disk=30), explicit=3)[0] == 1  # --tier never raises it


def test_no_docker_is_0_and_a_slow_cpu_drops_a_tier():
    assert syscheck.pick_tier(probe(docker=False)) == (0, "Docker is not running")
    assert syscheck.pick_tier(probe(cpus=8, mem=32.0, disk=60, cpu_x=0.3))[0] == 2


def test_no_otel_demo_clone_caps_at_medium():
    tier, why = syscheck.pick_tier(probe(envs=False))
    assert tier == 2 and "needs demo_dir" in why
