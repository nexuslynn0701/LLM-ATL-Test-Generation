# src/executor/transformation_executor.py

import os
from pathlib import Path
import subprocess
import logging
import threading
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

# ── 固定配置 ──────────────────────────────────────────────────────────────────

def _project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))


def _default_config() -> dict:
    root    = _project_root()
    dataset = os.path.join(root, "datasets", "models_BibTexML2DocBook")
    return {
        "java_cp":             os.path.join(root, "lib"),
        "source_mm":           os.path.join(dataset, "BibTeX.ecore"),
        "target_mm":           os.path.join(dataset, "DocBook.ecore"),
        "trace_mm":            os.path.join(dataset, "Trace.ecore"),
        "source_mm_name":      "BibTeX",
        "target_mm_name":      "DocBook",
        "trace_mm_name":       "TMM",
        "transformations_dir": os.path.join(dataset, "transformations"),
        "timeout":             300,
        "reject_containment_warning": True,
        "max_workers":         8,    # parallel mutant threads
    }


_XMI_NS = "http://www.omg.org/XMI"
_XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
_XMI_ID = f"{{{_XMI_NS}}}id"
_XSI_TYPE = f"{{{_XSI_NS}}}type"
_ANT2MAVEN_NORMALIZE_LOCK = threading.Lock()


def _failure_result(error: str) -> dict:
    return {
        "success": False,
        "output": None,
        "outputs": {},
        "trace": None,
        "returncode": -1,
        "stdout": "",
        "stderr": error,
        "error": error,
    }


def _resolve_exec_name(transformation_name: str, cfg: dict) -> str:
    if transformation_name == cfg.get("atl_name"):
        return cfg.get("atl_exec_name", transformation_name)
    return transformation_name


def _prepare_source_model(source_model_path: str, cfg: dict):
    """Normalize Ant2Maven XMI ids without modifying the LLM-generated file."""
    if not cfg.get("normalize_source_xmi_ids"):
        return source_model_path, None

    try:
        tree = ET.parse(source_model_path)
    except Exception as exc:
        return None, f"Cannot parse source XMI: {exc}"

    root = tree.getroot()
    rejected = set(cfg.get("reject_source_xsi_types", []))
    found = sorted({
        value.split(":", 1)[1]
        for elem in root.iter()
        for value in [elem.attrib.get(_XSI_TYPE, "")]
        if value.startswith("Ant:") and value.split(":", 1)[1] in rejected
    })
    if found:
        return None, f"Unsupported Ant source xsi:type(s): {found}"

    if Path(source_model_path).parent.name == ".exec_normalized":
        return source_model_path, None

    normalized_dir = Path(source_model_path).parent / ".exec_normalized"
    normalized_path = normalized_dir / Path(source_model_path).name

    ET.register_namespace("xmi", _XMI_NS)
    ET.register_namespace("xsi", _XSI_NS)
    ET.register_namespace("Ant", "Ant")

    used = {
        elem.attrib[_XMI_ID]
        for elem in root.iter()
        if _XMI_ID in elem.attrib
    }

    n = 1
    for elem in root.iter():
        if _XMI_ID in elem.attrib:
            continue
        while f"traceid_{n:04d}" in used:
            n += 1
        elem.set(_XMI_ID, f"traceid_{n:04d}")
        used.add(f"traceid_{n:04d}")
        n += 1

    with _ANT2MAVEN_NORMALIZE_LOCK:
        normalized_dir.mkdir(parents=True, exist_ok=True)
        tmp = normalized_path.with_suffix(
            normalized_path.suffix + f".tmp.{threading.get_ident()}"
        )
        tree.write(tmp, encoding="ASCII", xml_declaration=True)
        os.replace(tmp, normalized_path)

    return str(normalized_path), None


# ── 核心执行函数 ───────────────────────────────────────────────────────────────

def run_transformation(
    source_model_path: str,
    output_model_path: str,
    transformation_name: str = "BibTeX2DocBook",
    config: dict = None,
) -> dict:
    """
    Execute a single ATL transformation.

    Returns
    -------
    {
        "success":     bool,
        "output":      str | None,
        "trace":       str | None,
        "returncode":  int,
        "stdout":      str,
        "stderr":      str,
        "error":       str | None,
    }
    """
    cfg = _default_config()
    if config:
        cfg.update(config)

    source_model_path, source_error = _prepare_source_model(
        source_model_path, cfg
    )
    if source_error:
        return _failure_result(source_error)

    if cfg.get("target_mms"):
        return run_transformation_multi_output(
            source_model_path,
            output_model_path,
            transformation_name,
            cfg,
        )

    exec_name = _resolve_exec_name(transformation_name, cfg)
    asm_path = os.path.join(
        cfg["transformations_dir"],
        f"{exec_name}.asm"
    )

    if not os.path.isfile(asm_path):
        return {
            "success":    False,
            "returncode": -1,
            "stdout":     "",
            "stderr":     "",
            "error":      f"ASM file not found: {asm_path}",
        }

    os.makedirs(os.path.dirname(os.path.abspath(output_model_path)),
                exist_ok=True)

    cp  = os.pathsep.join((str(Path(cfg["java_cp"]) / "*"), str(cfg["java_cp"])))
    cmd = [
        "java", "-cp", cp, "ATLRunner",
        source_model_path,
        cfg["source_mm"],
        cfg["target_mm"],
        cfg["trace_mm"],
        cfg["source_mm_name"],
        cfg["target_mm_name"],
        cfg["trace_mm_name"],
        asm_path,
        output_model_path,
    ]

    logger.debug(f"Running: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            errors="replace",  # Java may emit localized Windows diagnostics.
            timeout=cfg["timeout"],
        )
    except subprocess.TimeoutExpired:
        return {
            "success":    False,
            "returncode": -1,
            "stdout":     "",
            "stderr":     "",
            "error":      f"Timeout after {cfg['timeout']}s",
        }
    except Exception as e:
        return {
            "success":    False,
            "returncode": -1,
            "stdout":     "",
            "stderr":     "",
            "error":      str(e),
        }

    containment_warning = (
        cfg.get("reject_containment_warning")
        and "containment references cannot span across models"
        in f"{result.stdout}\n{result.stderr}"
    )
    success = (
        result.returncode == 0
        and os.path.isfile(output_model_path)
        and not containment_warning
    )
    trace_path = output_model_path.replace(".xmi", "_trace.xmi")

    return {
        "success":    success,
        "output":     output_model_path if success else None,
        "trace":      trace_path if (success and os.path.isfile(trace_path)) else None,
        "returncode": result.returncode,
        "stdout":     result.stdout,
        "stderr":     result.stderr,
        "error":      result.stderr if not success else None,
    }


def _multi_output_paths(output_model_path: str, cfg: dict) -> dict:
    base, ext = os.path.splitext(output_model_path)
    if not ext:
        ext = ".xmi"
    return {
        out_name: f"{base}_{out_name}{ext}"
        for out_name in cfg["target_mms"].keys()
    }


def run_transformation_multi_output(
    source_model_path: str,
    output_model_path: str,
    transformation_name: str,
    config: dict,
) -> dict:
    cfg = _default_config()
    cfg.update(config)

    exec_name = _resolve_exec_name(transformation_name, cfg)
    asm_path = os.path.join(
        cfg["transformations_dir"],
        f"{exec_name}.asm"
    )
    if not os.path.isfile(asm_path):
        return {
            "success": False,
            "output": None,
            "outputs": {},
            "trace": None,
            "returncode": -1,
            "stdout": "",
            "stderr": "",
            "error": f"ASM file not found: {asm_path}",
        }

    output_paths = _multi_output_paths(output_model_path, cfg)
    trace_path = output_model_path.replace(".xmi", "_trace.xmi")
    os.makedirs(os.path.dirname(os.path.abspath(output_model_path)), exist_ok=True)

    cp = os.pathsep.join((str(Path(cfg["java_cp"]) / "*"), str(cfg["java_cp"])))
    cmd = [
        "java", "-cp", cp, "ATLRunnerMulti",
        source_model_path,
        cfg["source_mm"],
        cfg["trace_mm"],
        cfg["source_mm_name"],
        cfg["trace_mm_name"],
        asm_path,
        trace_path,
    ]

    target_mm_names = cfg.get("target_mm_names", {})
    for out_name, mm_path in cfg["target_mms"].items():
        cmd.extend([
            out_name,
            target_mm_names.get(out_name, out_name),
            mm_path,
            output_paths[out_name],
        ])

    logger.debug(f"Running multi-output: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            errors="replace",  # Java may emit localized Windows diagnostics.
            timeout=cfg["timeout"],
        )
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "output": None,
            "outputs": {},
            "trace": None,
            "returncode": -1,
            "stdout": "",
            "stderr": "",
            "error": f"Timeout after {cfg['timeout']}s",
        }
    except Exception as e:
        return {
            "success": False,
            "output": None,
            "outputs": {},
            "trace": None,
            "returncode": -1,
            "stdout": "",
            "stderr": "",
            "error": str(e),
        }

    containment_warning = (
        cfg.get("reject_containment_warning")
        and "containment references cannot span across models"
        in f"{result.stdout}\n{result.stderr}"
    )
    success = (
        result.returncode == 0
        and all(os.path.isfile(path) for path in output_paths.values())
        and not containment_warning
    )

    first_output = next(iter(output_paths.values()), None)
    return {
        "success": success,
        "output": first_output if success else None,
        "outputs": output_paths if success else {},
        "trace": trace_path if (success and os.path.isfile(trace_path)) else None,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "error": result.stderr if not success else None,
    }


# ── Parallel mutant execution ──────────────────────────────────────────────────

def run_mutants_parallel(
    source_model_path: str,
    output_dir: str,
    index_str: str,
    mutant_names: list,
    config: dict = None,
    max_workers: int = None,
) -> dict:
    """
    Run all mutant transformations in parallel using a thread pool.

    Parameters
    ----------
    source_model_path : input XMI source model
    output_dir        : directory for mutant output files
    index_str         : model index string, e.g. "0001"
    mutant_names      : list of mutant transformation names (without .asm)
    config            : optional config override
    max_workers       : thread pool size (default: config["max_workers"])

    Returns
    -------
    { mutant_name: run_transformation() result dict, ... }
    """
    cfg = _default_config()
    if config:
        cfg.update(config)

    workers = max_workers or cfg["max_workers"]

    # Ant normalization must finish before Java readers start. Replacing the
    # same normalized file from every worker races with Windows file handles.
    source_model_path, source_error = _prepare_source_model(source_model_path, cfg)
    if source_error:
        return {name: _failure_result(source_error) for name in mutant_names}

    def _run_one(name: str) -> tuple:
        out = os.path.join(output_dir, f"output_{index_str}_{name}.xmi")
        return name, run_transformation(source_model_path, out, name, cfg)

    results = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_run_one, name): name
                   for name in mutant_names}
        for future in as_completed(futures):
            name, result = future.result()
            results[name] = result

    return results


def run_all_mutants(
    source_model_path: str,
    output_dir: str,
    index_str: str,
    mutant_names: list = None,
    config: dict = None,
) -> dict:
    """
    Run original transformation + all mutants (parallel).

    Returns
    -------
    {
        "original": { run_transformation result },
        "mutants":  { mutant_name: result, ... },
    }
    """
    cfg = _default_config()
    if config:
        cfg.update(config)

    if mutant_names is None:
        mutant_names = _discover_mutants(cfg["transformations_dir"])

    original_output = os.path.join(
        output_dir, f"output_{index_str}_original.xmi")
    original = run_transformation(
        source_model_path,
        original_output,
        cfg.get("atl_name", "BibTeX2DocBook"),
        cfg,
    )
    logger.info(f"[{index_str}] original: success={original['success']}")

    mutants = run_mutants_parallel(
        source_model_path = source_model_path,
        output_dir        = output_dir,
        index_str         = index_str,
        mutant_names      = mutant_names,
        config            = cfg,
    )

    return {"original": original, "mutants": mutants}


def _discover_mutants(transformations_dir: str) -> list:
    """Scan transformations/ and return all Mutant .asm names (no extension)."""
    names = []
    for f in sorted(os.listdir(transformations_dir)):
        if f.endswith(".asm") and "Mutant" in f and "no_trace" not in f:
            names.append(f.replace(".asm", ""))
    return names


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    import time
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )

    root    = _project_root()
    dataset = os.path.join(root, "datasets", "models_BibTexML2DocBook")
    source  = os.path.join(dataset, "scenarios", "scenario1",
                           "AutomaticModel_BibTex1.xmi")
    out_dir = os.path.join(root, "results", "executor_test")
    os.makedirs(out_dir, exist_ok=True)

    cfg          = _default_config()
    mutant_names = _discover_mutants(cfg["transformations_dir"])

    print(f"\n[TEST] Parallel mutant execution ({len(mutant_names)} mutants)")
    print(f"       max_workers = {cfg['max_workers']}")

    t0      = time.time()
    results = run_mutants_parallel(
        source_model_path = source,
        output_dir        = out_dir,
        index_str         = "test",
        mutant_names      = mutant_names,
    )
    elapsed = time.time() - t0

    ok   = sum(1 for r in results.values() if r["success"])
    fail = len(results) - ok
    print(f"\n  Completed in {elapsed:.1f}s")
    print(f"  OK={ok}  FAILED={fail}  total={len(results)}")


if __name__ == "__main__":
    main()
