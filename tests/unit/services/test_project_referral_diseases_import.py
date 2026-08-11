import builtins
import importlib
import sys


def test_project_referral_disease_service_does_not_import_verification_blueprint(monkeypatch):
    sys.modules.pop("services.project_referral_diseases", None)
    original_import = builtins.__import__

    def reject_web_blueprint(name, *args, **kwargs):
        if name == "verify_encounter_set" or name.startswith("verify_encounter_set."):
            raise AssertionError("worker-safe referral policy imported the verification web blueprint")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", reject_web_blueprint)

    module = importlib.import_module("services.project_referral_diseases")

    assert callable(module.canonicalize_project_positive_diseases)
