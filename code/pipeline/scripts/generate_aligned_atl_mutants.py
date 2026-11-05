from __future__ import annotations

import argparse
import csv
import json
import random
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path.cwd()))

from src.experiment.multi_config_experiment import DATASETS, _dataset_executor_config
from src.executor.transformation_executor import run_transformation


POOLED_SINGLE_COUNTS = {
    "binding_value_change": 25,
    "binding_deletion": 15,
    "out_pattern_element_addition": 12,
    "binding_feature_change": 7,
    "guard_or_filter_mutation": 7,
    "in_pattern_element_addition": 6,
    "out_pattern_element_deletion": 3,
    "binding_addition": 3,
    "out_pattern_element_class_change": 1,
}

SAME_RULE_MULTI_PATTERNS = [
    ("MO_ADD_OUT_BIND", ["out_pattern_element_addition", "binding_addition"]),
    ("MO_DEL_OUT_BIND", ["out_pattern_element_deletion", "binding_deletion"]),
    ("MO_CLASS_BIND", ["out_pattern_element_class_change", "binding_feature_change"]),
    ("MO_VALUE_OUT_ADD", ["binding_value_change", "out_pattern_element_addition"]),
]

CROSS_RULE_MULTI_PATTERNS = [
    ("MO_CROSS_DEL_OUT_DEL", ["binding_deletion", "out_pattern_element_deletion"]),
    ("MO_CROSS_ADD_OUT_ADD", ["binding_addition", "out_pattern_element_addition"]),
    ("MO_CROSS_VALUE_OUT_ADD", ["binding_value_change", "out_pattern_element_addition"]),
    ("MO_CROSS_DEL_VALUE", ["binding_deletion", "binding_value_change"]),
    ("MO_CROSS_VALUE_GUARD", ["binding_value_change", "guard_or_filter_mutation"]),
]


@dataclass
class RuleBlock:
    name: str
    start_line: int
    end_line: int


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def find_matching_brace(s: str, open_idx: int) -> int:
    depth = 0
    for i in range(open_idx, len(s)):
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
            if depth == 0:
                return i
    return -1


def offset_to_line(text: str, offset: int) -> int:
    return text[:offset].count("\n")


def parse_rules(text: str) -> list[RuleBlock]:
    rule_re = re.compile(
        r'(?m)^[ \t]*(?:abstract[ \t]+)?(?:unique[ \t]+)?(?:lazy[ \t]+)?rule[ \t]+([A-Za-z_]\w*)[ \t]*\{'
    )
    rules = []
    for m in rule_re.finditer(text):
        name = m.group(1)
        open_idx = text.find("{", m.start())
        close_idx = find_matching_brace(text, open_idx)
        if close_idx < 0:
            continue
        rules.append(RuleBlock(
            name=name,
            start_line=offset_to_line(text, m.start()),
            end_line=offset_to_line(text, close_idx),
        ))
    return rules


def parse_ecore_classes(path: Path) -> list[str]:
    if not path.exists():
        return []
    text = read_text(path)
    return sorted(set(re.findall(r'eClassifiers[^>]+name="([^"]+)"', text)))


def binding_lines(lines: list[str], rule: RuleBlock) -> list[int]:
    out = []
    for i in range(rule.start_line, rule.end_line + 1):
        line = lines[i]
        if line.strip().startswith("--"):
            continue
        if "<-" in line and re.search(r'\b[A-Za-z_]\w*\s*<-', line):
            out.append(i)
    return out


def out_element_lines(lines: list[str], rule: RuleBlock) -> list[int]:
    out = []
    for i in range(rule.start_line, rule.end_line + 1):
        line = lines[i]
        if line.strip().startswith("--"):
            continue
        if re.search(r'\b[A-Za-z_]\w*\s*:\s*[A-Za-z_]\w*![A-Za-z_]\w*\s*\(', line):
            if not re.search(r'\bfrom\b', line):
                out.append(i)
    return out


def source_pattern_lines(lines: list[str], rule: RuleBlock) -> list[int]:
    out = []
    for i in range(rule.start_line, rule.end_line + 1):
        line = lines[i]
        if line.strip().startswith("--"):
            continue
        if re.search(r'\bfrom\s+[A-Za-z_]\w*\s*:\s*[A-Za-z_]\w*![A-Za-z_]\w*', line):
            out.append(i)
    return out


def split_binding(line: str):
    m = re.match(r'^(\s*)([A-Za-z_]\w*)(\s*<-\s*)(.*?)(,?\s*)(--.*)?$', line)
    if not m:
        return None
    return m


def mutate_rhs(rhs: str, rng: random.Random) -> str:
    rhs = rhs.strip()

    if re.search(r"'[^']*'", rhs):
        return re.sub(r"'[^']*'", "'mutant'", rhs, count=1)

    if rhs in ("true", "false"):
        return "false" if rhs == "true" else "true"

    if re.fullmatch(r"-?\d+", rhs):
        return str(int(rhs) + 1)

    if re.search(r'\b[A-Za-z_]\w*\.[A-Za-z_]\w*\b', rhs):
        refs = re.findall(r'\b([A-Za-z_]\w*)\.([A-Za-z_]\w*)\b', rhs)
        if refs:
            var, feat = refs[0]
            return rhs.replace(f"{var}.{feat}", f"{var}.{feat}", 1) + " + ''"

    return rhs + " + ''"


def comment_line(lines: list[str], idx: int) -> None:
    if not lines[idx].lstrip().startswith("--"):
        leading = re.match(r'^(\s*)', lines[idx]).group(1)
        lines[idx] = leading + "--" + lines[idx][len(leading):]


def find_paren_block_end(lines: list[str], start: int, max_end: int) -> int | None:
    depth = 0
    seen = False
    for i in range(start, max_end + 1):
        for ch in lines[i]:
            if ch == "(":
                depth += 1
                seen = True
            elif ch == ")":
                depth -= 1
                if seen and depth <= 0:
                    return i
    return None


def op_binding_deletion(lines, rule, rng, ctx):
    cands = binding_lines(lines, rule)
    if not cands:
        return None
    idx = rng.choice(cands)
    comment_line(lines, idx)
    return {"line": idx + 1, "detail": "commented binding line"}


def op_binding_value_change(lines, rule, rng, ctx):
    cands = [i for i in binding_lines(lines, rule) if split_binding(lines[i])]
    if not cands:
        return None
    idx = rng.choice(cands)
    m = split_binding(lines[idx])
    old_rhs = m.group(4)
    new_rhs = mutate_rhs(old_rhs, rng)
    if new_rhs == old_rhs:
        return None
    lines[idx] = f"{m.group(1)}{m.group(2)}{m.group(3)}{new_rhs}{m.group(5)} -- Mutation: binding value change"
    return {"line": idx + 1, "detail": f"{old_rhs.strip()} -> {new_rhs.strip()}"}


def op_binding_feature_change(lines, rule, rng, ctx):
    cands = [i for i in binding_lines(lines, rule) if split_binding(lines[i])]
    if len(cands) < 2:
        return None
    idx = rng.choice(cands)
    donor = rng.choice([i for i in cands if i != idx])
    m = split_binding(lines[idx])
    dm = split_binding(lines[donor])
    old = m.group(2)
    new = dm.group(2)
    if old == new:
        return None
    lines[idx] = f"{m.group(1)}{new}{m.group(3)}{m.group(4)}{m.group(5)} -- Mutation: binding feature change"
    return {"line": idx + 1, "detail": f"{old} -> {new}"}


def op_guard_or_filter_mutation(lines, rule, rng, ctx):
    cands = source_pattern_lines(lines, rule)
    if not cands:
        return None
    idx = rng.choice(cands)
    line = lines[idx]

    if "(" in line:
        pos = line.find("(")
        lines[idx] = line[:pos + 1] + "false and " + line[pos + 1:] + " -- Mutation: filter condition change"
    else:
        m = re.search(r'(\bfrom\s+[A-Za-z_]\w*\s*:\s*[A-Za-z_]\w*![A-Za-z_]\w*)', line)
        if not m:
            return None
        end = m.end()
        lines[idx] = line[:end] + "(false)" + line[end:] + " -- Mutation: filter condition change"
    return {"line": idx + 1, "detail": "made source pattern guard unsatisfiable"}


def op_in_pattern_element_addition(lines, rule, rng, ctx):
    cands = source_pattern_lines(lines, rule)
    if not cands:
        return None
    idx = rng.choice(cands)
    line = lines[idx]
    m = re.search(r'\bfrom\s+([A-Za-z_]\w*)\s*:\s*([A-Za-z_]\w*)!([A-Za-z_]\w*)', line)
    if not m:
        return None
    mm, cls = m.group(2), m.group(3)
    indent = re.match(r'^(\s*)', line).group(1)
    insert = f"{indent}, __mutSrc{ctx['mutant_index']} : {mm}!{cls} -- Mutation: in-pattern element addition"
    lines.insert(idx + 1, insert)
    return {"line": idx + 2, "detail": f"added source pattern {mm}!{cls}"}


def op_binding_addition(lines, rule, rng, ctx):
    cands = [i for i in binding_lines(lines, rule) if split_binding(lines[i])]
    if not cands:
        return None
    idx = rng.choice(cands)
    m = split_binding(lines[idx])
    new_line = f"{m.group(1)}{m.group(2)}{m.group(3)}{m.group(4)}{m.group(5)} -- Mutation: binding addition"
    lines.insert(idx + 1, new_line)
    return {"line": idx + 2, "detail": "duplicated existing binding"}


def op_out_pattern_element_addition(lines, rule, rng, ctx):
    cands = out_element_lines(lines, rule)
    if not cands:
        return None
    idx = rng.choice(cands)
    line = lines[idx]
    m = re.search(r'([A-Za-z_]\w*)\s*:\s*([A-Za-z_]\w*)!([A-Za-z_]\w*)\s*\(', line)
    if not m:
        return None
    mm, cls = m.group(2), m.group(3)
    end = find_paren_block_end(lines, idx, rule.end_line)
    if end is None:
        return None
    indent = re.match(r'^(\s*)', lines[idx]).group(1)
    insert = f"{indent}, __mutOut{ctx['mutant_index']} : {mm}!{cls}() -- Mutation: out-pattern element addition"
    lines.insert(end + 1, insert)
    return {"line": end + 2, "detail": f"added output element {mm}!{cls}"}


def op_out_pattern_element_deletion(lines, rule, rng, ctx):
    cands = out_element_lines(lines, rule)
    if not cands:
        return None
    idx = rng.choice(cands)
    end = find_paren_block_end(lines, idx, rule.end_line)
    if end is None:
        return None
    for j in range(idx, end + 1):
        comment_line(lines, j)
    return {"line": idx + 1, "detail": f"commented output element block lines {idx+1}-{end+1}"}


def op_out_pattern_element_class_change(lines, rule, rng, ctx):
    cands = out_element_lines(lines, rule)
    target_classes = ctx.get("target_classes") or []
    if not cands or len(target_classes) < 2:
        return None
    idx = rng.choice(cands)
    line = lines[idx]
    m = re.search(r'([A-Za-z_]\w*)\s*:\s*([A-Za-z_]\w*)!([A-Za-z_]\w*)\s*\(', line)
    if not m:
        return None
    old_cls = m.group(3)
    choices = [c for c in target_classes if c != old_cls]
    if not choices:
        return None
    new_cls = rng.choice(choices)
    lines[idx] = line[:m.start(3)] + new_cls + line[m.end(3):] + " -- Mutation: out-pattern element class change"
    return {"line": idx + 1, "detail": f"{old_cls} -> {new_cls}"}


OPS: dict[str, Callable] = {
    "binding_value_change": op_binding_value_change,
    "binding_deletion": op_binding_deletion,
    "out_pattern_element_addition": op_out_pattern_element_addition,
    "binding_feature_change": op_binding_feature_change,
    "guard_or_filter_mutation": op_guard_or_filter_mutation,
    "in_pattern_element_addition": op_in_pattern_element_addition,
    "out_pattern_element_deletion": op_out_pattern_element_deletion,
    "binding_addition": op_binding_addition,
    "out_pattern_element_class_change": op_out_pattern_element_class_change,
}


def allocate_counts(total: int, weights: dict[str, int]) -> dict[str, int]:
    s = sum(weights.values())
    raw = {k: total * v / s for k, v in weights.items()}
    floor = {k: int(raw[k]) for k in raw}
    rest = total - sum(floor.values())
    rem = sorted(raw, key=lambda k: raw[k] - floor[k], reverse=True)
    for k in rem[:rest]:
        floor[k] += 1
    return floor


def compile_atl(root: Path, atl_path: Path, asm_path: Path) -> dict:
    cmd = ["java", "-cp", "lib/*:lib", "ATLAsmCompilerRunner", str(atl_path), str(asm_path)]
    p = subprocess.run(cmd, cwd=root, text=True, capture_output=True, timeout=120)
    return {
        "returncode": p.returncode,
        "stdout": p.stdout,
        "stderr": p.stderr,
        "asm_exists": asm_path.exists(),
    }


def smoke_execute(dataset: str, mutant_name: str, root: Path, out_base: Path) -> dict:
    ds = DATASETS[dataset]
    cfg = _dataset_executor_config(ds)

    smoke_input = cfg.get("smoke_input")
    if not smoke_input:
        return {"success": True, "skipped": True, "reason": "no smoke_input configured"}

    res = run_transformation(
        smoke_input,
        str(out_base),
        mutant_name,
        cfg,
    )
    return {
        "success": bool(res.get("success")),
        "trace": res.get("trace"),
        "output": res.get("output"),
        "outputs": res.get("outputs"),
        "stderr": (res.get("stderr") or "")[:1000],
        "error": res.get("error"),
    }


def choose_rule_with_capacity(lines, rules, op_name, rng, ctx, exclude=None):
    exclude = set(exclude or [])
    candidates = []
    for r in rules:
        if r.name in exclude:
            continue
        trial = list(lines)
        res = OPS[op_name](trial, r, rng, dict(ctx))
        if res is not None:
            candidates.append(r)
    if not candidates:
        return None
    return rng.choice(candidates)


def generate_one(original_lines, rules, op_names, fault_model, rng, ctx, cross_rule=False):
    lines = list(original_lines)
    injection_points = []
    target_rules = []

    used_rules = set()
    for op_name in op_names:
        if op_name not in OPS:
            return None

        if cross_rule:
            rule = choose_rule_with_capacity(original_lines, rules, op_name, rng, ctx, exclude=used_rules)
        else:
            if target_rules:
                rule = next(r for r in rules if r.name == target_rules[0])
                trial = list(lines)
                if OPS[op_name](trial, rule, rng, dict(ctx)) is None:
                    return None
            else:
                rule = choose_rule_with_capacity(original_lines, rules, op_name, rng, ctx)

        if rule is None:
            return None

        point = OPS[op_name](lines, rule, rng, ctx)
        if point is None:
            return None

        used_rules.add(rule.name)
        if rule.name not in target_rules:
            target_rules.append(rule.name)
        injection_points.append({
            "operator": op_name,
            "rule": rule.name,
            **point,
        })

    return lines, target_rules, injection_points


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--seed", type=int, default=20260529)
    ap.add_argument("--prefix", default=None)
    ap.add_argument("--max-attempts", type=int, default=3000)
    args = ap.parse_args()

    root = Path.cwd()
    rng = random.Random(args.seed)

    if args.dataset not in DATASETS:
        raise SystemExit(f"Unknown dataset: {args.dataset}")

    ds = DATASETS[args.dataset]
    ds_dir = ds["dataset_dir"]
    trans_dir = ds_dir / "transformations"
    atl_name = ds["atl_name"]
    original_atl = trans_dir / f"{atl_name}.atl"

    if not original_atl.exists():
        raise SystemExit(f"Original ATL not found: {original_atl}")

    prefix = args.prefix or f"{atl_name}_FormalMutant"

    original_text = read_text(original_atl)
    original_lines = original_text.splitlines()
    rules = parse_rules(original_text)

    target_mm_paths = []
    if "target_mms" in ds:
        target_mm_paths = [ds_dir / p for p in ds["target_mms"].values()]
    else:
        target_mm_paths = [ds_dir / ds["target_mm"]]

    target_classes = []
    for p in target_mm_paths:
        target_classes.extend(parse_ecore_classes(p))
    target_classes = sorted(set(target_classes))

    single_n = round(args.n * 0.70)
    same_n = round(args.n * 0.10)
    cross_n = args.n - single_n - same_n

    single_targets = allocate_counts(single_n, POOLED_SINGLE_COUNTS)

    plan = []
    for op, count in single_targets.items():
        for _ in range(count):
            plan.append(("single_operator", [op], "single_rule_single_operator", False))

    for i in range(same_n):
        name, ops = SAME_RULE_MULTI_PATTERNS[i % len(SAME_RULE_MULTI_PATTERNS)]
        plan.append(("multi_operator", ops, "same_rule_coupled", False))

    for i in range(cross_n):
        name, ops = CROSS_RULE_MULTI_PATTERNS[i % len(CROSS_RULE_MULTI_PATTERNS)]
        plan.append(("multi_operator", ops, "cross_rule_multi_fault", True))

    rng.shuffle(plan)

    out_manifest = trans_dir / f"{prefix}_manifest.json"
    out_csv = trans_dir / f"{prefix}_manifest.csv"

    accepted = []
    generated = []
    attempts = 0
    idx = 1

    while len(accepted) < args.n and attempts < args.max_attempts and plan:
        attempts += 1
        operator_type, sub_ops, fault_model, cross_rule = plan[0]

        mutant_name = f"{prefix}{idx}"
        ctx = {
            "mutant_index": idx,
            "target_classes": target_classes,
        }

        gen = generate_one(original_lines, rules, sub_ops, fault_model, rng, ctx, cross_rule=cross_rule)
        if gen is None:
            generated.append({
                "mutant": mutant_name,
                "operator_type": operator_type,
                "sub_operators": sub_ops,
                "fault_model": fault_model,
                "lifecycle": "generation_failed",
            })
            idx += 1
            rng.shuffle(plan)
            continue

        mutant_lines, target_rules, injection_points = gen
        atl_path = trans_dir / f"{mutant_name}.atl"
        asm_path = trans_dir / f"{mutant_name}.asm"

        mutant_text = "\n".join(mutant_lines) + "\n"
        write_text(atl_path, mutant_text)

        compile_res = compile_atl(root, atl_path, asm_path)
        lifecycle = "compile_failed"
        smoke_res = {}

        if compile_res["asm_exists"]:
            smoke_out = root / "results" / "mutant_generation_smoke" / args.dataset / f"output_{mutant_name}.xmi"
            smoke_out.parent.mkdir(parents=True, exist_ok=True)
            smoke_res = smoke_execute(args.dataset, mutant_name, root, smoke_out)
            lifecycle = "executable" if smoke_res.get("success") else "stillborn"

        rec = {
            "mutant": mutant_name,
            "dataset": args.dataset,
            "operator_type": operator_type,
            "sub_operators": sub_ops,
            "fault_model": fault_model,
            "target_rule": target_rules[0] if len(target_rules) == 1 else None,
            "target_rules": target_rules,
            "injection_points": injection_points,
            "seed": args.seed,
            "attempt": attempts,
            "atl_path": str(atl_path),
            "asm_path": str(asm_path),
            "compile_returncode": compile_res["returncode"],
            "compile_asm_exists": compile_res["asm_exists"],
            "lifecycle": lifecycle,
            "smoke_success": smoke_res.get("success"),
            "smoke_error": smoke_res.get("error"),
        }

        generated.append(rec)

        if lifecycle == "executable":
            accepted.append(rec)
            plan.pop(0)
            print(f"[OK] {len(accepted):03d}/{args.n} {mutant_name} {fault_model} {sub_ops} rules={target_rules}")
        else:
            print(f"[DROP] {mutant_name} {lifecycle} {fault_model} {sub_ops}")

        idx += 1

    out_manifest.write_text(json.dumps({
        "dataset": args.dataset,
        "original_atl": str(original_atl),
        "prefix": prefix,
        "seed": args.seed,
        "target_n_executable": args.n,
        "target_split": {
            "single_operator": single_n,
            "same_rule_coupled": same_n,
            "cross_rule_multi_fault": cross_n,
        },
        "single_operator_distribution_source": "pooled original four-subject comment audit",
        "single_operator_target_counts": single_targets,
        "accepted_count": len(accepted),
        "attempts": attempts,
        "accepted": accepted,
        "all_generated": generated,
    }, indent=2), encoding="utf-8")

    fieldnames = [
        "mutant", "dataset", "operator_type", "sub_operators", "fault_model",
        "target_rule", "target_rules", "seed", "attempt", "atl_path", "asm_path",
        "compile_returncode", "compile_asm_exists", "lifecycle", "smoke_success", "smoke_error"
    ]
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in accepted:
            row = dict(r)
            row["sub_operators"] = ";".join(row["sub_operators"])
            row["target_rules"] = ";".join(row["target_rules"])
            w.writerow({k: row.get(k) for k in fieldnames})

    print("\n[DONE]")
    print("accepted:", len(accepted))
    print("manifest:", out_manifest)
    print("csv:", out_csv)

    if len(accepted) < args.n:
        raise SystemExit(f"Only generated {len(accepted)} executable mutants out of target {args.n}")


if __name__ == "__main__":
    main()
