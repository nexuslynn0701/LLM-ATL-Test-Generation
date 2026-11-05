# src/analyzer/sbfl_analyzer.py
#
# Spectrum-Based Fault Localization (SBFL) for ATL model transformations.
#
# Strictly aligned with Troya et al. (2018) "Spectrum-Based Fault
# Localisation of Model Transformations" (MODELS 2018).
#
# Six SBFL formulae, all definitions verified against:
#   [1] Abreu et al. (2007) "On the Accuracy of Spectrum-based Fault
#       Localisation" — Ochiai, Tarantula, Mountford
#   [2] Wong et al. (2014) "The DStar Method for Effective Software
#       Fault Localization" — D*
#   [3] Naish et al. (2011) "A Model for Spectra-based Software Diagnosis"
#       — Kulczynski2
#   [4] Janssen et al. (2009) "Zoltar: A Spectrum-based Fault Localisation
#       Tool" — Zoltar
#
# EXAM score computed with three tie-breaking strategies (Troya 2018 §4.3):
#   AC (Average Case)  — primary result, matches Table 7
#   BC (Best Case)     — lower bound
#   WC (Worst Case)    — upper bound
#
# Notation (consistent across all formulae):
#   ef  = # failing tests that EXECUTE   rule r
#   ep  = # passing tests that EXECUTE   rule r
#   nf  = # failing tests that DON'T execute r
#   np  = # passing tests that DON'T execute r
#   Higher suspiciousness score = more suspicious (likely faulty).

import csv
import math
import logging
import statistics
from pathlib import Path

import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Buggy rule registry  (extracted from SBFL_MT Java source, Troya et al.)
# ─────────────────────────────────────────────────────────────────────────────

BUGGY_RULES = {
    # ── BibTeX2DocBook (40 mutants) ───────────────────────────────────────────
    "BibTeX2DocBook_Mutant1":  ["Article_Title_Journal"],
    "BibTeX2DocBook_Mutant2":  ["Main"],
    "BibTeX2DocBook_Mutant3":  ["Author"],
    "BibTeX2DocBook_Mutant4":  ["Article_NoTitle_NoJournal"],
    "BibTeX2DocBook_Mutant5":  ["Author"],
    "BibTeX2DocBook_Mutant6":  ["UntitledEntry"],
    "BibTeX2DocBook_Mutant7":  ["TitledEntry_Title_NoArticle"],
    "BibTeX2DocBook_Mutant8":  ["Main"],
    "BibTeX2DocBook_Mutant9":  ["TitledEntry_Title_NoArticle"],
    "BibTeX2DocBook_Mutant10": ["TitledEntry_NoTitle_NoArticle"],
    "BibTeX2DocBook_Mutant11": ["Article_Title_Journal"],
    "BibTeX2DocBook_Mutant12": ["Article_NoTitle_Journal"],
    "BibTeX2DocBook_Mutant13": ["Author"],
    "BibTeX2DocBook_Mutant14": ["Article_Title_NoJournal"],
    "BibTeX2DocBook_Mutant15": ["UntitledEntry"],
    "BibTeX2DocBook_Mutant16": ["Article_NoTitle_NoJournal"],
    "BibTeX2DocBook_Mutant17": ["Main"],
    "BibTeX2DocBook_Mutant18": ["TitledEntry_Title_NoArticle"],
    "BibTeX2DocBook_Mutant19": ["TitledEntry_NoTitle_NoArticle"],
    "BibTeX2DocBook_Mutant20": ["Article_Title_Journal"],
    "BibTeX2DocBook_Mutant21": ["Main"],
    "BibTeX2DocBook_Mutant22": ["TitledEntry_Title_NoArticle"],
    "BibTeX2DocBook_Mutant23": ["Article_Title_Journal"],
    "BibTeX2DocBook_Mutant24": ["Author"],
    "BibTeX2DocBook_Mutant25": ["TitledEntry_Title_NoArticle"],
    "BibTeX2DocBook_Mutant26": ["Main"],
    "BibTeX2DocBook_Mutant27": ["TitledEntry_Title_NoArticle", "TitledEntry_NoTitle_NoArticle"],
    "BibTeX2DocBook_Mutant28": ["Article_Title_Journal",       "Article_NoTitle_Journal"],
    "BibTeX2DocBook_Mutant29": ["Author",                      "UntitledEntry"],
    "BibTeX2DocBook_Mutant30": ["Main",                        "TitledEntry_Title_NoArticle"],
    "BibTeX2DocBook_Mutant31": ["Article_Title_Journal",       "Main"],
    "BibTeX2DocBook_Mutant32": ["Author",                      "TitledEntry_NoTitle_NoArticle"],
    "BibTeX2DocBook_Mutant33": ["UntitledEntry",               "TitledEntry_Title_NoArticle"],
    "BibTeX2DocBook_Mutant34": ["TitledEntry_Title_NoArticle", "TitledEntry_NoTitle_NoArticle"],
    "BibTeX2DocBook_Mutant35": ["Main",                        "Author"],
    "BibTeX2DocBook_Mutant36": ["UntitledEntry",               "Article_Title_Journal"],
    "BibTeX2DocBook_Mutant37": ["Article_NoTitle_Journal",     "Article_Title_NoJournal"],
    "BibTeX2DocBook_Mutant38": ["TitledEntry_Title_NoArticle", "Article_Title_Journal"],
    "BibTeX2DocBook_Mutant39": ["Main",                        "TitledEntry_Title_NoArticle"],
    "BibTeX2DocBook_Mutant40": ["Author",                      "UntitledEntry"],

    # ── UML2ER (18 mutants) ───────────────────────────────────────────────────
    "SimpleUml2ER_Mutant1":  ["StrongReferences"],
    "SimpleUml2ER_Mutant2":  ["References"],
    "SimpleUml2ER_Mutant3":  ["Attributes"],
    "SimpleUml2ER_Mutant4":  ["Class"],
    "SimpleUml2ER_Mutant5":  ["Attributes"],
    "SimpleUml2ER_Mutant6":  ["Package"],
    "SimpleUml2ER_Mutant7":  ["Attributes"],
    "SimpleUml2ER_Mutant8":  ["StrongReferences"],
    "SimpleUml2ER_Mutant9":  ["WeakReferences"],
    "SimpleUml2ER_Mutant10": ["NamedElement"],
    "SimpleUml2ER_Mutant11": ["Attributes"],
    "SimpleUml2ER_Mutant12": ["Attributes",     "References"],
    "SimpleUml2ER_Mutant13": ["Class",          "Attributes"],
    "SimpleUml2ER_Mutant14": ["Attributes",     "WeakReferences"],
    "SimpleUml2ER_Mutant15": ["Package",        "Attributes"],
    "SimpleUml2ER_Mutant16": ["WeakReferences", "StrongReferences"],
    "SimpleUml2ER_Mutant17": ["Package",        "Class"],
    "SimpleUml2ER_Mutant18": ["Property",       "Class"],

    # ── CPL2SPL (50 mutants) ──────────────────────────────────────────────────
    "CPL2SPL_Mutant1":  ["Proxy2Select"],
    "CPL2SPL_Mutant2":  ["CPL2Program"],
    "CPL2SPL_Mutant3":  ["Redirection2SelectCase"],
    "CPL2SPL_Mutant4":  ["Redirect2Return"],
    "CPL2SPL_Mutant5":  ["Busy2SelectCase"],
    "CPL2SPL_Mutant6":  ["SubAction2Function"],
    "CPL2SPL_Mutant7":  ["Redirect2Return"],
    "CPL2SPL_Mutant8":  ["SubAction2Function"],
    "CPL2SPL_Mutant9":  ["Outgoing2Method"],
    "CPL2SPL_Mutant10": ["Outgoing2Method"],
    "CPL2SPL_Mutant11": ["NotPresent2ErrorResponse"],
    "CPL2SPL_Mutant12": ["CPL2Program"],
    "CPL2SPL_Mutant13": ["SubAction2Function"],
    "CPL2SPL_Mutant14": ["Busy2SelectCase"],
    "CPL2SPL_Mutant15": ["Redirection2SelectCase"],
    "CPL2SPL_Mutant16": ["Redirect2Return"],
    "CPL2SPL_Mutant17": ["Redirection2SelectCase"],
    "CPL2SPL_Mutant18": ["CPL2Program"],
    "CPL2SPL_Mutant19": ["Redirection2SelectCase"],
    "CPL2SPL_Mutant20": ["Proxy2Select"],
    "CPL2SPL_Mutant21": ["CPL2Program"],
    "CPL2SPL_Mutant22": ["Outgoing2Method"],
    "CPL2SPL_Mutant23": ["AddressSwitch2SelectStat"],
    "CPL2SPL_Mutant24": ["Proxy2Select"],
    "CPL2SPL_Mutant25": ["SubCall2Return"],
    "CPL2SPL_Mutant26": ["CPL2Program"],
    "CPL2SPL_Mutant27": ["SwitchedAddress2SelectCase"],
    "CPL2SPL_Mutant28": ["AddressSwitch2SelectStat"],
    "CPL2SPL_Mutant29": ["SubCall2Return"],
    "CPL2SPL_Mutant30": ["Redirect2Return"],
    "CPL2SPL_Mutant31": ["SubAction2Function"],
    "CPL2SPL_Mutant32": ["CPL2Program"],
    "CPL2SPL_Mutant33": ["Proxy2Select"],
    "CPL2SPL_Mutant34": ["SwitchedAddress2SelectCase"],
    "CPL2SPL_Mutant35": ["Otherwise2SelectDefault"],
    "CPL2SPL_Mutant36": ["Proxy2Select"],
    "CPL2SPL_Mutant37": ["NoAnswer2SelectCase",      "Redirection2SelectCase"],
    "CPL2SPL_Mutant38": ["Busy2SelectCase",           "NoAnswer2SelectCase"],
    "CPL2SPL_Mutant39": ["CPL2Program",               "Redirection2SelectCase"],
    "CPL2SPL_Mutant40": ["SubAction2Function",        "Outgoing2Method"],
    "CPL2SPL_Mutant41": ["Busy2SelectCase",           "Redirect2Return"],
    "CPL2SPL_Mutant42": ["CPL2Program",               "Redirection2SelectCase"],
    "CPL2SPL_Mutant43": ["CPL2Program",               "Proxy2Select"],
    "CPL2SPL_Mutant44": ["SubCall2Return",            "Redirect2Return"],
    "CPL2SPL_Mutant45": ["Redirection2SelectCase",    "SubAction2Function"],
    "CPL2SPL_Mutant46": ["SwitchedAddress2SelectCase","Proxy2Select"],
    "CPL2SPL_Mutant47": ["Main",                      "SubAction2Function"],
    "CPL2SPL_Mutant48": ["Outgoing2Method",           "Proxy2Select"],
    "CPL2SPL_Mutant49": ["SubCall2Return",            "Redirect2Return"],
    "CPL2SPL_Mutant50": ["Redirect2Return",           "SubAction2Function"],

    # ── Ecore2Maude (50 mutants) ──────────────────────────────────────────────
    "Ecore2Maude_Mutant1":  ["EmptyList"],
    "Ecore2Maude_Mutant2":  ["EqName"],
    "Ecore2Maude_Mutant3":  ["Initialize"],
    "Ecore2Maude_Mutant4":  ["Class2Sort"],
    "Ecore2Maude_Mutant5":  ["Class2Sort"],
    "Ecore2Maude_Mutant6":  ["Initialize"],
    "Ecore2Maude_Mutant7":  ["Initialize"],
    "Ecore2Maude_Mutant8":  ["Class2Sort"],
    "Ecore2Maude_Mutant9":  ["Class2Sort"],
    "Ecore2Maude_Mutant10": ["Reference2Operation"],
    "Ecore2Maude_Mutant11": ["Attribute2Operation"],
    "Ecore2Maude_Mutant12": ["Attribute2Operation"],
    "Ecore2Maude_Mutant13": ["Enum2Sort"],
    "Ecore2Maude_Mutant14": ["Enum2Sort"],
    "Ecore2Maude_Mutant15": ["EnumLiteral2Operation"],
    "Ecore2Maude_Mutant16": ["MetamodelEqName"],
    "Ecore2Maude_Mutant17": ["Reference2Operation"],
    "Ecore2Maude_Mutant18": ["Package2Operation"],
    "Ecore2Maude_Mutant19": ["Initialize"],
    "Ecore2Maude_Mutant20": ["Class2Sort"],
    "Ecore2Maude_Mutant21": ["EqType"],
    "Ecore2Maude_Mutant22": ["EqLowerBound"],
    "Ecore2Maude_Mutant23": ["EqUpperBound"],
    "Ecore2Maude_Mutant24": ["Reference2Operation"],
    "Ecore2Maude_Mutant25": ["EqContainingClass"],
    "Ecore2Maude_Mutant26": ["Attribute2Operation"],
    "Ecore2Maude_Mutant27": ["RefEqOpposite"],
    "Ecore2Maude_Mutant28": ["EqIsUnique"],
    "Ecore2Maude_Mutant29": ["Attribute2Operation"],
    "Ecore2Maude_Mutant30": ["EqPackage"],
    "Ecore2Maude_Mutant31": ["EnumEqMetaAux"],
    "Ecore2Maude_Mutant32": ["Class2Sort"],
    "Ecore2Maude_Mutant33": ["Attribute2Operation"],
    "Ecore2Maude_Mutant34": ["MetamodelEqName",    "MetamodelEqPackages"],
    "Ecore2Maude_Mutant35": ["EnumEqMetaAux",      "EnumEqDefaultValue"],
    "Ecore2Maude_Mutant36": ["EqLowerBound",       "EqUpperBound"],
    "Ecore2Maude_Mutant37": ["Class2Sort",          "Reference2Operation"],
    "Ecore2Maude_Mutant38": ["EqIsOrdered",         "EqIsUnique"],
    "Ecore2Maude_Mutant39": ["EnumLiteral2Operation","Attribute2Operation"],
    "Ecore2Maude_Mutant40": ["ClassEqAttributes",   "EqType"],
    "Ecore2Maude_Mutant41": ["ClassEqIsAbstract",   "EqPackage", "ClassEqSuperTypes"],
    "Ecore2Maude_Mutant42": ["Initialize", "Package2Operation", "PackEqMetamodel",
                              "PackEqSupPackage", "PackEqSubPackages",
                              "PackEqClasses", "EqPackage"],
    "Ecore2Maude_Mutant43": ["PackEqMetamodel",     "PackEqSupPackage", "PackEqSubPackages"],
    "Ecore2Maude_Mutant44": ["Initialize",          "Class2Sort"],
    "Ecore2Maude_Mutant45": ["Class2Sort",           "Attribute2Operation"],
    "Ecore2Maude_Mutant46": ["Attribute2Operation",  "Enum2Sort"],
    "Ecore2Maude_Mutant47": ["EqPackage",            "EnumEqMetaAux"],
    "Ecore2Maude_Mutant48": ["Class2Sort",           "EqType"],
    "Ecore2Maude_Mutant49": ["Initialize",           "Reference2Operation"],
    "Ecore2Maude_Mutant50": ["EqUpperBound",         "EqContainingClass"],
}


# ─────────────────────────────────────────────────────────────────────────────
# SBFL formulae  — precisely aligned to published definitions
# ─────────────────────────────────────────────────────────────────────────────
#
# Boundary convention (applied uniformly):
#   • ef == 0  →  rule never executed by a failing test  →  return 0.0
#   • Any remaining 0/0 or sqrt(0) case                  →  return 0.0
#   • Perfect discriminator (ep==0, nf==0, ef>0) for D*/Mountford
#     → return sentinel 1e9  (ranks first, consistent with ∞ interpretation)


def _tarantula(ef: int, ep: int, nf: int, np: int) -> float:
    """
    Tarantula — Jones & Harrold (ICSE 2005).

    Exact definition (Abreu et al. 2007, Eq. 3):

        fail_rate = ef / (ef + nf)
        pass_rate = ep / (ep + np)
        susp = fail_rate / (fail_rate + pass_rate)

    Interpretation: the fraction of failing tests that execute r,
    normalised by adding the analogous fraction for passing tests.
    This is *not* ef / (ef + ep); the denominators are different.
    """
    total_fail = ef + nf
    total_pass = ep + np

    if total_fail == 0:
        return 0.0   # no failing tests → formula undefined

    fail_rate = ef / total_fail
    pass_rate = (ep / total_pass) if total_pass > 0 else 0.0

    denom = fail_rate + pass_rate
    if denom == 0.0:
        return 0.0
    return fail_rate / denom


def _ochiai(ef: int, ep: int, nf: int, np: int) -> float:
    """
    Ochiai — Abreu et al. (ISSRE 2006 / AST 2007), Eq. 2.

        susp = ef / sqrt((ef + nf) * (ef + ep))
    """
    if ef == 0:
        return 0.0
    denom = math.sqrt((ef + nf) * (ef + ep))
    return (ef / denom) if denom > 0.0 else 0.0


def _dstar(ef: int, ep: int, nf: int, np: int, star: int = 2) -> float:
    """
    D* — Wong et al. (TSE 2014), Eq. 6.  Default star=2 (D²).

        susp = ef^star / (ep + nf)

    star=2 is used by Troya et al. (2018) to reproduce Table 7.
    When ep + nf == 0 and ef > 0 (perfect discriminator) the formula
    is ∞; we return the sentinel 1e9 so the rule ranks first.
    """
    if ef == 0:
        return 0.0
    denom = ep + nf
    if denom == 0:
        return 1e9   # perfect discriminator → maximum suspicion
    return (ef ** star) / denom


def _kulczynski2(ef: int, ep: int, nf: int, np: int) -> float:
    """
    Kulczynski2 — Naish et al. (TOSEM 2011), Table 1, row K2.

        susp = 0.5 * ( ef/(ef+nf) + ef/(ef+ep) )

    Arithmetic mean of P(execute r | fail) and P(fail | execute r).
    """
    if ef == 0:
        return 0.0
    t1 = ef / (ef + nf) if (ef + nf) > 0 else 0.0
    t2 = ef / (ef + ep) if (ef + ep) > 0 else 0.0
    return 0.5 * (t1 + t2)


def _mountford(ef: int, ep: int, nf: int, np: int) -> float:
    """
    Mountford — Abreu et al. (AST 2007), Table 1.

    Standard definition from the SBFL survey (Abreu / Lucia et al.),
    which is the version referenced by Troya et al. (2018):

        susp = ef / ( 0.5*(ef*ep + ef*nf) + ep*nf )

    Note: this differs from some ecological variants of the Mountford
    similarity index; we use the SBFL-specific form here.

    When ep==0 and nf==0 (perfect discriminator, denominator==0)
    we return the sentinel 1e9.
    """
    if ef == 0:
        return 0.0
    denom = 0.5 * (ef * ep + ef * nf) + ep * nf
    if denom == 0.0:
        return 1e9   # perfect discriminator → maximum suspicion
    return ef / denom


def _zoltar(ef: int, ep: int, nf: int, np: int) -> float:
    """
    Zoltar — Janssen et al. (TAIC-PART 2009).

    Original paper definition:

        susp = ef / ( ef + nf + ep + (10000 * nf * ep) / ef )   if ef > 0
             = 0                                                  if ef = 0

    The 10000*nf*ep/ef penalty heavily down-ranks rules executed by many
    passing tests, making Zoltar more conservative than Ochiai.
    """
    if ef == 0:
        return 0.0
    penalty = (10000.0 * nf * ep) / ef
    denom   = ef + nf + ep + penalty
    return (ef / denom) if denom > 0.0 else 0.0

# ── 新增13个公式，对照Troya et al. (2018) Table 6 ──────────────────────────

def _arithmetic_mean(ef: int, ep: int, nf: int, np: int) -> float:
    """
    Arithmetic Mean [Naish et al. / Troya Table 6, ref.117]
    
    formula: 2*(ef*np - nf*ep) / 
             ((ef+ep)*(np+nf) + (ef+nf)*(ep+np))
    """
    if ef == 0:
        return 0.0
    num   = 2.0 * (ef * np - nf * ep)
    denom = (ef + ep) * (np + nf) + (ef + nf) * (ep + np)
    if denom == 0.0:
        return 0.0
    return num / denom


def _barinel(ef: int, ep: int, nf: int, np: int) -> float:
    """
    Barinel [Abreu et al. 2009 / Troya Table 6, ref.2]
    
    formula: 1 - ep/(ep+ef)
    """
    if ef == 0:
        return 0.0
    denom = ep + ef
    if denom == 0:
        return 0.0
    return 1.0 - (ep / denom)


def _baroni_urbani_buser(ef: int, ep: int, nf: int, np: int) -> float:
    """
    Baroni-Urbani & Buser [Troya Table 6, ref.114]
    
    formula: (sqrt(ef*np) + ef) / (sqrt(ef*np) + ef + ep + nf)
    """
    if ef == 0:
        return 0.0
    sqrt_term = math.sqrt(ef * np)
    num   = sqrt_term + ef
    denom = sqrt_term + ef + ep + nf
    if denom == 0.0:
        return 0.0
    return num / denom


def _braun_banquet(ef: int, ep: int, nf: int, np: int) -> float:
    """
    Braun-Banquet [Troya Table 6, ref.115]
    
    formula: ef / max(ef+ep, ef+nf)
    """
    if ef == 0:
        return 0.0
    denom = max(ef + ep, ef + nf)
    if denom == 0:
        return 0.0
    return ef / denom


def _cohen(ef: int, ep: int, nf: int, np: int) -> float:
    """
    Cohen [Troya Table 6, ref.78]
    
    formula: 2*(ef*np - nf*ep) /
             ((ef+ep)*(np+ep) + (ef+nf)*(nf+np))
    
    Note: differs from Arithmetic Mean only in denominator.
    Arithmetic Mean denom: (ef+ep)*(np+nf) + (ef+nf)*(ep+np)
    Cohen denom:           (ef+ep)*(np+ep) + (ef+nf)*(nf+np)
    """
    if ef == 0:
        return 0.0
    num   = 2.0 * (ef * np - nf * ep)
    denom = (ef + ep) * (np + ep) + (ef + nf) * (nf + np)
    if denom == 0.0:
        return 0.0
    return num / denom


def _ochiai2(ef: int, ep: int, nf: int, np: int) -> float:
    """
    Ochiai2 [Troya Table 6, ref.11]
    
    formula: ef*np / sqrt((ef+ep)*(np+nf)*(ef+nf)*(ep+np))
    """
    if ef == 0:
        return 0.0
    num   = ef * np
    denom = math.sqrt(
        (ef + ep) * (np + nf) * (ef + nf) * (ep + np)
    )
    if denom == 0.0:
        return 0.0
    return num / denom


def _op2(ef: int, ep: int, nf: int, np: int) -> float:
    """
    Op2 [Troya Table 6, ref.78]
    
    formula: ef - ep/(NS+1)
    where NS = ep + np (total passing tests)
    """
    if ef == 0:
        return 0.0
    ns = ep + np
    return ef - ep / (ns + 1)


def _phi(ef: int, ep: int, nf: int, np: int) -> float:
    """
    Phi coefficient [Troya Table 6, ref.74]
    
    formula: (ef*np - nf*ep) /
             sqrt((ef+ep)*(ef+nf)*(ep+np)*(nf+np))
    """
    if ef == 0:
        return 0.0
    num   = ef * np - nf * ep
    denom = math.sqrt(
        (ef + ep) * (ef + nf) * (ep + np) * (nf + np)
    )
    if denom == 0.0:
        return 0.0
    return num / denom


def _pierce(ef: int, ep: int, nf: int, np: int) -> float:
    """
    Pierce [Troya Table 6, ref.115]
    
    formula: (ef*nf + nf*ep) / (ef*nf + 2*nf*np + ep*np)
    
    Verified against Table 6:
    num   = NCF*NUF + NUF*NCS = ef*nf + nf*ep
    denom = NCF*NUF + 2*NUF*NUS + NCS*NUS = ef*nf + 2*nf*np + ep*np
    """
    if ef == 0:
        return 0.0
    num   = ef * nf + nf * ep
    denom = ef * nf + 2 * nf * np + ep * np
    if denom == 0.0:
        return 0.0
    return num / denom


def _rogers_tanimoto(ef: int, ep: int, nf: int, np: int) -> float:
    """
    Rogers & Tanimoto [Troya Table 6, ref.73]
    
    formula: (ef+np) / (ef+np + 2*(nf+ep))
    """
    if ef == 0:
        return 0.0
    num   = ef + np
    denom = ef + np + 2 * (nf + ep)
    if denom == 0.0:
        return 0.0
    return num / denom


def _russell_rao(ef: int, ep: int, nf: int, np: int) -> float:
    """
    Russell-Rao [Troya Table 6, ref.85]
    
    formula: ef / (ef + nf + ep + np)
    """
    if ef == 0:
        return 0.0
    denom = ef + nf + ep + np
    if denom == 0:
        return 0.0
    return ef / denom


def _simple_matching(ef: int, ep: int, nf: int, np: int) -> float:
    """
    Simple Matching [Troya Table 6, ref.115]
    
    formula: (ef+np) / (ef+ep+np+nf)
    """
    if ef == 0:
        return 0.0
    num   = ef + np
    denom = ef + ep + np + nf
    if denom == 0.0:
        return 0.0
    return num / denom


# Public formula registry and canonical order
FORMULAE: dict = {
    # original 6
    "ochiai":              _ochiai,
    "tarantula":           _tarantula,
    "dstar":               _dstar,
    "kulczynski2":         _kulczynski2,
    "mountford":           _mountford,
    "zoltar":              _zoltar,
    # new 12 (Troya et al. 2018 Table 6)
    "arithmetic_mean":     _arithmetic_mean,
    "barinel":             _barinel,
    "baroni_urbani_buser": _baroni_urbani_buser,
    "braun_banquet":       _braun_banquet,
    "cohen":               _cohen,
    "ochiai2":             _ochiai2,
    "op2":                 _op2,
    "phi":                 _phi,
    "pierce":              _pierce,
    "rogers_tanimoto":     _rogers_tanimoto,
    "russell_rao":         _russell_rao,
    "simple_matching":     _simple_matching,
}

FORMULA_ORDER: list = [
    "arithmetic_mean",
    "barinel",
    "braun_banquet",
    "baroni_urbani_buser",
    "cohen",
    "dstar",
    "kulczynski2",
    "mountford",
    "ochiai",
    "ochiai2",
    "op2",
    "phi",
    "pierce",
    "rogers_tanimoto",
    "russell_rao",
    "simple_matching",
    "tarantula",
    "zoltar",
]

TIE_MODES: tuple = ("AC", "BC", "WC")


# ─────────────────────────────────────────────────────────────────────────────
# Tie-breaking  (Troya et al. 2018, §4.3)
# ─────────────────────────────────────────────────────────────────────────────
#
# BC (Best Case)    = 1 + #{rules with STRICTLY higher suspiciousness}
# WC (Worst Case)   = #{rules with suspiciousness >= target}
#                   = BC + #{rules with same score} - 1
# AC (Average Case) = (BC + WC) / 2   ← primary result, matches Table 7
#
# Multi-fault mutants (multiple buggy rules):
#   BC → min of per-rule EXAM values   (most optimistic)
#   WC → max of per-rule EXAM values   (most pessimistic)
#   AC → mean of per-rule EXAM values  (primary result)


def _rank_one_rule(
    svals:     dict,
    rule:      str,
    all_rules: list,
    mode:      str,
) -> float:
    """
    Return EXAM = rank / |R| for `rule` under `mode`.
    Returns 1.0 if `rule` is absent from svals (worst-case fallback).
    """
    if rule not in svals:
        return 1.0

    n_rules      = len(all_rules)
    target_score = svals[rule]

    higher = sum(1 for r in all_rules if svals.get(r, 0.0) > target_score)
    tied   = sum(1 for r in all_rules if svals.get(r, 0.0) == target_score)

    rank_bc = higher + 1
    rank_wc = higher + tied
    rank_ac = (rank_bc + rank_wc) / 2.0

    if   mode == "BC": return rank_bc / n_rules
    elif mode == "WC": return rank_wc / n_rules
    else:              return rank_ac / n_rules  # AC


def _exam_for_buggy_rules(
    svals:       dict,
    buggy_rules: list,
    all_rules:   list,
    mode:        str,
) -> float:
    """Aggregate EXAM score for a (possibly multi-fault) mutant."""
    per_rule = [_rank_one_rule(svals, r, all_rules, mode) for r in buggy_rules]
    if not per_rule:
        return 1.0
    if   mode == "BC": return min(per_rule)
    elif mode == "WC": return max(per_rule)
    else:              return sum(per_rule) / len(per_rule)  # AC


# ─────────────────────────────────────────────────────────────────────────────
# XMI / Trace helpers
# ─────────────────────────────────────────────────────────────────────────────


def _outputs_differ(original_output, mutant_output) -> bool:
    """
    Compare one-output or multi-output transformation results.

    For multi-output transformations, original_output and mutant_output are
    dicts like {"OUTMaven": path, "OUTProject": path}. The mutant is failing
    if any declared output differs or if one side is missing an output.
    """
    if isinstance(original_output, dict) or isinstance(mutant_output, dict):
        if not isinstance(original_output, dict) or not isinstance(mutant_output, dict):
            return True

        names = set(original_output) | set(mutant_output)
        for name in names:
            if name not in original_output or name not in mutant_output:
                return True
            if _models_differ(original_output[name], mutant_output[name]):
                return True
        return False

    return _models_differ(original_output, mutant_output)


def _parse_trace_rules(trace_path: str) -> set:
    """
    Return the set of ATL rule names executed in `trace_path` (XMI).
    The synthetic "createTrace" rule is excluded.
    """
    executed: set = set()
    try:
        tree = ET.parse(trace_path)
        for elem in tree.getroot().iter():
            if elem.tag.endswith("traceLinks") or elem.tag == "traceLinks":
                rule = elem.get("ruleName")
                if rule and rule != "createTrace":
                    executed.add(rule)
    except Exception as exc:
        logger.warning(f"Failed to parse trace {trace_path}: {exc}")
    return executed


def _models_differ(output_path: str, mutant_output_path: str) -> bool:
    """
    Return True if the test FAILS for this mutant (mutant detected).

    Uses structural XMI comparison (ignores xmi:id, attribute order,
    whitespace). Child ordering is preserved because ordered EReferences
    can make serialized containment order semantically relevant.
    """
    try:
        from src.analyzer.coverage_analyzer import compare_xmi_models
        return not compare_xmi_models(output_path, mutant_output_path)
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Core per-mutant SBFL computation
# ─────────────────────────────────────────────────────────────────────────────

def compute_sbfl_for_mutant(
    trace_paths:         list,
    output_paths:        list,
    mutant_output_paths: list,
    all_rules:           list,
    mutant_name:         str,
    buggy_rules:         list,
    formulae:            list = None,
) -> dict:
    """
    Compute SBFL suspiciousness and EXAM score for ONE mutant independently.

    Each call builds its own coverage matrix, making results directly
    comparable to Troya et al. (2018) Table 7 (per-mutant evaluation).

    Parameters
    ----------
    trace_paths         : list[str]  — trace XMI per test model
    output_paths        : list[str]  — original transformation output per test
    mutant_output_paths : list[str]  — mutant transformation output per test
    all_rules           : list[str]  — complete ATL rule list (defines |R|)
    mutant_name         : str
    buggy_rules         : list[str]  — truly faulty rule(s)
    formulae            : list[str]  — subset of FORMULA_ORDER (default: all)

    Returns
    -------
    dict with keys:
        mutant        : str
        buggy_rules   : list[str]
        total_tests   : int
        total_fail    : int
        total_pass    : int
        rule_stats    : dict[rule → {ef, ep, nf, np}]
        scores        : dict[formula → dict[rule → float]]
        exam_scores   : dict["{formula}_{mode}" → float]
                        18 keys total (6 formulae × 3 modes)
                        Primary paper result = *_AC keys.
    """
    if formulae is None:
        formulae = FORMULA_ORDER

    n = len(trace_paths)
    assert len(output_paths)        == n, "output_paths length mismatch"
    assert len(mutant_output_paths) == n, "mutant_output_paths length mismatch"
    assert n > 0,                         "at least one test required"

    # ── Step 1: build pass/fail vector ───────────────────────────────────────
    pass_fail = [
        _outputs_differ(output_paths[i], mutant_output_paths[i])
        for i in range(n)
    ]
    total_fail = sum(pass_fail)
    total_pass = n - total_fail

    # ── Step 2: build ef / ep / nf / np counters per rule ────────────────────
    rule_stats: dict = {r: {"ef": 0, "ep": 0, "nf": 0, "np": 0}
                        for r in all_rules}
    for i, trace_path in enumerate(trace_paths):
        executed = _parse_trace_rules(trace_path)
        failed   = pass_fail[i]
        for rule in all_rules:
            s = rule_stats[rule]
            if rule in executed:
                if failed: s["ef"] += 1
                else:      s["ep"] += 1
            else:
                if failed: s["nf"] += 1
                else:      s["np"] += 1

    # ── Step 3: compute suspiciousness per formula ────────────────────────────
    scores: dict = {}
    for fname in formulae:
        fn    = FORMULAE[fname]
        svals = {
            rule: fn(
                rule_stats[rule]["ef"],
                rule_stats[rule]["ep"],
                rule_stats[rule]["nf"],
                rule_stats[rule]["np"],
            )
            for rule in all_rules
        }
        scores[fname] = svals

    # ── Step 4: compute EXAM (6 formulae × 3 modes = 18 values) ──────────────
    exam_scores: dict = {}
    for fname, svals in scores.items():
        for mode in TIE_MODES:
            exam_scores[f"{fname}_{mode}"] = _exam_for_buggy_rules(
                svals, buggy_rules, all_rules, mode
            )

    return {
        "mutant":      mutant_name,
        "buggy_rules": buggy_rules,
        "total_tests": n,
        "total_fail":  total_fail,
        "total_pass":  total_pass,
        "rule_stats":  rule_stats,
        "scores":      scores,
        "exam_scores": exam_scores,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Batch computation
# ─────────────────────────────────────────────────────────────────────────────

def compute_sbfl_batch(
    mutant_names:        list,
    get_trace_paths_fn,
    get_output_path_fn,
    get_mutant_output_fn,
    all_rules:           list,
    formulae:            list = None,
    buggy_rules_map      : dict | None = None,
) -> list:
    """
    Compute per-mutant SBFL for every mutant in `mutant_names`.

    Parameters
    ----------
    mutant_names         : list[str]
    get_trace_paths_fn   : callable(mutant_name) → list[str]
    get_output_path_fn   : callable(i: int) → str
    get_mutant_output_fn : callable(mutant_name, i: int) → str
    all_rules            : list[str]
    formulae             : list[str]  (default: FORMULA_ORDER)

    Returns
    -------
    list[dict]  — one result dict per mutant
    """
    results = []
    rule_map = buggy_rules_map if buggy_rules_map is not None else BUGGY_RULES

    for mutant in mutant_names:
        buggy = rule_map.get(mutant)
        if buggy is None:
            logger.warning(f"No buggy rule mapping for {mutant} – skipping")
            continue

        trace_paths         = get_trace_paths_fn(mutant)
        n_tests             = len(trace_paths)
        output_paths        = [get_output_path_fn(i)           for i in range(n_tests)]
        mutant_output_paths = [get_mutant_output_fn(mutant, i) for i in range(n_tests)]

        result = compute_sbfl_for_mutant(
            trace_paths         = trace_paths,
            output_paths        = output_paths,
            mutant_output_paths = mutant_output_paths,
            all_rules           = all_rules,
            mutant_name         = mutant,
            buggy_rules         = buggy,
            formulae            = formulae,
        )
        results.append(result)

        # Progress log — AC scores only (readable width)
        ac_log = "  ".join(
            f"{k}={v:.3f}"
            for k, v in result["exam_scores"].items()
            if k.endswith("_AC")
        )
        logger.info(f"{mutant}: fail={result['total_fail']}/{n_tests}  {ac_log}")

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Aggregation across mutants  (matches Table 7 layout)
# ─────────────────────────────────────────────────────────────────────────────

def summarize_exam_scores(
    results:  list,
    formulae: list = None,
    modes:    list = None,
) -> dict:
    """
    Aggregate EXAM scores across all mutants.

    Returns mean / median / std for every (formula, mode) pair,
    matching Troya et al. (2018) Table 7.

    Returns
    -------
    dict["{formula}_{mode}" → {"mean", "median", "std", "per_mutant"}]
    """
    if formulae is None:
        formulae = FORMULA_ORDER
    if modes is None:
        modes = list(TIE_MODES)

    summary: dict = {}
    for fname in formulae:
        for mode in modes:
            key    = f"{fname}_{mode}"
            values = [
                r["exam_scores"][key]
                for r in results
                if key in r["exam_scores"]
            ]
            if not values:
                continue
            summary[key] = {
                "mean":       statistics.mean(values),
                "median":     statistics.median(values),
                "std":        statistics.stdev(values) if len(values) > 1 else 0.0,
                "per_mutant": values,
            }
    return summary


# ─────────────────────────────────────────────────────────────────────────────
# Pretty-print: Table 7 style
# ─────────────────────────────────────────────────────────────────────────────

def print_summary_table(
    summary:  dict,
    formulae: list = None,
    dataset:  str  = "",
) -> None:
    """
    Print a Table-7-aligned summary.

    Columns:  Formula | AC mdn / AC mean / AC sd | BC mdn | WC mdn
    """
    if formulae is None:
        formulae = FORMULA_ORDER

    title = f"  EXAM Score Summary{' — ' + dataset if dataset else ''}  "
    bar   = "=" * 72
    print(f"\n{bar}")
    print(title.center(72))
    print(bar)
    print(
        f"{'Formula':<14} | "
        f"{'AC_mdn':>7} {'AC_mean':>7} {'AC_sd':>6} | "
        f"{'BC_mdn':>7} | "
        f"{'WC_mdn':>7}"
    )
    print("-" * 72)
    for fname in formulae:
        ac = summary.get(f"{fname}_AC", {})
        bc = summary.get(f"{fname}_BC", {})
        wc = summary.get(f"{fname}_WC", {})
        print(
            f"{fname:<14} | "
            f"{ac.get('median', float('nan')):>7.4f} "
            f"{ac.get('mean',   float('nan')):>7.4f} "
            f"{ac.get('std',    float('nan')):>6.4f} | "
            f"{bc.get('median', float('nan')):>7.4f} | "
            f"{wc.get('median', float('nan')):>7.4f}"
        )
    print(bar)


# ─────────────────────────────────────────────────────────────────────────────
# CSV export
# ─────────────────────────────────────────────────────────────────────────────

def export_exam_to_csv(
    results:  list,
    out_path: str,
    formulae: list = None,
) -> None:
    """
    Write per-mutant EXAM scores (18 values) to CSV.

    Columns:
        mutant, buggy_rules, total_tests, total_fail,
        ochiai_AC/BC/WC, tarantula_AC/BC/WC, dstar_AC/BC/WC,
        kulczynski2_AC/BC/WC, mountford_AC/BC/WC, zoltar_AC/BC/WC
    """
    if formulae is None:
        formulae = FORMULA_ORDER

    exam_keys  = [f"{f}_{m}" for f in formulae for m in TIE_MODES]
    fieldnames = ["mutant", "buggy_rules", "total_tests", "total_fail"] + exam_keys

    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            row: dict = {
                "mutant":      r["mutant"],
                "buggy_rules": "|".join(r["buggy_rules"]),
                "total_tests": r["total_tests"],
                "total_fail":  r["total_fail"],
            }
            for k in exam_keys:
                val = r["exam_scores"].get(k, float("nan"))
                row[k] = f"{val:.6f}"
            writer.writerow(row)

    logger.info(f"EXAM scores written → {out_path}")


# ─────────────────────────────────────────────────────────────────────────────
# Sanity check  (run with: python -m src.analyzer.sbfl_analyzer)
# ─────────────────────────────────────────────────────────────────────────────

def run_sanity_check() -> None:
    """
    Four self-contained checks:

    1. Formula boundary conditions — ef==0 must always yield 0.0
    2. Tie-breaking correctness    — three rules all tied, buggy in middle
    3. Perfect-rank case           — no tie, buggy rule highest
    4. Multi-fault case            — two buggy rules, mixed ranks

    For BibTeX2DocBook Ochiai (AC), Troya et al. Table 7 reports ~0.188.
    After running the full experiment, confirm your result is in [0.14, 0.24].
    """
    SEP = "=" * 64

    # ── Check 1: boundary conditions ─────────────────────────────────────────
    print(f"\n{SEP}")
    print("CHECK 1: Formula boundary conditions (ef=0 must always → 0.0)")
    print(SEP)

    boundary_cases = [
        (0, 5, 5, 0,  "ef=0 (rule never in failing test) → 0"),
        (0, 0, 5, 5,  "ef=0, ep=0 (rule never executed)  → 0"),
        (5, 0, 0, 5,  "perfect discriminator"),
        (5, 5, 0, 0,  "all tests execute rule"),
        (3, 2, 2, 3,  "typical mixed case"),
        (1, 0, 0, 0,  "single test, single execution"),
    ]

    hdr = f"{'Case':<42}" + "".join(f"{f:>11}" for f in FORMULA_ORDER)
    print(hdr)
    print("-" * len(hdr))

    ok_boundary = True
    for ef, ep, nf, np_, desc in boundary_cases:
        row  = f"{desc:<42}"
        fail = False
        for fname in FORMULA_ORDER:
            val = FORMULAE[fname](ef, ep, nf, np_)
            if ef == 0 and val != 0.0:
                row += f"{'ERR':>11}"
                fail = True
            else:
                row += f"{val:>11.4f}"
        print(row + ("  ✗" if fail else ""))
        if fail:
            ok_boundary = False

    print("  →", "PASS ✔" if ok_boundary else "FAIL ✗  (ef=0 cases must return 0.0)")

    # ── Check 2: tie-breaking ─────────────────────────────────────────────────
    print(f"\n{SEP}")
    print("CHECK 2: Tie-breaking  (3 rules, all score=0.5, buggy=rule_B)")
    print("Expected:  BC=0.3333  AC=0.6667  WC=1.0000")
    print(SEP)

    tied_svals = {"rule_A": 0.5, "rule_B": 0.5, "rule_C": 0.5}
    tied_rules = ["rule_A", "rule_B", "rule_C"]
    expected   = {"BC": 1/3, "AC": 2/3, "WC": 1.0}
    ok_tie     = True

    for mode in TIE_MODES:
        exam  = _exam_for_buggy_rules(tied_svals, ["rule_B"], tied_rules, mode)
        ok    = abs(exam - expected[mode]) < 1e-9
        ok_tie = ok_tie and ok
        print(f"  mode={mode}  EXAM={exam:.6f}  expected={expected[mode]:.6f}"
              f"  {'✔' if ok else '✗ WRONG'}")

    # ── Check 3: perfect rank (no tie) ────────────────────────────────────────
    print(f"\n{SEP}")
    print("CHECK 3: Perfect rank  (rule_B highest, no tie)")
    print("Expected:  BC=AC=WC=0.3333  (rank 1 of 3)")
    print(SEP)

    perf_svals = {"rule_A": 0.3, "rule_B": 0.9, "rule_C": 0.1}
    ok_perf    = True
    for mode in TIE_MODES:
        exam = _exam_for_buggy_rules(perf_svals, ["rule_B"], tied_rules, mode)
        ok   = abs(exam - 1/3) < 1e-9
        ok_perf = ok_perf and ok
        print(f"  mode={mode}  EXAM={exam:.6f}  expected={1/3:.6f}"
              f"  {'✔' if ok else '✗ WRONG'}")

    # ── Check 4: multi-fault ──────────────────────────────────────────────────
    print(f"\n{SEP}")
    print("CHECK 4: Multi-fault  (buggy=[rule_A, rule_B])")
    print("  svals = {A:0.9, B:0.5, C:0.5}")
    print("  rule_A: rank 1/3 in all modes")
    print("  rule_B: BC=2/3, AC=2.5/3, WC=3/3")
    print("  BC → min(1/3, 2/3) = 1/3 = 0.3333")
    print("  WC → max(1/3, 3/3) = 1.0")
    print("  AC → mean(1/3, 2.5/3) = 3.5/6 = 0.5833")
    print(SEP)

    multi_svals  = {"rule_A": 0.9, "rule_B": 0.5, "rule_C": 0.5}
    multi_expect = {"BC": 1/3, "AC": 3.5/6, "WC": 1.0}
    ok_multi     = True
    for mode in TIE_MODES:
        exam  = _exam_for_buggy_rules(
            multi_svals, ["rule_A", "rule_B"], tied_rules, mode
        )
        ok    = abs(exam - multi_expect[mode]) < 1e-9
        ok_multi = ok_multi and ok
        print(f"  mode={mode}  EXAM={exam:.6f}  expected={multi_expect[mode]:.6f}"
              f"  {'✔' if ok else '✗ WRONG'}")

    # ── Summary ───────────────────────────────────────────────────────────────
    all_ok = ok_boundary and ok_tie and ok_perf and ok_multi
    print(f"\n{SEP}")
    print(f"Overall: {'ALL CHECKS PASSED ✔' if all_ok else 'SOME CHECKS FAILED ✗'}")
    print(SEP)
    if all_ok:
        print(
            "\nNext step: run compute_sbfl_batch on BibTeX2DocBook with 100 random\n"
            "test models and verify Ochiai_AC mean ≈ 0.188 (Troya Table 7).\n"
        )


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    run_sanity_check()
