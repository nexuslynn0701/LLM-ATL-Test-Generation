"""Pure SBFL suspiciousness formulas, independent of any plotting code.

Arguments are (ef, ep, nf, np): covered failing/passing and uncovered
failing/passing tests. Zero-denominator handling preserves the experiment's
existing definitions. Invalid executions do not enter these counts.
"""
import math

def ochiai(ef, ep, nf, np):
    d = math.sqrt((ef + nf) * (ef + ep))
    return ef / d if d else 0.0

def tarantula(ef, ep, nf, np):
    fail_rate = ef / (ef + nf) if ef + nf else 0.0
    pass_rate = ep / (ep + np) if ep + np else 0.0
    d = fail_rate + pass_rate
    return fail_rate / d if d else 0.0

def dstar2(ef, ep, nf, np):
    d = ep + nf
    return ef * ef / d if d else (math.inf if ef else 0.0)

def kulczynski2(ef, ep, nf, np):
    a = ef / (ef + nf) if ef + nf else 0.0
    b = ef / (ef + ep) if ef + ep else 0.0
    return 0.5 * (a + b)

def mountford(ef, ep, nf, np):
    d = 0.5 * (ef * ep + ef * nf) + ep * nf
    return ef / d if d else (math.inf if ef else 0.0)

def zoltar(ef, ep, nf, np):
    if not ef:
        return 0.0
    return ef / (ef + ep + nf + (10000.0 * ep * nf / ef))

def arithmetic_mean(ef, ep, nf, np):
    a = ef / (ef + nf) if ef + nf else 0.0
    b = ep / (ep + np) if ep + np else 0.0
    return a - b

def barinel(ef, ep, nf, np):
    if not ef: return 0.0
    return 1.0 - ep / (ep + ef)

def braun_banquet(ef, ep, nf, np):
    a = ef / (ef + nf) if ef + nf else 0.0
    b = ep / (ep + np) if ep + np else 0.0
    d = a + b
    return a / d if d else 0.0

def baroni_urbani_buser(ef, ep, nf, np):
    return (ef * np) / ((ef + ep) * (ef + nf + ep + np)) if (ef + ep) * (ef + nf + ep + np) else 0.0

def cohen(ef, ep, nf, np):
    d = (ef + nf) * (ep + np) * (ef + ep) * (nf + np)
    return (2*ef*np - 2*nf*ep) / math.sqrt(d) if d > 0 else 0.0

def ochiai2(ef, ep, nf, np):
    a = ef / (ef + nf) if ef + nf else 0.0
    b = ef / (ef + ep) if ef + ep else 0.0
    return a * b

def op2(ef, ep, nf, np):
    a = ef / (ef + nf) if ef + nf else 0.0
    b = ep / (ep + np) if ep + np else 0.0
    return a - b / (b + 1) if (b + 1) else a

def phi(ef, ep, nf, np):
    d = (ef + nf) * (ep + np) * (ef + ep) * (nf + np)
    return (ef*np - nf*ep) / math.sqrt(d) if d > 0 else 0.0

def pierce(ef, ep, nf, np):
    a = ef / (ef + nf) if ef + nf else 0.0
    b = ep / (ep + np) if ep + np else 0.0
    return a - b

def rogers_tanimoto(ef, ep, nf, np):
    d = ef + nf + ep + np
    return (ef + np) / d if d else 0.0

def russell_rao(ef, ep, nf, np):
    d = ef + nf + ep + np
    return ef / d if d else 0.0

def simple_matching(ef, ep, nf, np):
    d = ef + nf + ep + np
    return (ef + np) / d if d else 0.0

FORMULAS = {
    'ochiai': ochiai,
    'tarantula': tarantula,
    'dstar2': dstar2,
    'kulczynski2': kulczynski2,
    'mountford': mountford,
    'zoltar': zoltar,
    'arithmetic_mean': arithmetic_mean,
    'barinel': barinel,
    'braun_banquet': braun_banquet,
    'baroni_urbani_buser': baroni_urbani_buser,
    'cohen': cohen,
    'ochiai2': ochiai2,
    'op2': op2,
    'phi': phi,
    'pierce': pierce,
    'rogers_tanimoto': rogers_tanimoto,
    'russell_rao': russell_rao,
    'simple_matching': simple_matching,
}
