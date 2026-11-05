"""Shared six-subject metamodel, transformation and execution configuration."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DATASETS = {
    "BibTeX2DocBook": {
        "dataset_dir":    ROOT / "datasets/models_BibTexML2DocBook",
        "source_mm":      "BibTeX.ecore",
        "target_mms":     ["DocBook.ecore"],
        "atl_name":       "BibTeX2DocBook",
        "atl_file":       "transformations/BibTeX2DocBook.atl",
        "ocl_file":       "OCL_Constraints.txt",
        "source_mm_name": "BibTeX",
        "target_mm_name": "DocBook",
        "trace_mm_name":  "TMM",
        "trace_mm":       "Trace.ecore",
        "java_cp":        str(ROOT / "lib"),
    },
    "CPL2SPL": {
        "dataset_dir":    ROOT / "datasets/models_CPL2SPL",
        "source_mm":      "CPL.ecore",
        "target_mms":     ["SPL.ecore"],
        "atl_name":       "CPL2SPL",
        "atl_file":       "transformations/CPL2SPL.atl",
        "ocl_file":       "OCL_Constraints.txt",
        "source_mm_name": "CPL",
        "target_mm_name": "SPL",
        "trace_mm_name":  "TMM",
        "trace_mm":       "Trace.ecore",
        "java_cp":        str(ROOT / "lib"),
    },
    "UML2ER": {
        "dataset_dir":    ROOT / "datasets/models_UML2ER",
        "source_mm":      "SimpleUml.ecore",
        "target_mms":     ["ER.ecore"],
        "atl_name":       "SimpleUml2ER",
        "atl_file":       "transformations/SimpleUml2ER.atl",
        "ocl_file":       "OCL_Constraints.txt",
        "source_mm_name": "SimpleUML",
        "target_mm_name": "ER",
        "trace_mm_name":  "TMM",
        "trace_mm":       "Trace.ecore",
        "java_cp":        str(ROOT / "lib"),
    },
    "Ecore2Maude": {
        "dataset_dir":    ROOT / "datasets/models_Ecore2Maude",
        "source_mm":      "ecore.ecore",
        "target_mms":     ["Maude.ecore"],
        "atl_name":       "Ecore2Maude",
        "atl_file":       "transformations/Ecore2Maude.atl",
        "ocl_file":       "OCL_Constraints.txt",
        "source_mm_name": "Ecore",
        "target_mm_name": "Maude",
        "trace_mm_name":  "TMM",
        "trace_mm":       "Trace.ecore",
        "java_cp":        str(ROOT / "lib"),
    },
    "Ant2Maven": {
        "dataset_dir":          ROOT / "datasets/models_Ant2Maven",
        "source_mm":            "Ant.ecore",
        "target_mms":           ["MavenMaven.ecore", "MavenProject.ecore"],
        "executor_target_mms":  {
            "OUTMaven":   "MavenMaven.ecore",
            "OUTProject": "MavenProject.ecore",
        },
        "atl_name":             "Ant2Maven",
        "atl_exec_name":        "Ant2Maven_trace",
        "atl_file":             "transformations/Ant2Maven.atl",
        "ocl_file":             "OCL_CONTRACT.txt",
        "source_mm_name":       "Ant",
        "target_mm_name":       "MavenMaven",
        "target_mm_names":      {
            "OUTMaven":   "MavenMaven",
            "OUTProject": "MavenProject",
        },
        "trace_mm_name":        "TMM",
        "trace_mm":             "Trace.ecore",
        "java_cp":              str(ROOT / "lib"),
        "normalize_source_xmi_ids": True,
        "reject_containment_warning": True,
        "reject_source_xsi_types": ["Echo", "Exec"],
        "conditions":           ["sm", "stm", "astm", "astmo"],
        "pilot_min_validity":   0.70,
    },
    "Grafcet2PetriNet": {
        "dataset_dir":    ROOT / "datasets/models_Grafcet2PetriNet",
        "source_mm":      "Grafcet.ecore",
        "target_mms":     ["PetriNet.ecore"],
        "atl_name":       "Grafcet2PetriNet_trace",
        "atl_file":       "transformations/Grafcet2PetriNet_trace.atl",
        "ocl_file":       "OCL_CONTRACT.txt",
        "source_mm_name": "Grafcet",
        "target_mm_name": "PetriNet",
        "trace_mm_name":  "TMM",
        "trace_mm":       "Trace.ecore",
        "java_cp":        str(ROOT / "lib"),
        "conditions":     ["sm", "stm", "astm", "astmo"],
        "pilot_min_validity": 0.10,
    },
}

def get_executor_config(dataset_name: str) -> dict:
    ds = DATASETS[dataset_name]
    dd = ds["dataset_dir"]
    cfg = {
        "source_mm":           str(dd / ds["source_mm"]),
        "target_mm":           str(dd / ds["target_mms"][0]),
        "trace_mm":            str(dd / ds["trace_mm"]),
        "source_mm_name":      ds["source_mm_name"],
        "target_mm_name":      ds["target_mm_name"],
        "trace_mm_name":       ds["trace_mm_name"],
        "transformations_dir": str(dd / "transformations"),
        "atl_name":            ds["atl_name"],
        "atl_exec_name":       ds.get("atl_exec_name", ds["atl_name"]),
        "java_cp":             ds["java_cp"],
        "max_workers":         8,
    }
    if "executor_target_mms" in ds:
        cfg["target_mms"] = {
            name: str(dd / filename)
            for name, filename in ds["executor_target_mms"].items()
        }
        cfg["target_mm_names"] = ds["target_mm_names"]
    for key in (
        "normalize_source_xmi_ids",
        "reject_containment_warning",
        "reject_source_xsi_types",
    ):
        if key in ds:
            cfg[key] = ds[key]
    return cfg


def get_mutant_executor_config(subject):
    """Execution settings for isolated mutant-generation and validation tools."""
    cfg = get_executor_config(subject)
    cfg.setdefault('timeout', 300)
    cfg.setdefault('normalize_source_xmi_ids', False)
    cfg.setdefault('reject_containment_warning', True)
    cfg.setdefault('reject_source_xsi_types', [])
    if subject == 'Ant2Maven':
        directory = DATASETS[subject]['dataset_dir']
        cfg['smoke_input'] = str(directory/'scenarios/scenario_smoke/buildAnt.xmi')
        cfg['smoke_expected_outputs'] = {
            'OUTMaven': str(directory/'scenarios/scenario_smoke/mavenFile.xmi'),
            'OUTProject': str(directory/'scenarios/scenario_smoke/projectFile.xmi'),
        }
    return cfg
