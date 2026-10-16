"""Marsh-Echo (九皋) training orchestrator.

Runs the pre-registered hyperparameter grid, the component ablations and the
torch baselines over 10 seeds x 2 data-generating processes.  Every run writes
its test-window tau scores into a per-dgp ``scores_<dgp>.npz`` so the numpy
report script can assemble tables without torch.  Best checkpoints (by
training-window validation loss) are kept for the export step.

Determinism: fixed seeds, CUBLAS workspace config, deterministic algorithms.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.egchpn_torch import baselines  # noqa: E402
from research.egchpn_torch.data import build_batch, n_relations, n_types, simulate  # noqa: E402
from research.egchpn_torch.losses import total_loss  # noqa: E402
from research.egchpn_torch.model import EGCHPNv2  # noqa: E402

ABLATIONS = [
    "none",
    "no_hypergraph",
    "no_gate",
    "gate_deterministic_only",
    "no_dual_tower",
    "no_temporal",
    "no_balance",
    "no_counterfactual",
    "no_evidence_loss",
    "no_lagrangian",
    "no_policy_head",
]

GRID = [
    {"lr": 1e-3, "wd": 0.0, "lam_policy": 0.1},
    {"lr": 3e-3, "wd": 0.0, "lam_policy": 0.1},
    {"lr": 1e-2, "wd": 0.0, "lam_policy": 0.1},
    {"lr": 3e-3, "wd": 1e-4, "lam_policy": 0.1},
    {"lr": 3e-3, "wd": 1e-3, "lam_policy": 0.1},
    {"lr": 3e-3, "wd": 0.0, "lam_policy": 0.05},
    {"lr": 3e-3, "wd": 0.0, "lam_policy": 0.2},
]

MULTIPLIERS = {"balance": 0.1, "counterfactual": 0.5, "evidence": 0.2, "policy": 0.1}


def setup_determinism(seed: int) -> None:
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    os.environ["PYTHONHASHSEED"] = "0"
    torch.manual_seed(seed)
    np.random.seed(seed)
    torch.backends.cudnn.deterministic = True
    torch.use_deterministic_algorithms(True, warn_only=True)


def exact_projection(tau, quality, cost, margin, group_ids, allowed, budget, group_cap):
    """Greedy value-density selection with hard caps (numpy, detached label).

    The deployed plan is produced by this same class of exact projection, so
    the policy head is trained to imitate a feasible optimum instead of
    learning a relaxation that saturates.
    """

    value = quality * np.clip(tau, 0.0, 2.0) - cost / np.clip(margin, 1e-6, None)
    order = np.argsort(-np.where(allowed & (value > 0), value, -np.inf))
    plan = np.zeros(len(tau), dtype=np.float32)
    spend = 0.0
    groups: dict[int, int] = {}
    for index in order:
        index = int(index)
        if not allowed[index] or value[index] <= 0 or spend + cost[index] > budget:
            continue
        if groups.get(int(group_ids[index]), 0) >= group_cap:
            continue
        plan[index] = 1.0
        spend += float(cost[index])
        groups[int(group_ids[index])] = groups.get(int(group_ids[index]), 0) + 1
    return plan


def make_model(ablation: str, input_dim: int, n_rel: int, n_typ: int, hidden: int, layers: int) -> EGCHPNv2:
    # The evidence gate has two independently removable parts: the learned
    # confidence weighting and the non-learnable semantic hard mask.  Dropping
    # only the learned part must not silently keep the safety mask in place.
    return EGCHPNv2(
        input_dim=input_dim,
        hidden_dim=hidden,
        n_layers=layers,
        n_relations=max(n_rel, 1),
        n_types=max(n_typ, 1),
        temporal="no_temporal" not in ablation,
        gate=ablation not in ("no_gate", "gate_deterministic_only"),
        semantic_mask=ablation != "no_gate",
        dual_tower="no_dual_tower" not in ablation,
        policy_head="no_policy_head" not in ablation,
    )


def score_path(out_dir: Path, dgp: str, method: str, seed: int) -> Path:
    return out_dir / dgp / f"scores_{method}_seed{seed}.npz"


def run_one(
    seed: int,
    dgp: str,
    ablation: str,
    cfg: dict,
    device: torch.device,
    out_dir: Path,
    epochs: int,
    hidden: int,
    layers: int,
    baseline: str | None = None,
    n_customers: int = 3000,
    gate_consistency: float = 0.0,
    dr_weight: float = 0.0,
    select_metric: str = "loss",
) -> dict:
    setup_determinism(seed)
    started = time.time()
    pairwise = ablation == "no_hypergraph" or baseline in ("gat_trained", "hgt_lite")
    # A clique expansion multiplies the edge count by the path cardinality, so
    # the pairwise rows use a smaller population; policy values across rows are
    # therefore reported with their population size and compared on the
    # population-normalised metrics only.
    customers = max(600, n_customers // 3) if pairwise else n_customers
    sim = simulate(seed, dgp=dgp, n_customers=customers)
    batch, arrays = build_batch(sim, device, pairwise=pairwise)
    customers = arrays["customer_nodes"]
    days = arrays["days"]
    test_mask = torch.as_tensor(days >= 63, device=device)
    node_mask = torch.zeros(len(sim.spec.node_types), dtype=torch.bool, device=device)
    node_mask[customers] = True
    cust_fit = days < 50
    cust_val = (days >= 50) & (days < 63)
    node_fit = torch.zeros_like(node_mask)
    node_fit[customers[cust_fit]] = True
    node_val = torch.zeros_like(node_mask)
    node_val[customers[cust_val]] = True
    n_nodes = len(sim.spec.node_types)
    customer_index = {int(node): position for position, node in enumerate(customers)}

    def node_vec(values, dtype) -> torch.Tensor:
        tensor = torch.zeros(n_nodes, dtype=dtype, device=device)
        tensor[customers] = torch.as_tensor(np.asarray(values), dtype=dtype, device=device)
        return tensor

    treatment = node_vec(arrays["treatment"], torch.float32)
    outcome = node_vec(arrays["outcome"], torch.float32)
    ite = node_vec(arrays["y1"] - arrays["y0"], torch.float32)
    holdout = node_vec(arrays["in_holdout"], torch.bool)
    rule_node = node_vec(arrays["eligible_rule"], torch.float32)
    quality = node_vec(sim.spec.gate_attrs()[:, 0], torch.float32)
    from research.egchpn_torch.losses import dr_pseudo_outcome

    fit_customers = customers[cust_fit]
    pseudo_customer = dr_pseudo_outcome(
        sim.spec.node_features[customers],
        arrays["outcome"],
        arrays["treatment"],
        arrays["propensity"],
        np.asarray([customer_index[int(node)] for node in fit_customers], dtype=np.int64),
    )
    pseudo = node_vec(pseudo_customer, torch.float32)
    admissible = node_vec(np.asarray([edge.status == "eligible" for edge in sim.spec.hyperedges], dtype=np.float32), torch.float32)

    ablations = set() if ablation == "none" else {ablation}
    if baseline is not None:
        ablations = {"no_evidence_loss"}
    if baseline is None:
        model = make_model(ablation, batch.x.shape[1], int(batch.rel_ids.max().item()) + 1, int(batch.type_ids.max().item()) + 1, hidden, layers).to(device)
    else:
        model = baselines.build(baseline, batch.x.shape[1], int(batch.rel_ids.max().item()) + 1, int(batch.type_ids.max().item()) + 1, hidden, layers).to(device)
    def augment(out: dict) -> dict:
        out["g_node"] = (batch.H @ out["g_raw"]) / batch.H.sum(dim=1).clamp(min=1.0)
        return out

    optimizer = torch.optim.Adam(model.parameters(), lr=cfg["lr"], weight_decay=cfg["wd"])
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    lambdas = {"budget": torch.zeros((), device=device), "group": torch.zeros((), device=device)}
    fit_nodes_np = node_fit.cpu().numpy()
    budget = float(0.2 * int(fit_nodes_np.sum()))
    group_cap = 200
    quality_np = quality.detach().cpu().numpy()
    cost_np = batch.cost.detach().cpu().numpy()
    margin_np = batch.margin.detach().cpu().numpy()
    group_np = batch.group_ids.detach().cpu().numpy()
    plan_np = exact_projection(np.zeros(n_nodes, dtype=np.float32), quality_np, cost_np, margin_np, group_np, fit_nodes_np, budget, group_cap)
    plan_t = torch.as_tensor(plan_np, device=device)
    best_val = float("inf")
    best_state = None
    progress: list[dict] = []
    for epoch in range(epochs):
        model.train()
        optimizer.zero_grad(set_to_none=True)
        temperature = max(0.5, 1.0 * (0.9995 ** epoch))
        out = augment(model(batch, temperature=temperature))
        loss, parts = total_loss(
            out,
            outcome,
            treatment,
            ite,
            holdout,
            rule_node,
            node_fit,
            quality,
            batch.margin,
            batch.cost,
            batch.group_ids,
            budget,
            group_cap,
            MULTIPLIERS,
            lambdas,
            ablations,
            plan_t,
            admissible,
            gate_consistency,
        )
        if dr_weight:
            from research.egchpn_torch.losses import dr_loss

            dr_term = dr_loss(out["tau"], pseudo, node_fit)
            loss = loss + dr_weight * dr_term
            parts["dr"] = float(dr_term.detach())
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
        optimizer.step()
        scheduler.step()
        if epoch % 10 == 9:
            with torch.no_grad():
                for key in lambdas:
                    violation = float(parts.get(f"{key}_violation", 0.0))
                    step = 0.05 * violation - (0.01 * float(lambdas[key]) if violation == 0.0 else 0.0)
                    lambdas[key] = torch.clamp(lambdas[key] + step, min=0.0, max=50.0).detach()
        if epoch % 20 == 0:
            with torch.no_grad():
                plan_np = exact_projection(out["tau"].detach().cpu().numpy(), quality_np, cost_np, margin_np, group_np, fit_nodes_np, budget, group_cap)
                plan_t = torch.as_tensor(plan_np, device=device)
        if epoch % 5 == 0:
            with torch.no_grad():
                val_out = augment(model(batch, temperature=0.2))
                # The Lagrangian penalty grows with the policy head instead of with
                # model quality, so the "quality" criterion evaluates it without that
                # term and keeps the composite only as a logged diagnostic.
                common = (val_out, outcome, treatment, ite, holdout, rule_node, node_val, quality, batch.margin, batch.cost, batch.group_ids, budget, group_cap, MULTIPLIERS, lambdas, ablations, plan_t, admissible, gate_consistency)
                criterion, _ = total_loss(*common, lagrangian=select_metric != "quality")
                val_value = float(criterion)
                if select_metric == "quality":
                    composite, _ = total_loss(*common, lagrangian=True)
                    logged_composite = float(composite)
                else:
                    logged_composite = val_value
            if val_value < best_val:
                best_val = val_value
                best_state = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
            progress.append({"epoch": epoch, "loss": float(loss.detach()), "val": val_value, "val_composite": logged_composite, **{k: v for k, v in parts.items()}})
    if best_state is not None:
        model.load_state_dict(best_state)
    model.eval()
    with torch.no_grad():
        out = augment(model(batch, temperature=0.2))
        tau = out["tau"][customers].cpu().numpy()
        factual = out["y1"][customers].cpu().numpy()
        z = out["z"][customers].cpu().numpy()
    tag = baseline or f"marshecho_{ablation}"
    run_dir = out_dir / dgp
    run_dir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        run_dir / f"scores_{tag}_seed{seed}.npz",
        tau=tau.astype(np.float32),
        factual=factual.astype(np.float32),
        z=z.astype(np.float32),
        test_index=customers[test_mask.cpu().numpy()].astype(np.int64),
    )
    if baseline is None and ablation == "none":
        suffix = f"lr{cfg['lr']}_wd{cfg['wd']}_lp{cfg['lam_policy']}_h{hidden}_L{layers}_e{epochs}"
        torch.save(
            {"state_dict": best_state, "cfg": {**cfg, "hidden": hidden, "layers": layers, "epochs": epochs, "gate_consistency": gate_consistency, "dr_weight": dr_weight}, "model_cfg": model.cfg},
            run_dir / f"checkpoint_seed{seed}_{suffix}.pt",
        )
        torch.save(
            {"state_dict": best_state, "cfg": {**cfg, "hidden": hidden, "layers": layers, "epochs": epochs, "gate_consistency": gate_consistency, "dr_weight": dr_weight}, "model_cfg": model.cfg},
            run_dir / f"checkpoint_seed{seed}.pt",
        )
    progress_tag = f"{tag}_quality" if select_metric == "quality" else tag
    (run_dir / f"progress_{progress_tag}_seed{seed}.jsonl").write_text("\n".join(json.dumps(row) for row in progress[::10]), encoding="utf-8")
    return {
        "seed": seed,
        "dgp": dgp,
        "method": tag,
        "ablation": ablation,
        "baseline": baseline,
        "cfg": cfg,
        "hidden": hidden,
        "layers": layers,
        "epochs": epochs,
        "gate_consistency": gate_consistency,
        "dr_weight": dr_weight,
        "best_val": best_val,
        "select_metric": select_metric,
        "wall_seconds": round(time.time() - started, 2),
        "lambda_budget": float(lambdas["budget"]),
        "lambda_group": float(lambdas["group"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Marsh-Echo training sweep")
    parser.add_argument("--seeds", default="13,29,41,53,67,83,97,101,113,127")
    parser.add_argument("--dgps", default="v1,v2")
    parser.add_argument("--ablations", default="none")
    parser.add_argument("--grid", action="store_true", help="run the pre-registered hyperparameter grid (dgp v1 only)")
    parser.add_argument("--baselines", default="")
    parser.add_argument("--epochs", type=int, default=4000)
    parser.add_argument("--hidden", type=int, default=96)
    parser.add_argument("--layers", type=int, default=3)
    parser.add_argument("--n-customers", type=int, default=3000)
    parser.add_argument("--tag", default="main", help="per-worker manifest suffix")
    parser.add_argument("--skip-ablations", action="store_true", help="run only the torch baselines loop")
    parser.add_argument("--cfg-index", type=int, default=1, help="index into the pre-registered GRID")
    parser.add_argument("--lr", type=float, default=None, help="override GRID lr (final-stage retrain)")
    parser.add_argument("--weight-decay", type=float, default=None)
    parser.add_argument("--lam-policy", type=float, default=None)
    parser.add_argument("--gate-consistency", type=float, default=0.0, help="weight of the inadmissible-path uplift penalty")
    parser.add_argument("--dr-weight", type=float, default=0.0, help="weight of the AIPW pseudo-outcome CATE loss")
    parser.add_argument("--skip-existing", action="store_true", help="resume mode: do not redo runs whose score file already exists")
    parser.add_argument(
        "--select-metric",
        choices=("loss", "quality"),
        default="loss",
        help="checkpoint-selection criterion: 'loss' is the full composite including the "
        "Lagrangian penalty, 'quality' drops that penalty term (it scales with the policy "
        "head, not with model quality)",
    )
    parser.add_argument("--out", default=str(ROOT / "research" / "egchpn_torch" / "runs"))
    args = parser.parse_args()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    base_cfg = dict(GRID[args.cfg_index])
    if args.lr is not None:
        base_cfg["lr"] = args.lr
    if args.weight_decay is not None:
        base_cfg["wd"] = args.weight_decay
    if args.lam_policy is not None:
        base_cfg["lam_policy"] = args.lam_policy
    MULTIPLIERS["policy"] = base_cfg["lam_policy"]
    seeds = [int(item) for item in args.seeds.split(",")]
    dgps = args.dgps.split(",")
    ablations = args.ablations.split(",")
    baselines_list = [item for item in args.baselines.split(",") if item]
    manifest: list[dict] = []
    started_all = time.time()
    if args.grid:
        for cfg_index, cfg in enumerate(GRID):
            for seed in seeds:
                method = "marshecho_none"
                if args.skip_existing and score_path(out_dir, "v1", method, seed).exists():
                    continue
                manifest.append(run_one(seed, "v1", "none", cfg, device, out_dir, args.epochs, args.hidden, args.layers, n_customers=args.n_customers, gate_consistency=args.gate_consistency, dr_weight=args.dr_weight, select_metric=args.select_metric))
                (out_dir / f"manifest_{args.tag}.jsonl").write_text("\n".join(json.dumps(row) for row in manifest), encoding="utf-8")
                print(f"[grid {cfg_index}] seed={seed} wall={manifest[-1]['wall_seconds']}s total={time.time()-started_all:.0f}s", flush=True)
    for dgp in dgps:
        for ablation in ([] if args.skip_ablations else ablations):
            for seed in seeds:
                method = "marshecho_no_gate" if ablation == "no_gate" else f"marshecho_{ablation}"
                if args.skip_existing and score_path(out_dir, dgp, method, seed).exists():
                    continue
                manifest.append(run_one(seed, dgp, ablation, base_cfg, device, out_dir, args.epochs, args.hidden, args.layers, n_customers=args.n_customers, gate_consistency=args.gate_consistency, dr_weight=args.dr_weight, select_metric=args.select_metric))
                (out_dir / f"manifest_{args.tag}.jsonl").write_text("\n".join(json.dumps(row) for row in manifest), encoding="utf-8")
                print(f"[{dgp}/{ablation}] seed={seed} wall={manifest[-1]['wall_seconds']}s total={time.time()-started_all:.0f}s", flush=True)
        for baseline in baselines_list:
            for seed in seeds:
                if args.skip_existing and score_path(out_dir, dgp, baseline, seed).exists():
                    continue
                manifest.append(run_one(seed, dgp, "none", base_cfg, device, out_dir, args.epochs, args.hidden, args.layers, baseline=baseline, n_customers=args.n_customers, gate_consistency=args.gate_consistency, dr_weight=args.dr_weight, select_metric=args.select_metric))
                (out_dir / f"manifest_{args.tag}.jsonl").write_text("\n".join(json.dumps(row) for row in manifest), encoding="utf-8")
                print(f"[{dgp}/{baseline}] seed={seed} wall={manifest[-1]['wall_seconds']}s total={time.time()-started_all:.0f}s", flush=True)
    summary = {"total_wall_seconds": round(time.time() - started_all, 1), "runs": len(manifest), "device": str(device), "torch": torch.__version__, "cuda": torch.cuda.is_available()}
    (out_dir / f"sweep_summary_{args.tag}.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
