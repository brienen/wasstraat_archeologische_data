#!/usr/bin/env python3
"""
Test runner voor de Wasstraat unit tests.

Aanbevolen: gebruik een venv met pytest:
    ./tests/setup_venv.sh
    source .venv/bin/activate
    python -m pytest tests/unit/ -v

Fallback (zonder venv/pytest):
    python3 tests/run_tests.py
"""
import sys
import os
import types
import unittest
import re

# Project root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "tests"))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "airflow_app", "dags"))
sys.path.insert(0, PROJECT_ROOT)


# ============================================================
# Zorg dat pytest importeerbaar is (stub als het niet echt is)
# ============================================================
try:
    import pytest
except ImportError:
    # Maak een minimale pytest stub zodat @pytest.mark.parametrize werkt
    pytest_mod = types.ModuleType("pytest")

    def _parametrize(argnames, argvalues, **kwargs):
        """Decorator die parametrized test cases omzet naar losse methods."""
        if isinstance(argnames, str):
            argnames = [a.strip() for a in argnames.split(",")]

        def decorator(func):
            func._parametrize = (argnames, argvalues)
            return func
        return decorator

    class _MarkNS:
        parametrize = staticmethod(_parametrize)

        def __getattr__(self, name):
            """Andere markers (unit, integration) zijn no-ops."""
            def noop_decorator(*args, **kwargs):
                if len(args) == 1 and callable(args[0]):
                    return args[0]
                return lambda f: f
            return noop_decorator

    pytest_mod.mark = _MarkNS()

    class _FixtureDecorator:
        def __call__(self, *args, **kwargs):
            if args and callable(args[0]):
                return args[0]
            return lambda f: f

    pytest_mod.fixture = _FixtureDecorator()

    from contextlib import contextmanager

    @contextmanager
    def _raises(exc_type, match=None):
        try:
            yield
        except exc_type:
            pass
        except Exception as e:
            raise AssertionError(f"Expected {exc_type.__name__}, got {type(e).__name__}: {e}")
        else:
            raise AssertionError(f"Expected {exc_type.__name__} but no exception was raised")

    pytest_mod.raises = _raises

    sys.modules["pytest"] = pytest_mod
    import pytest


# ============================================================
# Conftest setup (mocks voor shared.config, roman, etc.)
# ============================================================

# --- Mock roman ---
if "roman" not in sys.modules:
    roman_mod = types.ModuleType("roman")
    def _fromRoman(s):
        m = {"I":1,"V":5,"X":10,"L":50,"C":100,"D":500,"M":1000}
        r = 0; s = s.upper()
        for i in range(len(s)):
            if i+1<len(s) and m.get(s[i],0)<m.get(s[i+1],0): r-=m.get(s[i],0)
            else: r+=m.get(s[i],0)
        return r
    roman_mod.fromRoman = _fromRoman
    roman_mod.toRoman = lambda n: ""
    sys.modules["roman"] = roman_mod

# --- Mock timeperiod2daterange ---
if "timeperiod2daterange" not in sys.modules:
    tp = types.ModuleType("timeperiod2daterange")
    tp.detection2daterange = lambda x: None
    sys.modules["timeperiod2daterange"] = tp

# --- Mock shared.config ---
mc = types.ModuleType("shared.config")
for a in [
    "MONGO_URI","MONGO_STAGING_URI","MONGO_FILES_URI","MONGO_ANALYSE_URI",
    "MONGO_SERVER","MONGO_INITDB_ROOT_USERNAME","MONGO_INITDB_ROOT_PASSWORD",
    "DB_STAGING","DB_FILES","DB_ANALYSE",
    "COLL_ANALYSE","COLL_ANALYSE_CLEAN","COLL_PLAATJES","COLL_FILENAMES",
    "COLL_STAGING_METAINFO","COLL_STAGING_OUD","COLL_STAGING_NIEUW",
    "COLL_STAGING_MAGAZIJNLIJST","COLL_STAGING_DELFIT","COLL_STAGING_DIGIFOTOS",
    "COLL_STAGING_MONSTER","COLL_STAGING_REFERENTIETABELLEN","COLL_STAGING_RAPPORTEN",
    "COLL_ANALYSE_FOTO","COLL_ANALYSE_ARTEFACT","COLL_ANALYSE_PROJECT",
    "COLL_ANALYSE_VONDST","COLL_ANALYSE_SPOOR","COLL_ANALYSE_VLAK",
    "COLL_ANALYSE_PUT","COLL_ANALYSE_DOOS","COLL_ANALYSE_STANDPLAATS",
    "COLL_ANALYSE_STELLING","COLL_ANALYSE_PLAATSING","COLL_ANALYSE_VINDPLAATS",
    "ES_HOST","AIRFLOW_TEMPDIR","AIRFLOW_LOGDIR",
    "AIRFLOW_INPUT_PROJECTEN","AIRFLOW_INPUT_IMAGES","AIRFLOW_INPUT_DELFIT",
    "AIRFLOW_INPUT_MAGAZIJNLIJST","AIRFLOW_INPUT_DIGIFOTOS","AIRFLOW_INPUT_MONSTER",
    "AIRFLOW_INPUT_RAPPORTEN","AIRFLOW_OUTPUT_MEDIA",
    "FILE_WORD_ICON","FILE_ABREXCEL","FILE_EXTRA_PROJECTS","FILE_IMPORT_FILES_EXCEL",
]:
    setattr(mc, a, "test")
mc.MONGO_MINPOOLSIZE = 50
mc.AIRFLOW_WASSTRAAT_CONFIG = os.path.join(
    PROJECT_ROOT, "data", "wasstraat_config", "Wasstraat_Config_HarmonizeV3.xlsx"
)
mc.IMAGE_EXTENSIONS = [".jpg",".jpeg",".gif",".png",".tif",".psd",".pdf",".jp2",".doc",".docx"]
sys.modules["shared.config"] = mc
sys.modules["shared"] = types.ModuleType("shared")

cc = types.ModuleType("shared.const")
with open(os.path.join(PROJECT_ROOT, "shared", "const.py")) as f:
    exec(f.read(), cc.__dict__)
sys.modules["shared.const"] = cc


# ============================================================
# Parametrize-aware TestLoader
# ============================================================

def collect_and_run_pytest_classes(test_classes):
    """
    Draait pytest-style test classes (niet afgeleid van unittest.TestCase)
    met ondersteuning voor @pytest.mark.parametrize.
    Retourneert (passed, failed, errors) counts.
    """
    passed = 0
    failed = 0
    errors = 0

    for cls in test_classes:
        instance = cls()
        methods = {}

        for name in dir(cls):
            if not name.startswith("test_"):
                continue
            method = getattr(cls, name)
            if not callable(method):
                continue

            if hasattr(method, "_parametrize"):
                argnames, argvalues = method._parametrize
                for i, vals in enumerate(argvalues):
                    if not isinstance(vals, (list, tuple)):
                        vals = (vals,)
                    kwargs = dict(zip(argnames, vals))
                    suffix = "_".join(str(v).replace(" ","_")[:15] for v in vals)
                    suffix = re.sub(r'[^a-zA-Z0-9_]', '', suffix)
                    methods[f"{name}[{suffix}]"] = (method, kwargs)
            else:
                methods[name] = (method, {})

        for test_name, (method, kwargs) in sorted(methods.items()):
            full_name = f"{cls.__name__}::{test_name}"
            try:
                method(instance, **kwargs)
                passed += 1
                print(f"  PASS  {full_name}")
            except AssertionError as e:
                failed += 1
                print(f"  FAIL  {full_name}: {e}")
            except Exception as e:
                errors += 1
                print(f"  ERROR {full_name}: {type(e).__name__}: {e}")

    return passed, failed, errors


# ============================================================
# Main: discover en run alle tests
# ============================================================

if __name__ == "__main__":
    test_modules = []

    # foto_parsing (geen externe deps behalve shared.const)
    from unit.test_foto_parsing import (
        TestObjectfotoRegex, TestTekeningRegex, TestProjectfotoRegex,
        TestRapportRegex, TestProjectcodeExtractie, TestArtefactsoortDetectie
    )
    test_modules.extend([
        TestObjectfotoRegex, TestTekeningRegex, TestProjectfotoRegex,
        TestRapportRegex, TestProjectcodeExtractie, TestArtefactsoortDetectie
    ])

    # archutils
    from unit.test_archutils import (
        TestConvertToInt, TestConvertToBool, TestConvertToDate,
        TestFixDatering, TestLogError
    )
    test_modules.extend([
        TestConvertToInt, TestConvertToBool, TestConvertToDate,
        TestFixDatering, TestLogError
    ])

    # rijksdriehoek
    from unit.test_rijksdriehoek import TestRdToWgs, TestWgsToRd, TestRoundTrip
    test_modules.extend([TestRdToWgs, TestWgsToRd, TestRoundTrip])

    # harmonizer
    try:
        from unit.test_harmonizer import (
            TestGetKolomValues, TestGetAggrTables, TestLoadHarmonizer,
            TestGetHarmonizeAggr, TestGetObjects
        )
        test_modules.extend([
            TestGetKolomValues, TestGetAggrTables, TestLoadHarmonizer,
            TestGetHarmonizeAggr, TestGetObjects
        ])
    except Exception as e:
        print(f"SKIP harmonizer tests: {e}")

    # encoding
    try:
        from unit.test_encoding import (
            TestSanitizeTextBasic, TestSanitizeTextDiacritics,
            TestSanitizeTextMojibake, TestSanitizeTextControlChars,
            TestSanitizeTextField, TestSanitizeAllStringFields,
            TestSanitizeTextArchaeologicalData,
            TestMdbExportEncoding, TestQuestionMarkRegression
        )
        test_modules.extend([
            TestSanitizeTextBasic, TestSanitizeTextDiacritics,
            TestSanitizeTextMojibake, TestSanitizeTextControlChars,
            TestSanitizeTextField, TestSanitizeAllStringFields,
            TestSanitizeTextArchaeologicalData,
            TestMdbExportEncoding, TestQuestionMarkRegression
        ])
    except Exception as e:
        print(f"SKIP encoding tests: {e}")

    print(f"\nRunning tests from {len(test_modules)} test classes...\n")
    p, f, e = collect_and_run_pytest_classes(test_modules)

    print("\n" + "=" * 60)
    total = p + f + e
    if f == 0 and e == 0:
        print(f"ALL {p} TESTS PASSED")
    else:
        print(f"{p} passed, {f} failed, {e} errors (total: {total})")
    print("=" * 60)

    sys.exit(0 if (f == 0 and e == 0) else 1)
