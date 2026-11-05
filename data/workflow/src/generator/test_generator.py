import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from src.prompt.prompt_builder import (
    build_prompt,
    get_metamodel_paths,
    get_example_paths,
    build_saturation_aware_hint,
)
from src.llm.llm_client import read_api_key, call_llm
from src.llm import call_logger


# ── BibTeX2DocBook-specific constraints ───────────────────────────────────────

_BIBTEX_SAFETY_NOTE = """
CRITICAL CONSTRAINT:
  ALL Article entries MUST have BOTH title AND journal attributes.
  Omitting either causes a transformation crash when non-Article entries exist.

Other constraints:
  - Non-Article TitledEntry types (Book, Manual, InBook, InCollection,
    Proceedings, InProceedings, TechReport, Unpublished, MasterThesis,
    PhDThesis) must have a title attribute.
  - Book / InBook / InCollection require publisher.
  - InProceedings / InCollection require booktitle.
  - Unpublished requires note.
  - Misc and Booklet are safe without title.
  - Every entry must have an id attribute.
"""

_BIBTEX_RULE_CONDITIONS = {
    "Main":
        "always triggered once — include a BibTeXFile root element",
    "Author":
        "triggered for each <authors author='...'> child element. "
        "Example:\n"
        "  <entries xsi:type='BibTeX:Article' id='a1' "
        "title='T' journal='J'>\n"
        "    <authors author='Alice Smith'/>\n"
        "  </entries>",
    "UntitledEntry":
        "triggered by Misc or Booklet entries. "
        "Example: <entries xsi:type='BibTeX:Misc' id='m1'/>",
    "TitledEntry_Title_NoArticle":
        "triggered by Book, Manual, InBook, Proceedings, TechReport, "
        "Unpublished, MasterThesis, PhDThesis WITH title. "
        "ALL Articles in the same model must have both title AND journal. "
        "Example:\n"
        "  <entries xsi:type='BibTeX:Article' id='a1' "
        "title='Paper' journal='IEEE TSE' year='2020'/>\n"
        "  <entries xsi:type='BibTeX:Book' id='b1' "
        "title='My Book' publisher='Springer' year='2019'/>",
    "TitledEntry_NoTitle_NoArticle":
        "SKIP — title is mandatory (lowerBound=1) for all TitledEntry subtypes",
    "Article_Title_Journal":
        "triggered by Article WITH both title AND journal. "
        "Example:\n"
        "  <entries xsi:type='BibTeX:Article' id='a1' "
        "title='My Paper' journal='IEEE TSE' year='2020'/>",
    "Article_NoTitle_Journal":
        "SKIP — ATL limitation: crashes when non-Article TitledEntry present",
    "Article_Title_NoJournal":
        "SKIP — ATL limitation: crashes when non-Article TitledEntry present",
    "Article_NoTitle_NoJournal":
        "SKIP — ATL limitation: crashes when non-Article TitledEntry present",
}

_BIBTEX_SKIP_RULES = {
    "TitledEntry_NoTitle_NoArticle",
    "Article_NoTitle_Journal",
    "Article_Title_NoJournal",
    "Article_NoTitle_NoJournal",
}

# ── Generic safety note ───────────────────────────────────────────────────────

_GENERIC_SAFETY_NOTE = """
Ensure the generated model:
  - Is well-formed XML conforming to the source metamodel.
  - Contains valid references between elements.
  - Has all mandatory attributes set (check lowerBound=1 in the metamodel).
  - Every element must have an id or name attribute where required.
"""

# ── FROZEN safety notes (2026-05-25) ────────────────────────────────────────
# 
_ANT2MAVEN_SAFETY_NOTE = """
Ant2Maven source XMI safety rules. Follow these exactly.

You are generating an Ant source model only. Do not generate Maven output models.

HARD EXECUTABILITY GATE. Violating any item makes the generated model invalid:
- Project.default is the only allowed reference-valued attribute. It MUST equal
  the xmi:id of one contained <targets> element in the same model.
- Never use depends="..." attributes and never create nested <depends> elements.
- Never generate <tasks xsi:type="Ant:Echo"> or <tasks xsi:type="Ant:Exec">.
- Never generate <tasks xsi:type="Ant:NewTask"> and never use taskName references.
- A standalone contained <taskdef .../> element is allowed, but do not reference
  it from any task.
- Keep all generated structures contained. Do not add href, refid, classpathref,
  path references, or external ID references.

The provided minimal_project.xmi is a syntax exemplar only. It demonstrates
the minimum valid Ant XMI serialization structure, including containment
element names and the Project.default reference. Do not copy its content or
task composition. Generate a new source model using independently selected
valid Ant elements and values.

Use the Ant.ecore XML element names exactly:
- Root Project element: <Ant:Project ...>
- Project contains targets using <targets>, not <target>.
- Target contains tasks using <tasks>, not <task>.
- Project.default is an EReference to a contained Target, not a plain string attribute.
  Therefore every default target must have xmi:id, and Project.default must equal that id.
  Correct:
    <Ant:Project ... default="compile">
      <targets xmi:id="compile" name="compile"> ... </targets>
    </Ant:Project>
- Never set Project.default to an id that is not defined.
- Never invent references such as compileTarget, mytask, //@path.0 unless the referenced object exists.
- If you use any reference-valued attribute, the target object must have a matching xmi:id in the same model.
- Keep the model simple and executable. Prefer one Project with one or two contained targets.

Important typing rule:
- Ant Project.default must reference an Ant Target object.
- Do not confuse Ant Target with Maven Goal. The source model must never contain Maven classes.
- Do not use <Target> as a project child; use <targets>.
- Do not use <Goal> in the Ant source model.

Minimal valid pattern:
<?xml version="1.0" encoding="ASCII"?>
<Ant:Project
    xmi:version="2.0"
    xmlns:xmi="http://www.omg.org/XMI"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xmlns:Ant="Ant"
    name="MyProject"
    default="compile"
    basedir=".">
  <targets xmi:id="compile" name="compile">
    <tasks xsi:type="Ant:Javac" srcdir="src" destdir="bin"/>
    <tasks xsi:type="Ant:Jar" jarfile="dist/app.jar"/>
  </targets>
</Ant:Project>

For this experiment, avoid fragile cross references.
Allowed reference:
- Project.default -> one contained <targets xmi:id="...">.

Forbidden references in generated Ant source models:
- Do not use Target.depends.
- Do not use taskName references.
- Do not use path references, pathElement references, fileset references, classpathref, refid, or any external ID reference.
- Do not use attributes whose value names another object, except Project.default.
- Do not use unsupported task types such as <tasks xsi:type="Ant:Echo"> or <tasks xsi:type="Ant:Exec">.
  Ant2Maven.atl has no matched rules for Echo or Exec, so these source objects cannot be transformed safely.
- Use only Ant source types handled by matched rules in Ant2Maven.atl.
- Do not invent ids such as mytask, compileTarget, init, main unless the same xmi:id is defined in the model.

To increase coverage safely, add only contained elements:
- Additional <targets xmi:id="test" name="test"> with no depends.
- Tasks as contained <tasks xsi:type="Ant:Javac" srcdir="src" destdir="bin"/>.
- Tasks as contained <tasks xsi:type="Ant:Jar" jarfile="dist/app.jar"/>.
- Tasks as contained <tasks xsi:type="Ant:Mkdir" dir="build"/>.
- Tasks as contained <tasks xsi:type="Ant:Delete" dir="build"/>.
Avoid classpaths, path, fileset, filterset, taskdef, and nested references until the model is executable.
"""



# ── BibTeX2DocBook-specific constraints (added 2026-05-28) ───────────────────
_BIBTEX_SAFETY_NOTE = """
CRITICAL XMI FORMAT for BibTeX2DocBook source models:

1. Root element MUST be <BibTeX:BibTeXFile> directly — NOT wrapped in <xmi:XMI>:
   CORRECT:
     <BibTeX:BibTeXFile xmi:version="2.0"
         xmlns:xmi="http://www.omg.org/XMI"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xmlns:BibTeX="http://BibTeX/1.0">
   INCORRECT:
     <xmi:XMI xmi:version="2.0" ...>
       <BibTeX:BibTeXFile>

2. The xmlns:xsi namespace MUST be declared on the root element.
   xsi:type is used on <entries> elements and requires this declaration.

3. All <entries> elements use xsi:type to specify the concrete type:
   <entries xsi:type="BibTeX:Article" id="..." title="..." year="..." journal="...">

4. Authors are nested elements, not attributes:
   <authors author="John Doe"/>
"""
# _CPL_SAFETY_NOTE and _UML2ER_SAFETY_NOTE are frozen after 2026-05-25.
# CPL2SPL and UML2ER rerun3 data was collected with these exact strings.
# Future additions (e.g., Ecore2Maude) MUST add new constants only.
# DO NOT modify _CPL_SAFETY_NOTE or _UML2ER_SAFETY_NOTE after this date.
# ─────────────────────────────────────────────────────────────────────────────
# ── UML2ER-specific constraints ──────────────────────────────────────────────
_UML2ER_SAFETY_NOTE = """
IMPORTANT CONSTRAINTS for SimpleUML source models:
0. Root element MUST use the SimpleUml namespace prefix:
   CORRECT:   <SimpleUml:Package xmi:version="2.0" xmlns:xmi="http://www.omg.org/XMI" xmlns:SimpleUml="http://SimpleUML" name="...">
   INCORRECT: <Package xmlns:xmi=...> or <Package name="...">
1. complexType is a REFERENCE attribute, not a nested element:
   CORRECT:   <ownedProperty name="author" complexType="//@ownedElements.1"/>
   INCORRECT: <ownedProperty name="author"><complexType name="Author"/></ownedProperty>
2. superClasses is a REFERENCE list:
   CORRECT:   <ownedElements name="Student" superClasses="//@ownedElements.0 //@ownedElements.1"/>
   INCORRECT: <ownedElements name="Student"><superClasses name="Person"/></ownedElements>
3. All ownedElements are top-level children of the Package root element.
4. Use //@ownedElements.N (0-based index) for all cross-references.
"""

# ── CPL2SPL-specific constraints ─────────────────────────────────────────────

_CPL_SAFETY_NOTE = """
CRITICAL CONSTRAINTS for CPL2SPL models:

1. ONLY these types can appear as top-level <elements> entries:
   CPL, SubCall, Location, Redirect, Reject, Proxy,
   AddressSwitch, StringSwitch, LanguageSwitch, TimeSwitch, PrioritySwitch
   DO NOT use Failure, Busy, Default, NoAnswer, Redirection, NotPresent,
   Otherwise, SubAction, Outgoing, Incoming as top-level elements.
   These types ONLY appear as child elements inside Proxy or Switch nodes.

2. SubCall.ref is a plain STRING, NOT an object reference:
   CORRECT: <elements xsi:type="CPL:SubCall" ref="anyStringValue"/>
   WRONG:   <elements xsi:type="CPL:SubCall" ref="sub1"/>

3. Child elements of Proxy use containment, not xsi:type:
   <elements xsi:type="CPL:Proxy" recurse="yes" ordering="parallel">
     <busy/>
     <noAnswer/>
     <redirection/>
     <failure/>
     <default contents="//@elements.2"/>
   </elements>

4. contents references use XMI path format (0-based index):
   contents="//@elements.2" means the 3rd <elements> entry.

5. All string attributes can be arbitrary values (e.g. "abc", "xyz").

CORRECT minimal example:
  <elements xsi:type="CPL:CPL"/>
  <elements xsi:type="CPL:SubCall" ref="someAction"/>
  <elements xsi:type="CPL:Proxy" recurse="yes" ordering="parallel">
    <busy/>
    <default contents="//@elements.1"/>
  </elements>
  <elements xsi:type="CPL:Reject" status="486" reason="Busy"/>
"""

# ── Ecore2Maude-specific constraints ─────────────────────────────────────────

_ECORE_SAFETY_NOTE = """
CRITICAL CONSTRAINTS for Ecore2Maude models (source is an Ecore metamodel):

1. ALL cross-references MUST use index-based XMI path format:
   eType="//@eClassifiers.2"        (3rd classifier, 0-based)
   eSuperTypes="//@eClassifiers.0 //@eClassifiers.1"
   DO NOT use name-based refs like eType="#//Address" — these cause crashes.

2. EPackage namespace: use xmlns:ecore="http://ecore" (NOT the standard EMF URI)
   <ecore:EPackage xmlns:ecore="http://ecore" name="myPkg" nsURI="myURI" nsPrefix="my">

3. EDataType references for primitive types use the full EMF URI:
   eType="ecore:EDataType http://www.eclipse.org/emf/2002/Ecore#//EString"
   eType="ecore:EDataType http://www.eclipse.org/emf/2002/Ecore#//EInt"

4. Attribute values can be arbitrary strings. Class names can be random.

5. CORRECT cross-reference example (3 classes, class 1 references class 0):
   <eClassifiers xsi:type="ecore:EClass" name="ClassA"/>
   <eClassifiers xsi:type="ecore:EClass" name="ClassB"
       eSuperTypes="//@eClassifiers.0">
     <eStructuralFeatures xsi:type="ecore:EReference" name="ref"
         eType="//@eClassifiers.0" containment="true"/>
   </eClassifiers>
"""


# ── Rule name extraction ──────────────────────────────────────────────────────

def extract_rule_names(atl_path: str) -> list:
    """
    Extract all rule names from an ATL file.
    Handles: rule X, abstract rule X, lazy rule X, unique lazy rule X.
    Excludes entrypoint rules.
    """
    _RULE_RE  = re.compile(
        r'^(?:abstract\s+)?(?:unique\s+)?(?:lazy\s+)?rule\s+\w'
    )
    _STRIP_RE = re.compile(
        r'^(?:abstract\s+)?(?:unique\s+)?(?:lazy\s+)?rule\s+'
    )
    rules = []
    try:
        with open(atl_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                stripped      = line.strip()
                is_entrypoint = stripped.startswith("entrypoint rule ")
                is_rule       = bool(_RULE_RE.match(stripped)) and not is_entrypoint
                if is_rule:
                    working = _STRIP_RE.sub("", stripped)
                    name    = working.split("{")[0].strip()
                    if " extends " in name:
                        name = name.split(" extends ")[0].strip()
                    if "(" in name:
                        name = name.split("(")[0].strip()
                    if name:
                        rules.append(name)
    except Exception:
        pass
    return rules


# ─────────────────────────────────────────────────────────────────────────────
# Generation mode system  (mixed_mode_feedback=True)
# ─────────────────────────────────────────────────────────────────────────────

_PHASE1_PATTERN = [
    "moderate", "moderate", "balanced", "moderate", "simple",
    "moderate", "balanced", "moderate", "simple",  "moderate",
]   # per 10: M=6, B=2, S=2

_PHASE2_PATTERN = [
    "balanced", "moderate", "simple",  "balanced", "moderate",
    "balanced", "simple",   "moderate","balanced", "simple",
]   # per 10: B=4, M=3, S=3

_PHASE3_PATTERN = [
    "balanced", "simple",   "balanced", "moderate", "simple",
    "balanced", "simple",   "balanced", "moderate", "simple",
]   # per 10: B=4, M=2, S=4

_VERIFIED_COUNTS_100 = {"balanced": 36, "moderate": 33, "simple": 31}


def _verify_mode_counts_range(start_pos: int, n: int) -> dict:
    """Compute exact mode counts for positions [start_pos, start_pos+n)."""
    counts: dict = {"balanced": 0, "moderate": 0, "simple": 0}
    for pos in range(start_pos, start_pos + n):
        if 1 <= pos <= 100:
            counts[_choose_mode_for_position(pos)] += 1
    return counts


def _choose_mode_for_position(global_position: int) -> str:
    """Return mode for absolute 1-based position. Valid range: [1, 100]."""
    if not (1 <= global_position <= 100):
        raise ValueError(
            f"global_position={global_position} is outside [1, 100]. "
            "Mixed-mode schedule is calibrated for 100-model runs."
        )
    if global_position <= 20:
        return _PHASE1_PATTERN[(global_position - 1) % len(_PHASE1_PATTERN)]
    elif global_position <= 70:
        return _PHASE2_PATTERN[(global_position - 21) % len(_PHASE2_PATTERN)]
    else:
        return _PHASE3_PATTERN[(global_position - 71) % len(_PHASE3_PATTERN)]


def _mode_phase_label(global_position: int) -> str:
    if global_position <= 20:   return "phase1"
    elif global_position <= 70: return "phase2"
    else:                        return "phase3"


_MODE_HINT_BALANCED = """\

--- GENERATION MODE: BALANCED-COMPACT ---
Generate a compact but non-trivial valid model.
Prefer triggering one uncovered rule or a very small subset of related rules.
Do not try to maximize total rule coverage in this single model.
Avoid unnecessary elements, but do not use the simplest repeated pattern.
Keep the model structurally different from previous models.
It is acceptable that some models expose faults and some do not.
--- END MODE ---
"""

_MODE_HINT_MODERATE = """\

--- GENERATION MODE: MODERATE-COVERAGE ---
Generate a valid model with moderate structural richness.
Try to trigger one or two uncovered rules, or a small set of related rules.
The model may include several elements, but avoid broad all-in-one coverage.
Do not generate a maximal model.
Keep this model different from previous ones in element combination and structure.
This mode is intended to maintain useful fault detection ability.
--- END MODE ---
"""

_MODE_HINT_SIMPLE = """\

--- GENERATION MODE: SIMPLE-DIVERSE ---
Generate a small valid model with a clearly different structural pattern
from previous models.
Use a minimal or near-minimal structure, but do not repeat previously used shapes.
Try to trigger only a limited subset of rules.
Prefer uncommon combinations of element types, containment structure, or references.
This model does not need to maximize fault exposure.
--- END MODE ---
"""

_DIVERSITY_BLOCK = """\

--- DIVERSITY REQUIREMENT ---
Do not generate a model with the same structural pattern as previous models.
Vary the number of elements, the element types used, the containment hierarchy,
and the reference structure.
Avoid repeating the easiest previously used pattern.
--- END DIVERSITY REQUIREMENT ---
"""

_MODE_HINTS = {
    "balanced": _MODE_HINT_BALANCED,
    "moderate": _MODE_HINT_MODERATE,
    "simple":   _MODE_HINT_SIMPLE,
}


def _build_mode_hint(mode: str) -> str:
    return _MODE_HINTS.get(mode, "") + _DIVERSITY_BLOCK


# ── Coverage-guided hints ─────────────────────────────────────────────────────

def _build_coverage_hint(covered_rules, all_rules, rule_conditions,
                         skip_rules, safety_note):
    """Detection-oriented. DO NOT MODIFY — backward-compatible."""
    covered_set = set(covered_rules)
    uncovered   = [r for r in all_rules
                   if r not in covered_set and r not in skip_rules]
    if not uncovered:
        return (
            "\nAll safe ATL rules have been covered. "
            "Generate a structurally different model to improve "
            "mutation kill rate." + safety_note
        )
    lines = [
        "\n--- COVERAGE-GUIDED GENERATION (ATL-verified) ---",
        f"Already covered: "
        f"{', '.join(sorted(covered_set)) if covered_set else 'none yet'}",
        "",
        "Design your model to trigger at least one of these UNCOVERED rules:",
    ]
    for rule in uncovered:
        condition = rule_conditions.get(
            rule,
            f"trigger the '{rule}' rule by creating appropriate "
            f"source model elements (see ATL transformation code above)"
        )
        lines.append(f"  - {rule}:\n      {condition}")
    lines += ["", "--- END COVERAGE GUIDANCE ---", safety_note]
    return "\n".join(lines)


def _build_coverage_hint_fl_aware(covered_rules, all_rules, rule_conditions,
                                  skip_rules, safety_note):
    """Strict FL-aware."""
    covered_set = set(covered_rules)
    uncovered   = [r for r in all_rules
                   if r not in covered_set and r not in skip_rules]
    if not uncovered:
        return (
            "\nAll safe ATL rules have been covered.\n"
            "Do NOT optimize for mutation kill rate.\n"
            "Generate a SMALL, structurally different VALID model.\n"
            "Prefer triggering only a SUBSET of transformation rules.\n"
            "It is acceptable that this model does NOT expose faults.\n"
            "The goal is execution diversity, not fault detection.\n"
            + safety_note
        )
    lines = [
        "\n--- FL-AWARE GENERATION (ATL-verified) ---",
        f"Already covered: "
        f"{', '.join(sorted(covered_set)) if covered_set else 'none yet'}",
        "",
        "Generate a SMALL valid model targeting ONE of these uncovered rules.",
        "Do NOT try to cover multiple uncovered rules at once.",
        "Use as few elements as possible.",
        "It is acceptable that this model does NOT expose faults.",
        "Preserve diversity: avoid models similar to previous ones.",
        "",
        "Target uncovered rules (pick ONE):",
    ]
    for rule in uncovered:
        condition = rule_conditions.get(
            rule,
            f"trigger the '{rule}' rule by creating appropriate "
            f"source model elements (see ATL transformation code above)"
        )
        lines.append(f"  - {rule}:\n      {condition}")
    lines += ["", "--- END FL-AWARE GUIDANCE ---", safety_note]
    return "\n".join(lines)


def _build_coverage_hint_mixed(covered_rules, all_rules, rule_conditions,
                               skip_rules, safety_note):
    """Neutral coverage context for mixed-mode."""
    covered_set = set(covered_rules)
    uncovered   = [r for r in all_rules
                   if r not in covered_set and r not in skip_rules]
    if not uncovered:
        return (
            "\nAll safe ATL rules have been covered.\n"
            "Follow the generation mode guidance above.\n"
            + safety_note
        )
    lines = [
        "\n--- COVERAGE CONTEXT (ATL-verified) ---",
        f"Already covered: "
        f"{', '.join(sorted(covered_set)) if covered_set else 'none yet'}",
        "",
        "Uncovered rules (use mode guidance above to decide how many to target):",
    ]
    for rule in uncovered:
        condition = rule_conditions.get(
            rule,
            f"trigger the '{rule}' rule by creating appropriate "
            f"source model elements (see ATL transformation code above)"
        )
        lines.append(f"  - {rule}:\n      {condition}")
    lines += ["", "--- END COVERAGE CONTEXT ---", safety_note]
    return "\n".join(lines)


# ── XML extraction ────────────────────────────────────────────────────────────

def extract_xml_block(text: str, tag: str) -> str:
    pattern = rf"<{tag}>(.*?)</{tag}>"
    match   = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None


def save_model(content: str, output_path: str) -> None:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)


# ── ATL verification with adaptive repair ────────────────────────────────────

def _verify_and_update_coverage(
    source_path, transform_dir, index_str, atl_path,
    transformation_name, covered_rules, all_rules,
    executor_config=None, api_key=None, safety_note="",
    metamodel_paths=None, enable_repair=True, provider=None,
) -> tuple:
    """Execute ATL and update covered_rules in-place.
    Returns (success, newly_covered, coverage_ratio, repaired, fired_rules).
    fired_rules is a set[str] — used by SAT_AWARE profile tracking.
    provider: 修复调用应与生成调用使用同一 LLM，由调用方传入。
    """
    from src.executor.transformation_executor import run_transformation
    from src.analyzer.coverage_analyzer import compute_rule_coverage

    os.makedirs(transform_dir, exist_ok=True)
    output_path = os.path.join(transform_dir, f"output_{index_str}.xmi")

    exec_result = run_transformation(
        source_model_path   = source_path,
        output_model_path   = output_path,
        transformation_name = transformation_name,
        config              = executor_config,
    )

    repaired = False
    if not exec_result["success"] and enable_repair and api_key:
        error_msg = exec_result.get("error", "") or exec_result.get("stderr", "")
        if error_msg:
            print(f"[INFO]  model_{index_str}: attempting adaptive repair "
                  f"(error: {error_msg[:80].strip()}…)")
            try:
                from src.generator.adaptive_fixer import AdaptiveFixer
                fixer = AdaptiveFixer(api_key, max_attempts=3, provider=provider)
                _, fix_success, attempts = fixer.fix(
                    source_path     = source_path,
                    error_msg       = error_msg,
                    safety_note     = safety_note,
                    metamodel_paths = metamodel_paths,
                )
                if fix_success:
                    exec_result = run_transformation(
                        source_model_path   = source_path,
                        output_model_path   = output_path,
                        transformation_name = transformation_name,
                        config              = executor_config,
                    )
                    if exec_result["success"]:
                        repaired = True
                        print(f"[INFO]  model_{index_str}: repaired ✓")
            except Exception as e:
                print(f"[WARN]  model_{index_str}: repair error: {e}")

    if not exec_result["success"]:
        return False, [], 0.0, repaired, set()

    trace_path = exec_result.get("trace", "")
    if not trace_path or not os.path.isfile(trace_path):
        return True, [], 0.0, repaired, set()

    cov_result    = compute_rule_coverage(trace_path, atl_path)
    fired_rules   = set(cov_result.get("executed_rules", []))
    newly_covered = []
    for rule in fired_rules:
        if rule not in covered_rules:
            covered_rules.append(rule)
            newly_covered.append(rule)

    return True, newly_covered, cov_result["rule_coverage"], repaired, fired_rules


# ── Main generation function ──────────────────────────────────────────────────

def generate_tests(
    template_path:          str,
    metamodel_paths:        list,
    ocl_path:               str,
    example_paths:          list,
    atl_path:               str,
    api_key:                str,
    output_dir:             str,
    n:                      int  = 5,
    start_index:            int  = 1,
    use_coverage_guidance:  bool = True,
    verify_coverage:        bool = True,
    transform_dir:          str  = None,
    transformation_name:    str  = None,
    executor_config:        dict = None,
    rule_conditions:        dict = None,
    skip_rules:             set  = None,
    safety_note:            str  = None,
    enable_repair:          bool = True,
    fl_aware_feedback:      bool = False,
    mixed_mode_feedback:    bool = False,
    sat_aware_feedback:     bool = False,   # NEW: saturation-aware strategy
    pre_built_prompt:        str  = None,    # 直接传入构建好的prompt，跳过内部模板渲染
    llm_provider:            str  = None,    # 显式指定LLM provider，覆盖环境变量
    abort_on_api_error:      bool = False,   # API基础设施错误立即中止
) -> list:
    """
    Generate n test model pairs with coverage-guided adaptive prompting.

    Feedback strategy (mutually exclusive):
      sat_aware_feedback=True    Distribution-aware (SAT_AWARE).
                                 Tracks execution profiles and discourages
                                 failure saturation and profile repetition.
      mixed_mode_feedback=True   Three-mode mixed (balanced/moderate/simple).
      fl_aware_feedback=True     Strict FL-aware (single mode, minimal).
      all False (default)        Detection-oriented (original).

    New parameter
    -------------
    sat_aware_feedback : bool, default False
        Enables the SAT_AWARE prompt strategy.  Tracks fired_rules after
        each ATL execution and injects saturation-aware hints.
        Requires verify_coverage=True to collect fired_rules from traces.
    """
    # ── Mutual exclusion ──────────────────────────────────────────────────
    active = sum([sat_aware_feedback, mixed_mode_feedback, fl_aware_feedback])
    if active > 1:
        raise ValueError(
            "Only one of sat_aware_feedback / mixed_mode_feedback / "
            "fl_aware_feedback may be True at a time."
        )

    # safety_note 注入到 base_prompt（在 GENERATION REQUIREMENTS 之后）
    _sn = safety_note or ""
    if pre_built_prompt is not None:
        # 直接使用外部构建好的prompt，跳过内部模板渲染
        # 用于四档阶梯实验（run_ladder_experiment.py）
        base_prompt = pre_built_prompt
    else:
        base_prompt = build_prompt(
            template_path, metamodel_paths, ocl_path, example_paths, atl_path,
            safety_note=_sn,
        )

    # ── Defaults ──────────────────────────────────────────────────────────
    if transformation_name is None:
        transformation_name = os.path.splitext(os.path.basename(atl_path))[0]

    if rule_conditions is None:
        if "BibTeX2DocBook" in atl_path or "BibTeX" in atl_path:
            rule_conditions = _BIBTEX_RULE_CONDITIONS
        else:
            rule_conditions = {}

    if skip_rules is None:
        if "BibTeX2DocBook" in atl_path or "BibTeX" in atl_path:
            skip_rules = _BIBTEX_SKIP_RULES
        else:
            skip_rules = set()

    if safety_note is None:
        if "BibTeX2DocBook" in atl_path or "BibTeX" in atl_path:
            safety_note = _BIBTEX_SAFETY_NOTE
        elif "CPL2SPL" in atl_path or "/CPL" in atl_path:
            safety_note = _CPL_SAFETY_NOTE
        elif "UML2ER" in atl_path or "SimpleUml" in atl_path or "/UML" in atl_path:
            safety_note = _UML2ER_SAFETY_NOTE
        elif "Ecore2Maude" in atl_path or "Ecore" in atl_path:
            safety_note = _ECORE_SAFETY_NOTE
        else:
            safety_note = _GENERIC_SAFETY_NOTE

    # ── Select strategy ───────────────────────────────────────────────────
    if sat_aware_feedback:
        _strategy = "SAT_AWARE (saturation-aware distribution control)"
    elif mixed_mode_feedback:
        _strategy = "MIXED-MODE (balanced/moderate/simple)"
    elif fl_aware_feedback:
        _strategy = "FL-AWARE STRICT (single mode, minimal)"
    else:
        _strategy = "DETECTION-ORIENTED (original)"

    print(f"[INFO] Feedback strategy: {_strategy}")

    if mixed_mode_feedback:
        end_pos = start_index + n - 1
        if start_index < 1 or end_pos > 100:
            raise ValueError(
                f"mixed_mode_feedback requires global positions in [1, 100], "
                f"but this batch spans [{start_index}, {end_pos}]."
            )

    all_rules     = extract_rule_names(atl_path)
    covered_rules: list = []
    repair_stats  = {"attempted": 0, "succeeded": 0, "failed": 0}

    # SAT_AWARE: accumulate fired-rule sets across models
    profile_history: list = []   # list of set[str]

    if transform_dir is None:
        transform_dir = os.path.join(
            os.path.dirname(output_dir), "outputs",
            os.path.basename(output_dir))

    saved_files = []

    for i in range(start_index, start_index + n):
        index_str  = f"{i:04d}"
        global_pos = i
        batch_pos  = i - start_index + 1
        print(f"[INFO] Generating model {index_str} ({batch_pos}/{n})...")

        # ── SAT_AWARE: periodic profile summary log ───────────────────────
        if sat_aware_feedback and batch_pos % 10 == 1 and profile_history:
            from src.analyzer.execution_profile_analyzer import (
                build_saturation_feedback_context,
            )
            _ctx = build_saturation_feedback_context(profile_history)
            print(
                f"[SAT_AWARE] model {index_str} | "
                f"profile_diversity={_ctx['profile_diversity']:.3f} | "
                f"frequent_rules={list(_ctx['frequent_rules'].keys())} | "
                f"frequent_combos={len(_ctx['frequent_combinations'])}"
            )

        # ── Mode hint (mixed-mode only) ────────────────────────────────────
        if mixed_mode_feedback:
            mode      = _choose_mode_for_position(global_pos)
            mode_hint = _build_mode_hint(mode)
            print(f"[INFO] Mode: {mode}  phase={_mode_phase_label(global_pos)}")
        else:
            mode      = None
            mode_hint = ""

        # ── Coverage / saturation hint ────────────────────────────────────
        if use_coverage_guidance and all_rules:
            covered_set  = set(covered_rules)
            uncovered    = [r for r in all_rules
                            if r not in covered_set and r not in skip_rules]

            if sat_aware_feedback:
                from src.analyzer.execution_profile_analyzer import (
                    build_saturation_feedback_context,
                )
                profile_ctx  = build_saturation_feedback_context(profile_history)
                coverage_hint = build_saturation_aware_hint(
                    uncovered_rules = uncovered if uncovered else None,
                    covered_rules   = list(covered_set),
                    profile_context = profile_ctx,
                    safety_note     = safety_note,
                )
            elif mixed_mode_feedback:
                coverage_hint = _build_coverage_hint_mixed(
                    covered_rules, all_rules, rule_conditions,
                    skip_rules, safety_note)
            elif fl_aware_feedback:
                coverage_hint = _build_coverage_hint_fl_aware(
                    covered_rules, all_rules, rule_conditions,
                    skip_rules, safety_note)
            else:
                coverage_hint = _build_coverage_hint(
                    covered_rules, all_rules, rule_conditions,
                    skip_rules, safety_note)

            safe_uncovered = len(uncovered)
            print(f"[INFO] Coverage: {len(covered_set)}/{len(all_rules)} "
                  f"covered, {safe_uncovered} safe-uncovered")
        else:
            coverage_hint = (
                f"\nGenerate a different test model than previous ones. "
                f"Model index: {index_str}" + safety_note
            )

        # ── Assemble prompt ───────────────────────────────────────────────
        prompt = base_prompt + mode_hint + coverage_hint

        try:
            _provider = llm_provider or os.environ.get("LLM_PROVIDER", "deepseek")
            print(f"[INFO] Using LLM provider: {_provider}")
            call_logger.set_context(
                call_role          = "generation",
                model_index        = index_str,
                output_dir         = output_dir,
                transformation     = transformation_name or "",
            )
            raw_response = call_llm(prompt, api_key, provider=_provider)
        except Exception as e:
            print(f"[ERROR] API call failed for model {index_str}: {e}")
            if abort_on_api_error:
                raise
            continue

        source_xmi     = extract_xml_block(raw_response, "source_model")
        target_xmi     = extract_xml_block(raw_response, "target_model")
        coverage_notes = extract_xml_block(raw_response, "coverage_notes")

        # Missing source block is an RQ1 generation failure.
        if source_xmi is None:
            raw_path = os.path.join(output_dir, f"raw_response_{index_str}.txt")
            save_model(raw_response, raw_path)
            print(f"[WARN] model_{index_str}: LLM returned no <source_model> block")
            saved_files.append({
                "index":              index_str,
                "raw":                raw_path,
                "status":             "GENERATION_FAIL_NO_SOURCE_MODEL",
                "generation_failure": True,
                "exec_success":       False,
                "generation_mode":    mode,
                "mode_phase":         _mode_phase_label(global_pos) if mixed_mode_feedback else None,
            })
            continue

        source_path = os.path.join(output_dir, f"source_model_{index_str}.xmi")
        target_path = os.path.join(output_dir, f"target_model_{index_str}.xmi")

        # ── Skip if trace already exists ──────────────────────────────────
        if transform_dir:
            _trace_check = os.path.join(
                transform_dir, f"output_{index_str}_trace.xmi")
            if os.path.isfile(_trace_check) and os.path.isfile(source_path):
                print(f"[INFO] Skipping model {index_str}: trace already exists")
                # Try to recover fired rules for profile tracking
                if sat_aware_feedback:
                    try:
                        from src.analyzer.coverage_analyzer import compute_rule_coverage
                        cov = compute_rule_coverage(_trace_check, atl_path)
                        profile_history.append(set(cov.get("executed_rules", [])))
                    except Exception:
                        pass
                saved_files.append({
                    "index":           index_str,
                    "source":          source_path,
                    "repaired":        False,
                    "exec_success":    True,
                    "generation_mode": mode,
                    "mode_phase":      _mode_phase_label(global_pos) if mixed_mode_feedback else None,
                })
                continue

        notes_path = os.path.join(output_dir, f"coverage_notes_{index_str}.txt")
        raw_path   = os.path.join(output_dir, f"raw_response_{index_str}.txt")

        save_model(source_xmi, source_path)
        if target_xmi is not None:
            save_model(target_xmi, target_path)
            print(f"[INFO] Saved: {target_path}")
        else:
            target_path = None
        if coverage_notes is not None:
            save_model(coverage_notes, notes_path)
        save_model(raw_response, raw_path)
        print(f"[INFO] Saved: {source_path}")

        pair = {
            "index":           index_str,
            "source":          source_path,
            "notes":           notes_path,
            "raw":             raw_path,
            "repaired":        False,
            "generation_mode": mode,
            "mode_phase":      _mode_phase_label(global_pos) if mixed_mode_feedback else None,
        }
        if target_path is not None:
            pair["target"] = target_path

        if use_coverage_guidance and verify_coverage:
            success, newly, cov, repaired, fired_rules = _verify_and_update_coverage(
                source_path         = source_path,
                transform_dir       = transform_dir,
                index_str           = index_str,
                atl_path            = atl_path,
                transformation_name = transformation_name,
                covered_rules       = covered_rules,
                all_rules           = all_rules,
                executor_config     = executor_config,
                api_key             = api_key if enable_repair else None,
                safety_note         = safety_note,
                metamodel_paths     = metamodel_paths,
                enable_repair       = enable_repair,
                provider            = llm_provider,
            )
            pair["exec_success"]  = success
            pair["rule_coverage"] = cov
            pair["repaired"]      = repaired

            # SAT_AWARE: record fired rules for next-round profile context
            if sat_aware_feedback and success and fired_rules:
                profile_history.append(fired_rules)

            if repaired:
                repair_stats["succeeded"] += 1
            elif not success:
                repair_stats["failed"] += 1

            if success:
                repair_tag = " [REPAIRED]" if repaired else ""
                print(
                    f"[INFO] ATL verified{repair_tag}: "
                    f"coverage={cov:.2%} | newly={newly} | "
                    f"total={len(set(covered_rules))}/{len(all_rules)}"
                )
            else:
                repair_stats["attempted"] += 1 if enable_repair else 0
                print(f"[WARN] model_{index_str}: ATL failed, coverage unchanged")

        saved_files.append(pair)

    # ── Summary ───────────────────────────────────────────────────────────
    if use_coverage_guidance and verify_coverage and all_rules:
        covered_set  = set(covered_rules)
        safe_total   = len([r for r in all_rules if r not in skip_rules])
        safe_covered = len([r for r in covered_set if r not in skip_rules])
        uncovered    = [r for r in all_rules
                        if r not in covered_set and r not in skip_rules]
        print(f"\n[SUMMARY] Batch coverage: {safe_covered}/{safe_total} safe rules covered")
        if uncovered:
            print(f"[SUMMARY] Still uncovered: {uncovered}")
        else:
            print(f"[SUMMARY] All safe rules covered!")

    if enable_repair and (repair_stats["succeeded"] + repair_stats["failed"]) > 0:
        total_r = repair_stats["succeeded"] + repair_stats["failed"]
        print(f"[SUMMARY] Adaptive repair: "
              f"{repair_stats['succeeded']}/{total_r} succeeded "
              f"({repair_stats['succeeded']/total_r:.0%})")

    if mixed_mode_feedback:
        mode_counts: dict = {}
        for p in saved_files:
            m = p.get("generation_mode") or "unknown"
            mode_counts[m] = mode_counts.get(m, 0) + 1
        expected = _verify_mode_counts_range(start_index, n)
        print(f"[SUMMARY] Mode distribution (actual):   {mode_counts}")
        print(f"[SUMMARY] Mode distribution (expected for pos {start_index}-"
              f"{start_index+n-1}): {expected}")

    if sat_aware_feedback and profile_history:
        from src.analyzer.execution_profile_analyzer import (
            build_saturation_feedback_context,
        )
        final_ctx = build_saturation_feedback_context(profile_history)
        print(f"[SUMMARY][SAT_AWARE] Final profile diversity: "
              f"{final_ctx['profile_diversity']:.3f}")
        print(f"[SUMMARY][SAT_AWARE] Total profiles tracked: "
              f"{final_ctx['num_profiles']}")
        if final_ctx["frequent_rules"]:
            print(f"[SUMMARY][SAT_AWARE] Frequent rules (≥0.7): "
                  f"{list(final_ctx['frequent_rules'].keys())}")

    return saved_files


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))

    dataset_dir   = os.path.join(base_dir, "datasets", "models_BibTexML2DocBook")
    template_path = os.path.join(base_dir, "prompts", "generate_test_model.txt")
    ocl_path      = os.path.join(dataset_dir, "OCL_Constraints.txt")
    scenarios_dir = os.path.join(dataset_dir, "scenarios")
    atl_path      = os.path.join(dataset_dir, "transformations", "BibTeX2DocBook.atl")
    api_key_path  = os.path.join(base_dir, "config", "deepseek_api_key.txt")
    output_dir    = os.path.join(base_dir, "results", "generated_models",
                                 "BibTeX2DocBook", "sat_aware_test")

    from src.llm.llm_client import read_api_key
    api_key         = read_api_key(api_key_path)
    example_paths   = get_example_paths(scenarios_dir, max_scenarios=3)
    metamodel_paths = get_metamodel_paths(dataset_dir, config="core")

    saved = generate_tests(
        template_path         = template_path,
        metamodel_paths       = metamodel_paths,
        ocl_path              = ocl_path,
        example_paths         = example_paths,
        atl_path              = atl_path,
        api_key               = api_key,
        output_dir            = output_dir,
        n                     = 3,
        start_index           = 1,
        use_coverage_guidance = True,
        verify_coverage       = True,
        enable_repair         = True,
        sat_aware_feedback    = True,
    )
    print(f"\n[INFO] Generated {len(saved)} model pair(s).")


if __name__ == "__main__":
    main()
